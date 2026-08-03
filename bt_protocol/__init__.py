#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from bt_protocol._protocol import (
    # request
    QueryBody,
    RegisterBody,
    CashBody,
    OrderBody,
    Event,
    # response
    ExperimentBody,
    TradeBody,
    PositionBody,
    AccountBody,
    SnapshotBody,
    Empty,
    ErrMSg,
    Sentinel,
    Resp,
    BodyItem,
    ResponseTypes,
    # global codec (kept for backward compatibility; prefer the public helpers below)
    _ENCODER,
    _DECODER,
    _RespDECODER,
    _RespListDECODER,
    # public codec helpers
    encode_event,
    decode_event,
    encode_resp,
    decode_resp,
    encode_resp_list,
    decode_resp_list,
)

try:
    __version__ = _pkg_version("bt-protocol")
except PackageNotFoundError:  # pragma: no cover - not installed
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    "QueryBody",
    "RegisterBody",
    "CashBody",
    "OrderBody",
    "Event",
    "ExperimentBody",
    "TradeBody",
    "PositionBody",
    "AccountBody",
    "SnapshotBody",
    "Empty",
    "ErrMSg",
    "Sentinel",
    "Resp",
    "BodyItem",
    "ResponseTypes",
    # public codec API
    "encode_event",
    "decode_event",
    "encode_resp",
    "decode_resp",
    "encode_resp_list",
    "decode_resp_list",
]