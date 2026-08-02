#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Union, Literal, Optional

import msgspec

# ---------------------------------------------------------------------------
# Request bodies (tagged union dispatched by msgspec on the "type" field)
# ---------------------------------------------------------------------------

class QueryBody(msgspec.Struct, frozen=True, tag="query"):
    start_date: int
    end_date: int
    sid: List[bytes] = []


class RegisterBody(msgspec.Struct, frozen=True, tag="register"):
    client_id: bytes
    strategy: str
    extra_info: str


class CashBody(msgspec.Struct, frozen=True, tag="cash"):
    session: int
    cash: float


# Filler strategies for OrderBody. Literal keeps the wire format compact (a str)
# while giving static type safety + msgspec validation on decode.
OrderFiller = Literal["default", "vwap", "twap"]


class OrderBody(msgspec.Struct, frozen=True, tag="order"):
    sid: bytes
    order_id: bytes
    order_type: int
    exec_type: int
    sizer_ratio: float
    price: float
    created_dt: int
    filler: OrderFiller = "default"  # default / vwap / twap


# Union of all request bodies. None is allowed because Event defaults body=None.
RequestBody = Union[QueryBody, RegisterBody, CashBody, OrderBody, None]


class Event(msgspec.Struct, frozen=True):
    topic: int
    sub_topic: int = -1
    experiment_id: bytes = b""
    # NOTE: must include None to match the default value; otherwise the type
    # annotation and the default contradict each other.
    body: RequestBody = None


# ---------------------------------------------------------------------------
# Response bodies (tagged union)
# ---------------------------------------------------------------------------

class ExperimentBody(msgspec.Struct, frozen=True, tag="experiment"):
    experiment_id: bytes


class TradeBody(msgspec.Struct, frozen=True, tag="trade"):
    order_id: bytes
    executed_dt: int
    executed_size: int
    executed_price: float
    comm: float
    isbuy: bool


class PositionBody(msgspec.Struct, frozen=True, tag="position"):
    sid: bytes
    datetime: int
    size: int
    available: int
    cost_basis: float
    pnl: float
    created_dt: int
    experiment_id: bytes
    pnl_ratio: float = 0.0  


class AccountBody(msgspec.Struct, frozen=True, tag="account"):
    datetime: int
    portfolio_value: float
    cash: float
    pnl: float
    leverage: float
    margin: float
    experiment_id: bytes


class SnapshotBody(msgspec.Struct, frozen=True, tag="snapshot"):
    account: AccountBody
    positions: List[PositionBody]
    trades: Optional[List[TradeBody]] = None


class Empty(msgspec.Struct, frozen=True, tag="empty"):
    pass


class ErrMSg(msgspec.Struct, frozen=True, tag="error"):
    error: str


class Sentinel(msgspec.Struct, frozen=True, tag="sentinel"):
    pass


BodyItem = Union[
    ExperimentBody,
    TradeBody,
    PositionBody,
    AccountBody,
    SnapshotBody,
    Empty,
    ErrMSg,
    Sentinel,
]


class Resp(msgspec.Struct, frozen=True):
    body: Union[BodyItem, List[BodyItem], None] = None


ResponseTypes = List[Resp]


# ---------------------------------------------------------------------------
# Global codec instances.
#
# Encoders/decoders in msgspec are designed to be reused; constructing one
# per message is wasteful. Keep a small set of typed codecs for the common
# request/response shapes used across the codebase.
# ---------------------------------------------------------------------------

_ENCODER = msgspec.msgpack.Encoder()
_DECODER = msgspec.msgpack.Decoder(type=Event)
_RespDECODER = msgspec.msgpack.Decoder(type=Resp)
_RespListDECODER = msgspec.msgpack.Decoder(type=ResponseTypes)