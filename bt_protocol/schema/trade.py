#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from uuid import UUID as PyUUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint

from bt_protocol._protocol import (
    AccountBody,
    ExperimentBody,
    PositionBody,
    Resp,
    TradeBody,
)
from bt_protocol.schema import DictSerializableMixin


class Base(DictSerializableMixin, DeclarativeBase):
    def _experiment_id_bytes(self) -> bytes:
        exp_id = getattr(self, "experiment_id", None)
        return exp_id.bytes if exp_id is not None else b""


class User(Base):

    __tablename__ = "user_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255, collation="C"), nullable=False)
    client_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), unique=True, server_default=text("gen_random_uuid()")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_user_id_client_id"),
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, user_id={self.user_id!r}, client_id={self.client_id!r})"


class Experiment(Base):

    __tablename__ = "experiment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("user_info.client_id", ondelete="CASCADE")
    )
    strategy: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    extra_info: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    experiment_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), unique=True, server_default=text("gen_random_uuid()")
    )

    __table_args__ = (
        UniqueConstraint(
            "client_id", "strategy", "extra_info", name="uq_client_strategy_extra_info"
        ),
    )

    vtorders: Mapped[List["vtOrder"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", lazy="raise"
    )
    vtpositions: Mapped[List["vtPosition"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", lazy="raise"
    )
    account: Mapped[List["vtAccount"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", lazy="raise"
    )

    def serialize(self, include_id: bool = False) -> Resp:
        return Resp(body=ExperimentBody(experiment_id=self._experiment_id_bytes()))

    def __repr__(self) -> str:
        return (
            f"Experiment(id={self.id!r}, experiment_id={self.experiment_id!r}, "
            f"client_id={self.client_id!r}, strategy={self.strategy!r}, "
            f"extra_info={self.extra_info!r})"
        )


class vtOrder(Base):

    __tablename__ = "vtorder"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    order_type: Mapped[int] = mapped_column(Integer, nullable=False)
    exec_type: Mapped[int] = mapped_column(Integer, nullable=False)
    created_dt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    experiment_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("experiment.experiment_id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint(
            "order_id", "experiment_id", name="uq_order_id_experiment_id"
        ),
        UniqueConstraint("order_id", name="uq_vtorder_order_id"),
        Index("ix_vtorder_experiment_id", "experiment_id"),
    )

    experiment: Mapped["Experiment"] = relationship(
        back_populates="vtorders", lazy="raise"
    )
    order_bits: Mapped[List["OrderBit"]] = relationship(
        back_populates="vtorder", cascade="all, delete-orphan", lazy="raise"
    )

    def __repr__(self) -> str:
        return (
            f"vtOrder(id={self.id!r}, sid={self.sid!r}, price={self.price!r}, "
            f"size={self.size!r}, order_type={self.order_type!r}, "
            f"exec_type={self.exec_type!r}, order_id={self.order_id!r}, "
            f"created_dt={self.created_dt!r})"
        )


class OrderBit(Base):

    __tablename__ = "order_bit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[bytes] = mapped_column(
        ForeignKey("vtorder.order_id", ondelete="CASCADE")
    )
    executed_dt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    executed_price: Mapped[float] = mapped_column(Float, nullable=False)
    executed_size: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    comm: Mapped[float] = mapped_column(Float, nullable=False)
    isbuy: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    __table_args__ = (
        UniqueConstraint("order_id", "executed_dt", name="uq_order_executed_dt"),
    )

    vtorder: Mapped["vtOrder"] = relationship(
        back_populates="order_bits", lazy="raise"
    )

    def serialize(self, include_id: bool = False) -> Resp:
        body = TradeBody(
            order_id=self.order_id,
            executed_dt=self.executed_dt,
            executed_size=self.executed_size,
            executed_price=self.executed_price,
            comm=self.comm,
            isbuy=self.isbuy,
        )
        return Resp(body=body)

    def __repr__(self) -> str:
        return (
            f"OrderBit(id={self.id!r}, order_id={self.order_id!r}, "
            f"executed_dt={self.executed_dt!r}, executed_price={self.executed_price!r}, "
            f"executed_size={self.executed_size!r}, comm={self.comm!r})"
        )


class vtPosition(Base):

    __tablename__ = "vtposition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    datetime: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    created_dt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    experiment_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("experiment.experiment_id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint(
            "datetime",
            "sid",
            "experiment_id",
            name="uq_position_datetime_sid_experiment_id",
        ),
        Index("ix_vtposition_experiment_id", "experiment_id"),
    )

    experiment: Mapped["Experiment"] = relationship(
        back_populates="vtpositions", lazy="raise"
    )

    def serialize(self, include_id: bool = False) -> Resp:
        """Serialize the DB position row into a :class:`Resp` wrapping :class:`PositionBody`.

        Note on PnL caliber:
        * ``self.pnl`` in DB is the **unrealized (floating)** PnL bucket, and
          ``self.realized_pnl`` is the **realized** PnL bucket. Both are passed
          as-is so ``bt_core``'s ``simulate._start`` can restore the two buckets
          independently without double-counting.
        * ``pnl_ratio`` is reconstructed on the fly as
          ``(pnl + realized_pnl) / (size * cost_basis)`` when ``size * cost_basis > 0``,
          matching ``bt_core``'s ``Position._update_pnl_ratio`` formula.
        """
        realized = self.realized_pnl if self.realized_pnl is not None else 0.0
        floating = self.pnl if self.pnl is not None else 0.0
        total_cost = (self.size or 0) * (self.cost_basis or 0.0)
        pnl_ratio = (floating + realized) / total_cost if total_cost > 0 else 0.0
        body = PositionBody(
            sid=self.sid,
            datetime=self.datetime,
            created_dt=self.created_dt,
            size=self.size,
            available=self.available,
            cost_basis=self.cost_basis,
            pnl=floating,
            pnl_ratio=pnl_ratio,
            experiment_id=self._experiment_id_bytes(),
            realized_pnl=realized,
        )
        return Resp(body=body)

    def __repr__(self) -> str:
        return (
            f"vtPosition(id={self.id!r}, sid={self.sid!r}, datetime={self.datetime!r}, "
            f"cost_basis={self.cost_basis!r}, size={self.size!r}, "
            f"available={self.available!r}, pnl={self.pnl!r})"
        )


