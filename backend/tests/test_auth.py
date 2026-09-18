"""Authentication, registration and session invalidation."""
import pytest

from tests.conftest import API, register


async def test_register_and_login(client):
    user = await register(client, email="Nisha@Example.com", full_name="Nisha Patel", phone="98765 43210")
    # Email is normalised to lower case, phone to E.164 for the pilot market.
    assert user.email == "nisha@example.com"

    me = await user.get("/me")
    assert me.status_code == 200
    assert me.json()["phone"] == "+919876543210"

    # Login works with either identifier.
    for identifier in ("nisha@example.com", "+919876543210", "9876543210"):
        response = await client.post(
            f"{API}/auth/login", json={"identifier": identifier, "password": user.password}
        )
        assert response.status_code == 200, f"{identifier}: {response.text}"


async def test_duplicate_email_is_rejected(client):
    await register(client, email="taken@example.com")
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "taken@example.com", "password": "anotherpass1", "full_name": "Someone Else"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACCOUNT_EXISTS"


async def test_wrong_password_is_rejected(client):
    user = await register(client)
    response = await client.post(
        f"{API}/auth/login", json={"identifier": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_unknown_account_gives_the_same_error(client):
    """No account enumeration: an unknown email looks like a wrong password."""
    response = await client.post(
        f"{API}/auth/login", json={"identifier": "nobody@example.com", "password": "whatever123"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_short_password_is_rejected(client):
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "weak@example.com", "password": "short", "full_name": "Weak Password"},
    )
    assert response.status_code == 422


async def test_admin_role_cannot_be_self_assigned(client):
    response = await client.post(
        f"{API}/auth/register",
        json={
            "email": "wannabe@example.com",
            "password": "sup3rsecret",
            "full_name": "Wannabe Admin",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 422


async def test_provider_registration_creates_a_provider_profile(client):
    user = await register(client, role="PROVIDER", full_name="Provider Person")
    profile = await user.get("/providers/me")
    assert profile.status_code == 200
    assert profile.json()["provider_type"] == "INDIVIDUAL"
    assert profile.json()["display_name"] == "Provider Person"


async def test_society_registration_requires_an_organization_name(client):
    response = await client.post(
        f"{API}/auth/register",
        json={
            "email": "society@example.com",
            "password": "sup3rsecret",
            "full_name": "Society Admin",
            "role": "PROVIDER",
            "provider_type": "SOCIETY",
        },
    )
    assert response.status_code == 422

    user = await register(
        client,
        email="society2@example.com",
        role="PROVIDER",
        provider_type="SOCIETY",
        organization_name="Green Acres Society",
    )
    profile = await user.get("/providers/me")
    assert profile.json()["society"]["name"] == "Green Acres Society"


async def test_refresh_returns_a_new_token(client):
    user = await register(client)
    response = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_logout_all_invalidates_existing_tokens(client):
    user = await register(client)
    assert (await user.get("/me")).status_code == 200
    assert (await user.post("/auth/logout-all")).status_code == 204
    # The old access token is now worthless.
    assert (await user.get("/me")).status_code == 401
    # ...and so is the old refresh token.
    stale = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert stale.status_code == 401


async def test_password_change_invalidates_sessions(client):
    user = await register(client)
    response = await user.post(
        "/me/password", json={"current_password": user.password, "new_password": "brand-new-pass"}
    )
    assert response.status_code == 204
    assert (await user.get("/me")).status_code == 401
    login = await client.post(
        f"{API}/auth/login", json={"identifier": user.email, "password": "brand-new-pass"}
    )
    assert login.status_code == 200


async def test_unauthenticated_requests_are_rejected(client):
    assert (await client.get(f"{API}/me")).status_code == 401
    assert (await client.get(f"{API}/bookings")).status_code == 401
    assert (await client.get(f"{API}/admin/dashboard")).status_code == 401
