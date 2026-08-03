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


# ---------------------------------------------------------------------------
# 1: gRPC generated stub must import cleanly (guards the grpcio>=1.83.0 pin)
# ---------------------------------------------------------------------------

def test_grpc_stub_imports_without_runtime_error():
    # If grpcio < 1.83.0 is installed, the generated _pb2_grpc.py raises
    # RuntimeError at import time. This test is the CI gate for F-2/D-1.
    import bt_protocol.serialize.pb.bt_protocol_service_pb2_grpc as grpc_mod  # noqa: F401
    assert hasattr(grpc_mod, "btDataFeedStub")


# ---------------------------------------------------------------------------
# 2: vtorder.order_id must have a single-column UniqueConstraint (C-1)
# ---------------------------------------------------------------------------

def test_vtorder_has_single_column_unique_on_order_id():
    from bt_protocol.schema.trade import vtOrder
    table = vtOrder.__table__
    # Collect all UniqueConstraints where the only column is "order_id".
    single_col_uqs = [
        c for c in table.constraints
        if type(c).__name__ == "UniqueConstraint"
        and len(c.columns) == 1
        and c.columns[0].name == "order_id"
    ]
    assert single_col_uqs, (
        "vtorder.order_id must have a single-column UniqueConstraint so that "
        "OrderBit.order_id can reference it as a foreign key (PostgreSQL rule)."
    )


# ---------------------------------------------------------------------------
# 3: all relationships must forbid implicit lazy loading (C-2)
# ---------------------------------------------------------------------------

def test_all_relationships_use_raise_or_explicit_lazy():
    # Allowed strategies: raise (force explicit eager load) or explicit eager
    # strategies. The default "select" is forbidden because it triggers sync IO
    # in async contexts (greenlet leak) and N+1 queries.
    allowed = {"raise", "selectin", "joined", "noload", "subquery", "write_only"}
    from bt_protocol.schema import asset, trade

    offenders = []
    for mod in (asset, trade):
        for mapper in mod.Base.registry.mappers:
            for rel in mapper.relationships:
                # SQLAlchemy evaluates `lazy` into a strategy; the raw value is
                # kept on rel.argument or rel.lazy. We check the configured lazy.
                if rel.lazy not in allowed:
                    offenders.append(f"{mapper.class_.__name__}.{rel.key} lazy={rel.lazy!r}")
    assert not offenders, f"relationships with forbidden lazy strategy: {offenders}"


# ---------------------------------------------------------------------------
# 4: alembic.ini must not contain hardcoded credentials (F-1)
# ---------------------------------------------------------------------------

def test_alembic_ini_has_no_hardcoded_credentials():
    import configparser
    ini_path = REPO_ROOT / "alembic.ini"
    parser = configparser.ConfigParser()
    parser.read(ini_path)
    url = parser.get("alembic", "sqlalchemy.url", fallback="")
    # Empty or placeholder only; no user:pass@host allowed.
    assert url.strip() == "", (
        "alembic.ini sqlalchemy.url must be empty; DATABASE_URL must be injected."
    )
    assert "postgres" not in url.lower() or url.strip() == ""


# ---------------------------------------------------------------------------
# 5: codec performance regression baseline (no per-message codec allocation)
# ---------------------------------------------------------------------------

def test_encode_decode_throughput_baseline():
    # A very loose lower bound to catch gross regressions (e.g. accidentally
    # constructing an Encoder per call). Numbers are conservative to stay
    # stable across machines; the goal is to flag order-of-magnitude drops.
    import time
    ev = Event(topic=1, sub_topic=2, body=QueryBody(start_date=20200101, end_date=20201231, sid=[b"A", b"B"]))
    n = 20000
    t0 = time.perf_counter()
    for _ in range(n):
        blob = _ENCODER.encode(ev)
        _DECODER.decode(blob)
    elapsed = time.perf_counter() - t0
    rps = n / elapsed
    # Should easily exceed 50k round-trips/s on any modern machine; we assert
    # a conservative 5k/s floor to avoid CI flakiness while still catching
    # per-message codec construction (~100x slower).
    assert rps > 5000, f"encode+decode throughput too low: {rps:.0f} round-trips/s"


# ---------------------------------------------------------------------------
# 6: serialize() return annotation must match actual Resp return (FN-1)
# ---------------------------------------------------------------------------

def test_serialize_return_annotation_is_resp():
    import inspect
    from bt_protocol.schema.trade import Experiment, OrderBit, vtPosition, vtAccount
    from bt_protocol import Resp
    for cls in (Experiment, OrderBit, vtPosition, vtAccount):
        sig = inspect.signature(cls.serialize)
        assert sig.return_annotation is Resp, (
            f"{cls.__name__}.serialize return annotation must be Resp, "
            f"got {sig.return_annotation!r}"
        )


# ---------------------------------------------------------------------------
# (extra): __version__ is exposed (D-5)
# ---------------------------------------------------------------------------

def test_package_exposes_version():
    # __version__ must exist as a non-empty string. In a dev checkout that has
    # not been `poetry install`-ed the value falls back to "0.0.0+unknown",
    # which is acceptable for this guard (the real version check belongs to
    # the packaging/CI stage).
    import bt_protocol
    assert hasattr(bt_protocol, "__version__")
    assert isinstance(bt_protocol.__version__, str)
    assert bt_protocol.__version__
