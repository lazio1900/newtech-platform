from typing import Literal, Optional

from pydantic import BaseModel


class RegistryRequestIn(BaseModel):
    address: str
    dong: Optional[str] = None
    ho: Optional[str] = None
    type: Literal["토지", "집합건물", "건물"] = "집합건물"
    requester_id: Optional[str] = None
    listing_id: Optional[str] = None
    force_refresh: bool = False


class RegistryRequestOut(BaseModel):
    id: int
    ic_id: Optional[int] = None
    status: str
    pdf_url: Optional[str] = None
    cost: int = 0
    cached: bool = False
    error_message: Optional[str] = None


class UsageOut(BaseModel):
    date: str
    issued_count: int
    cached_count: int
    failed_count: int
    total_cost: int
    daily_limit: int
    hourly_limit: int
