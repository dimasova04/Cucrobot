from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    rules_accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    crystals: Mapped[int] = mapped_column(Integer, default=0)
    sub_plan: Mapped[str | None] = mapped_column(String(32))
    sub_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_bonus_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_tier: Mapped[str] = mapped_column(String(16), default="base", server_default="base")


class CrystalTransaction(Base):
    __tablename__ = "crystal_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # start, bonus, purchase, charge, refund, admin
    amount: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    ref_type: Mapped[str | None] = mapped_column(String(16))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Generation(Base):
    __tablename__ = "generations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    model_air: Mapped[str] = mapped_column(String(64))
    model_tier: Mapped[str] = mapped_column(String(16))  # base / premium
    actors: Mapped[list] = mapped_column(JSON, default=list)  # [{"id":1,"name":"..."}]
    location: Mapped[str] = mapped_column(String(255))
    user_detail: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running, done, failed, rejected
    cost_usd: Mapped[float | None] = mapped_column(Float)
    crystals_charged: Mapped[int] = mapped_column(Integer, default=0)
    result_file_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_payment_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))  # tribute / stars
    external_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    product: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="")
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / unresolved
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Actor(Base):
    __tablename__ = "actors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    refs: Mapped[list["ActorRef"]] = relationship(
        back_populates="actor", cascade="all, delete-orphan", order_by="ActorRef.order", lazy="selectin"
    )


class ActorRef(Base):
    __tablename__ = "actor_refs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    actor: Mapped[Actor] = relationship(back_populates="refs")


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    orientation: Mapped[str] = mapped_column(String(16), default="portrait")  # portrait / landscape
    ref_file_id: Mapped[str | None] = mapped_column(String(255))
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
