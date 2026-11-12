from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Customer(BaseModel):
    customer_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    tier: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(8))
    # Source field "created_at"; renamed so it cannot be confused with the row timestamp.
    customer_since: Mapped[str] = mapped_column(String(40))
    verified: Mapped[bool] = mapped_column(Boolean)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
