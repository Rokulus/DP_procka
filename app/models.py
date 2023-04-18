"""
SQL Alchemy models declaration.
https://docs.sqlalchemy.org/en/14/orm/declarative_styles.html#example-two-dataclasses-with-declarative-table
Dataclass style for powerful autocompletion support.

https://alembic.sqlalchemy.org/en/latest/tutorial.html
Note, it is used by alembic migrations logic, see `alembic/env.py`

Alembic shortcuts:
# create migration
alembic revision --autogenerate -m "migration_name"

# apply all migrations
alembic upgrade head
"""
import uuid

from sqlalchemy import String, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user_model"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda _: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(254), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

class MatlabInstances(Base):
    __tablename__ = "matlab_instances"

    id: Mapped[str] = mapped_column(
    UUID(as_uuid=False), primary_key=True, default=lambda _: str(uuid.uuid4())
    )
    matlab_instance: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    user_email: Mapped[str] = mapped_column(
        String(254), nullable=True, default=None
    )
    expires_at: Mapped[int] = mapped_column(Integer, nullable=True, default=None)

