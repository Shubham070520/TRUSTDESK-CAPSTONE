"""A throwaway table used to exercise BaseModel and BaseHelper."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Widget(BaseModel):
    name: Mapped[str] = mapped_column(String(50), unique=True)