class vtAccount(Base):

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datetime: Mapped[int] = mapped_column(BigInteger, nullable=False)
    portfolio_value: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[float] = mapped_column(
        Float, default=1.0, server_default="1.0", nullable=False
    )
    margin: Mapped[float] = mapped_column(
        Float, default=0, server_default="0", nullable=False
    )
    experiment_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("experiment.experiment_id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint(
            "datetime", "experiment_id", name="uq_acct_datetime_experiment_id"
        ),
        Index("ix_account_experiment_id", "experiment_id"),
    )

    experiment: Mapped["Experiment"] = relationship(
        back_populates="account", lazy="raise"
    )

    def serialize(self, include_id: bool = False) -> Resp:
        body = AccountBody(
            datetime=self.datetime,
            portfolio_value=self.portfolio_value,
            cash=self.cash,
            pnl=self.pnl,
            leverage=self.leverage,
            margin=self.margin,
            experiment_id=self._experiment_id_bytes(),
        )
        return Resp(body=body)

    def __repr__(self) -> str:
        return (
            f"vtAccount(id={self.id!r}, datetime={self.datetime!r}, "
            f"portfolio_value={self.portfolio_value!r}, cash={self.cash!r}, "
            f"pnl={self.pnl!r}, leverage={self.leverage!r}, margin={self.margin!r})"
        )


__all__ = ["Base", "User", "Experiment", "vtOrder", "OrderBit", "vtPosition", "vtAccount"]
