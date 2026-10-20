#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Optional

from sqlalchemy import Float, ForeignKey, Integer, LargeBinary
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.schema import PrimaryKeyConstraint, UniqueConstraint

from bt_protocol.schema import DictSerializableMixin

__all__ = ["Base", "Asset", "Adjustment", "Rightment"]


class Base(DictSerializableMixin, DeclarativeBase):
    def serialize(self, include_id: bool = False) -> Dict[str, Any]:
        return self.to_dict(include_id=include_id)


class Asset(Base):

    __tablename__ = "asset"
    __table_args__ = (
        PrimaryKeyConstraint("id", "sid", name="pk_id_sid"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    name: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    first_trading: Mapped[int] = mapped_column(Integer, nullable=False)

    delist: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    merger: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    adjustment: Mapped[List["Adjustment"]] = relationship(
        "Adjustment",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    rightment: Mapped[List["Rightment"]] = relationship(
        "Rightment",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class Adjustment(Base):

    __tablename__ = "adjustment"
    __table_args__ = (
        UniqueConstraint("sid", "report_date", name="uq_sid_report_date_adjustment"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(
        LargeBinary,
        ForeignKey("asset.sid", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    report_date: Mapped[int] = mapped_column(Integer, nullable=False)
    register_date: Mapped[int] = mapped_column(Integer, nullable=False)
    ex_date: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_share: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    transfer: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    bonus: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")

    asset: Mapped["Asset"] = relationship(
        "Asset", back_populates="adjustment", lazy="raise"
    )


class Rightment(Base):

    __tablename__ = "rightment"
    __table_args__ = (
        UniqueConstraint("sid", "ex_date", name="uq_sid_ex_date_rightment"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(
        LargeBinary,
        ForeignKey("asset.sid", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    report_date: Mapped[int] = mapped_column(Integer, nullable=False)
    register_date: Mapped[int] = mapped_column(Integer, nullable=False)
    ex_date: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    ratio: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")

    asset: Mapped["Asset"] = relationship(
        "Asset", back_populates="rightment", lazy="raise"
    )
