import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reports.models import IssueType, ReportStatus


class ReportCreate(BaseModel):
    booking_id: uuid.UUID
    issue_type: IssueType
    description: str = Field(min_length=10, max_length=4000)


class ReportPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    booking_reference: str | None = None
    reporter_id: uuid.UUID
    issue_type: IssueType
    description: str
    status: ReportStatus
    admin_notes: str | None
    resolved_at: datetime | None
    photos: list[ReportPhotoOut]
    created_at: datetime


class ReportUpdate(BaseModel):
    status: ReportStatus
    admin_notes: str | None = Field(default=None, max_length=4000)


class ReportList(BaseModel):
    items: list[ReportOut]
    total: int
    limit: int
    offset: int
