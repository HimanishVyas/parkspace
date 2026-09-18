import uuid
from typing import Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.core.deps import DB, CurrentUser
from app.modules.providers import dashboard, service
from app.modules.providers.models import SocietyAgreement
from app.modules.providers.schemas import (
    AgreementOut,
    EarningsOut,
    ProviderDashboardOut,
    ProviderOut,
    ProviderPublic,
    ProviderUpdate,
    SocietyOut,
    SocietyUpdate,
    VerificationSubmit,
)

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    provider_type: Literal["INDIVIDUAL", "SOCIETY"] = "INDIVIDUAL"
    organization_name: str | None = Field(default=None, max_length=200)


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def become_provider(data: ProviderCreate, user: CurrentUser, db: DB):
    """Upgrade the current account to a provider (renters can list a space without
    creating a second account)."""
    provider = await service.create_provider_profile(db, user, data.provider_type, data.organization_name)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.get("/me", response_model=ProviderOut)
async def get_my_provider(user: CurrentUser, db: DB):
    return await service.require_provider(db, user)


@router.patch("/me", response_model=ProviderOut)
async def update_my_provider(data: ProviderUpdate, user: CurrentUser, db: DB):
    provider = await service.require_provider(db, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(provider, key, value)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.post("/me/verification", response_model=ProviderOut)
async def submit_verification(data: VerificationSubmit, user: CurrentUser, db: DB):
    provider = await service.require_provider(db, user)
    await service.submit_verification(db, provider, data)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.get("/dashboard", response_model=ProviderDashboardOut)
async def provider_dashboard(user: CurrentUser, db: DB):
    """Headline numbers for the provider (and society) dashboard."""
    provider = await service.require_provider(db, user)
    return await dashboard.build(db, provider.id)


@router.get("/earnings", response_model=EarningsOut)
async def provider_earnings(user: CurrentUser, db: DB, months: int = Query(default=6, ge=1, le=24)):
    provider = await service.require_provider(db, user)
    summary = await dashboard.build(db, provider.id)
    return EarningsOut(
        total_earnings=summary.total_earnings,
        pending_payout=summary.pending_payout,
        completed_payout=summary.completed_payout,
        upcoming_earnings=summary.upcoming_earnings,
        months=await dashboard.monthly_breakdown(db, provider.id, months),
    )


# --------------------------------------------------------------------------- #
# Society profile and agreements (PRD §29, §30)
# --------------------------------------------------------------------------- #
@router.get("/me/society", response_model=SocietyOut)
async def get_my_society(user: CurrentUser, db: DB):
    provider = await service.require_provider(db, user)
    return await service.require_society(db, provider)


@router.patch("/me/society", response_model=SocietyOut)
async def update_my_society(data: SocietyUpdate, user: CurrentUser, db: DB):
    provider = await service.require_provider(db, user)
    society = await service.require_society(db, provider)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(society, key, value)
    if data.name:
        provider.display_name = data.name
    await db.commit()
    await db.refresh(society)
    return society


@router.get("/me/society/agreements", response_model=list[AgreementOut])
async def list_my_agreements(user: CurrentUser, db: DB):
    """A society can see its own commercial terms; only admins may change them."""
    provider = await service.require_provider(db, user)
    society = await service.require_society(db, provider)
    rows = await db.scalars(
        select(SocietyAgreement)
        .where(SocietyAgreement.society_id == society.id)
        .order_by(SocietyAgreement.start_date.desc())
    )
    return list(rows.all())


@router.get("/{provider_id}", response_model=ProviderPublic)
async def get_provider(provider_id: uuid.UUID, db: DB):
    return await service.get_by_id(db, provider_id)
