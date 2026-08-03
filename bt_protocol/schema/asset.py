#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from typing import Optional
from sqlalchemy import func
from sqlalchemy import Integer, String, ForeignKey, BigInteger, Float, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.inspection import inspect
from sqlalchemy.schema import PrimaryKeyConstraint, CreateTable, UniqueConstraint
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import Identity

__all__ = ["Asset", "Adjustment", "Rightment"]


class Base(DeclarativeBase):
    # PostgreSQL id autoincrement when primary_key / SERIAL / IDENTITY 
    
    def serialize(self, include_id=False):
        if include_id:
            return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        else:
            return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs if c.key != "id"}


class Asset(Base):

    __tablename__ = "asset"
    __table_args__ = (
        PrimaryKeyConstraint("id", "sid", name="pk_id_sid"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    name: Mapped[bytes] = mapped_column(LargeBinary, nullable=False) # String(32, collation="c")
    first_trading: Mapped[int] = mapped_column(Integer, nullable=False)

    # delist or obsorted 
    delist: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    merger: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    adjustment: Mapped[List["Adjustment"]] = relationship("Adjustment", back_populates="asset", cascade="all, delete-orphan", lazy="raise")
    rightment: Mapped[List["Rightment"]] = relationship("Rightment", back_populates="asset", cascade="all, delete-orphan", lazy="raise")


class Adjustment(Base):

    __tablename__ = "adjustment"
    __table_args__ = (
        UniqueConstraint("sid", "report_date", name="uq_sid_report_date_adjustment"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary, 
                                     ForeignKey("asset.sid", onupdate="CASCADE", ondelete="CASCADE"), 
                                     nullable=False, use_existing_column=True)
    report_date: Mapped[int] = mapped_column(Integer, nullable=False, use_existing_column=True)
    register_date: Mapped[int] = mapped_column(Integer, nullable=False, use_existing_column=True)
    ex_date: Mapped[int] = mapped_column(Integer, nullable=False, use_existing_column=True)
    bonus_share: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True, server_default='0') # 送股
    transfer: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True, server_default='0') # 转股
    bonus: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True, server_default='0') # 股息

    asset: Mapped["Asset"] = relationship("Asset", back_populates="adjustment", lazy="raise")


class Rightment(Base):

    __tablename__ = "rightment"
    __table_args__ = (
        UniqueConstraint("sid", "ex_date", name="uq_sid_ex_date_rightment"),
        {"extend_existing": True},
    )

    # NOTE: `sid` is NOT part of the primary key here (consistent with Adjustment).
    # A composite PK (id, sid) would overlap with the FK -> asset.sid and complicate
    # cascade semantics. Use the single-column surrogate `id` as PK; the
    # (sid, ex_date) UniqueConstraint already guarantees business uniqueness.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary,
                                     ForeignKey("asset.sid", onupdate="CASCADE", ondelete="CASCADE"),
                                     nullable=False, use_existing_column=True)
    report_date: Mapped[int] = mapped_column(Integer, nullable=False, use_existing_column=True)
    register_date: Mapped[int] = mapped_column(Integer, nullable=False, use_existing_column=True)
    ex_date: Mapped[int] = mapped_column(Integer, nullable=False, use_existing_column=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True, server_default='0')
    ratio: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True, server_default='0')

    asset: Mapped["Asset"] = relationship("Asset", back_populates="rightment", lazy="raise")


# # --- Partitioning Support ---

# # __table_args__ = (
# #    {'postgresql_partition_by': 'RANGE (tick)', "extend_existing": True},
# # )

# # compile create table with partition by or raw sql ddl
# @compiles(CreateTable)
# def compile_create_partition_table(element, compiler, **kw):
#     table = element.element
#     if "postgresql_partition_by" in table.dialect_options["postgresql"]:
#         partition = table.dialect_options["postgresql"]["postgresql_partition_by"]
#         ddl = compiler.visit_create_table(element)
#         return ddl.replace("\n)", f"\n) PARTITION BY {partition}")
#     return compiler.visit_create_table(element)

