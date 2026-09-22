"""Refuse to start up insecurely.

Every setting here ships with a default that is right for a laptop and wrong for
the internet. The danger is not that somebody chooses a bad value — it is that
they choose nothing, and a deploy that forgets one environment variable comes up
looking healthy while signing tokens with a published secret or taking payments
through a gateway that never charges anybody.

So the checks run at import of the app, before it serves a request, and they
fail loudly rather than degrading quietly.
"""
import logging

from app.core.config import Settings

logger = logging.getLogger(__name__)


class InsecureConfiguration(RuntimeError):
    """Raised when a production process is configured with a development default."""


# (attribute, unsafe value, what to do about it)
_UNSAFE_DEFAULTS: list[tuple[str, object, str]] = [
    ("jwt_secret", "change-me-in-env", "set JWT_SECRET (openssl rand -hex 32)"),
    ("mock_gateway_secret", "mock-gateway-secret", "set MOCK_GATEWAY_SECRET"),
    ("seed_admin_password", "admin12345", "set SEED_ADMIN_PASSWORD"),
    ("seed_admin_email", "admin@example.com", "set SEED_ADMIN_EMAIL"),
]


def collect_problems(settings: Settings) -> list[str]:
    """Every reason this configuration is unfit to face the public internet."""
    problems = [
        f"{attribute} is still the shipped default — {remedy}"
        for attribute, unsafe, remedy in _UNSAFE_DEFAULTS
        if getattr(settings, attribute) == unsafe
    ]
    if settings.payment_gateway == "mock":
        problems.append(
            "payment_gateway is 'mock', which confirms bookings without taking money "
            "— set PAYMENT_GATEWAY=razorpay"
        )
    if settings.allow_sandbox_payments:
        problems.append(
            "allow_sandbox_payments is on, which lets any renter mark their own booking "
            "paid — unset ALLOW_SANDBOX_PAYMENTS"
        )
    if settings.debug:
        problems.append("debug is on — unset DEBUG")
    if settings.email_backend == "smtp" and settings.smtp_password and not settings.smtp_tls:
        problems.append("SMTP credentials are set without SMTP_TLS — they would go out in clear text")
    if any(origin.startswith("http://") for origin in settings.cors_origins):
        problems.append(f"cors_origins contains a plaintext origin: {settings.cors_origins}")
    if not settings.frontend_url.startswith("https://"):
        problems.append(f"frontend_url is not https: {settings.frontend_url}")
    return problems


def verify(settings: Settings) -> None:
    """Abort a production boot that would be insecure; warn loudly elsewhere.

    Outside production the same problems are only logged, because they are the
    normal state of a development machine. The warning still matters: it is what
    a misconfigured production deploy — one that left ENVIRONMENT unset and so
    never reached the hard check — looks like in the logs.
    """
    problems = collect_problems(settings)
    if not problems:
        return
    if settings.environment == "production":
        raise InsecureConfiguration(
            "Refusing to start in production with insecure configuration:\n  - "
            + "\n  - ".join(problems)
        )
    logger.warning(
        "Configuration is not production-safe (environment=%s):\n  - %s",
        settings.environment,
        "\n  - ".join(problems),
    )
