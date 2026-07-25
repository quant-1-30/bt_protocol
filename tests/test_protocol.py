#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""Smoke tests for the bt_protocol package.

These cover the highest-value, lowest-cost checks:

* all Avro ``.avsc`` files are valid JSON (guards against the missing-comma
  regressions that were present in the repo);
* the public API is importable from the top-level package;
* msgspec round-trip (encode -> decode) works for the request ``Event`` and the
  response ``Resp`` across every tagged body type.

Tests are written so that ``msgspec`` being absent surfaces as a clear skip /
error rather than a silent import failure.
"""

import json
from pathlib import Path

import pytest

# msgspec is a hard runtime dependency now; if it is missing the whole point of
# the package is broken, so we let ImportError propagate loudly.
import msgspec

from bt_protocol import (
    Event,
    QueryBody,
    RegisterBody,
    CashBody,
    OrderBody,
    Resp,
    ExperimentBody,
    TradeBody,
    PositionBody,
    AccountBody,
    SnapshotBody,
    Empty,
    ErrMSg,
    Sentinel,
    _ENCODER,
    _DECODER,
    _RespDECODER,
    _RespListDECODER,
)
from bt_protocol._protocol import BodyItem


REPO_ROOT = Path(__file__).resolve().parents[1]
AVRO_DIR = REPO_ROOT / "bt_protocol" / "serialize" / "avro"


# ---------------------------------------------------------------------------
# Avro schema validity
# ---------------------------------------------------------------------------

def _avsc_files():
    return sorted(AVRO_DIR.glob("*.avsc"))


def test_avro_directory_has_schemas():
    assert _avsc_files(), f"no .avsc files under {AVRO_DIR}"


@pytest.mark.parametrize("avsc", _avsc_files(), ids=lambda p: p.name)
def test_avsc_is_valid_json(avsc: Path):
    # Regression test for the missing-comma bugs in ticker.avsc / adjustment.avsc
    parsed = json.loads(avsc.read_text())
    assert parsed["type"] == "record"
    assert isinstance(parsed["fields"], list) and parsed["fields"]


# ---------------------------------------------------------------------------
# Public API importability
# ---------------------------------------------------------------------------

def test_public_api_importable():
    # If any of these are missing the __init__ re-export is broken.
    import bt_protocol
    for name in [
        "Event", "QueryBody", "RegisterBody", "CashBody", "OrderBody",
        "Resp", "ExperimentBody", "TradeBody", "PositionBody", "AccountBody",
        "SnapshotBody", "Empty", "ErrMSg", "Sentinel",
    ]:
        assert hasattr(bt_protocol, name), f"bt_protocol missing {name}"


# ---------------------------------------------------------------------------
# msgspec round-trip: Event (request)
# ---------------------------------------------------------------------------

def test_event_roundtrip_query():
    ev = Event(topic=1, sub_topic=2, body=QueryBody(start_date=20200101, end_date=20201231, sid=[b"A", b"B"]))
    blob = _ENCODER.encode(ev)
    back = _DECODER.decode(blob)
    assert isinstance(back, Event)
    assert back.topic == 1
    assert back.sub_topic == 2
    assert isinstance(back.body, QueryBody)
    assert back.body.start_date == 20200101
    assert back.body.sid == [b"A", b"B"]


def test_event_body_defaults_to_none_and_decodes():
    # Event with no body must still encode/decode (this used to break because
    # the Union did not include None).
    ev = Event(topic=0)
    back = _DECODER.decode(_ENCODER.encode(ev))
    assert back.body is None


def test_event_roundtrip_order_with_default_filler():
    ob = OrderBody(
        sid=b"S", order_id=b"O1", order_type=1, exec_type=2,
        sizer_ratio=0.5, price=10.0, created_dt=20200101,
    )
    ev = Event(topic=5, body=ob)
    back = _DECODER.decode(_ENCODER.encode(ev))
    assert isinstance(back.body, OrderBody)
    # default filler must round-trip
    assert back.body.filler == "default"


def test_event_roundtrip_register_and_cash():
    for body in (
        RegisterBody(client_id=b"C", strategy="alpha", extra_info="{}"),
        CashBody(session=1, cash=10000.0),
    ):
        ev = Event(topic=1, body=body)
        back = _DECODER.decode(_ENCODER.encode(ev))
        assert isinstance(back.body, type(body))


# ---------------------------------------------------------------------------
# msgspec round-trip: Resp (response) — every tagged body
# ---------------------------------------------------------------------------

def _account_body() -> AccountBody:
    return AccountBody(
        datetime=1, portfolio_value=2.0, cash=3.0, pnl=4.0,
        leverage=1.0, margin=0.0, experiment_id=b"\x01" * 16,
    )


def _position_body() -> PositionBody:
    return PositionBody(
        sid=b"S", datetime=1, size=100, available=100, cost_basis=10.0,
        pnl=1.0, created_dt=1, experiment_id=b"\x01" * 16,
    )


def _trade_body() -> TradeBody:
    return TradeBody(
        order_id=b"O", executed_dt=1, executed_size=10,
        executed_price=10.0, comm=0.1, isbuy=True,
    )


@pytest.mark.parametrize("body", [
    ExperimentBody(experiment_id=b"\x01" * 16),
    _trade_body(),
    _position_body(),
    _account_body(),
    SnapshotBody(account=_account_body(), positions=[_position_body()], trades=[_trade_body()]),
    Empty(),
    ErrMSg(error="boom"),
    Sentinel(),
], ids=lambda v: type(v).__name__)
def test_resp_roundtrip_each_body(body: BodyItem):
    resp = Resp(body=body)
    back = _RespDECODER.decode(_ENCODER.encode(resp))
    assert isinstance(back, Resp)
    assert isinstance(back.body, type(body))


def test_resp_list_roundtrip():
    resps = [
        Resp(body=Empty()),
        Resp(body=ErrMSg(error="x")),
        Resp(body=[Empty(), Sentinel()]),  # body as a list of items
    ]
    blob = _ENCODER.encode(resps)
    back = _RespListDECODER.decode(blob)
    assert len(back) == 3
    assert isinstance(back[0].body, Empty)
    assert isinstance(back[1].body, ErrMSg)
    assert isinstance(back[2].body, list)
    assert isinstance(back[2].body[0], Empty)


def test_resp_none_body_roundtrip():
    back = _RespDECODER.decode(_ENCODER.encode(Resp()))
    assert back.body is None