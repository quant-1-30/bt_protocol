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
    ErrMsg,
    Sentinel,
    encode_event,
    decode_event,
    encode_resp,
    decode_resp,
    encode_resp_list,
    decode_resp_list,
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
    blob = encode_event(ev)
    back = decode_event(blob)
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
    back = decode_event(encode_event(ev))
    assert back.body is None


def test_event_roundtrip_order_with_default_filler():
    ob = OrderBody(
        sid=b"S", order_id=b"O1", order_type=1, exec_type=2,
        sizer_ratio=0.5, price=10.0, created_dt=20200101,
    )
    ev = Event(topic=5, body=ob)
    back = decode_event(encode_event(ev))
    assert isinstance(back.body, OrderBody)
    # default filler must round-trip
    assert back.body.filler == "default"


def test_event_roundtrip_register_and_cash():
    for body in (
        RegisterBody(client_id=b"C", strategy="alpha", extra_info="{}"),
        CashBody(session=1, cash=10000.0),
    ):
        ev = Event(topic=1, body=body)
        back = decode_event(encode_event(ev))
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
    back = decode_resp(encode_resp(resp))
    assert isinstance(back, Resp)
    assert isinstance(back.body, type(body))


def test_resp_list_roundtrip():
    resps = [
        Resp(body=Empty()),
        Resp(body=ErrMSg(error="x")),
        Resp(body=[Empty(), Sentinel()]),  # body as a list of items
    ]
    blob = encode_resp_list(resps)
    back = decode_resp_list(blob)
    assert len(back) == 3
    assert isinstance(back[0].body, Empty)
    assert isinstance(back[1].body, ErrMSg)
    assert isinstance(back[2].body, list)
    assert isinstance(back[2].body[0], Empty)


def test_resp_none_body_roundtrip():
    back = decode_resp(encode_resp(Resp()))
    assert back.body is None


# ---------------------------------------------------------------------------
# 1: gRPC generated stub must import cleanly (guards the grpcio>=1.83.0 pin)
# ---------------------------------------------------------------------------

def test_grpc_stub_imports_without_runtime_error():
    # If grpcio < GRPC_GENERATED_VERSION is installed, the generated _pb2_grpc.py
    # raises RuntimeError at import time. Also assert that pyproject.toml's
    # declared grpcio lower bound is >= GRPC_GENERATED_VERSION so consumers
    # never resolve an older incompatible runtime.
    import re
    import bt_protocol.serialize.pb.bt_protocol_service_pb2_grpc as grpc_mod
    assert hasattr(grpc_mod, "btDataFeedStub")

    gen_ver = tuple(int(x) for x in grpc_mod.GRPC_GENERATED_VERSION.split("."))
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^grpcio\s*=\s*"?>=([0-9]+\.[0-9]+\.[0-9]+)', pyproject_text, re.M)
    assert m, "pyproject.toml must declare a >=X.Y.Z lower bound for grpcio"
    declared_floor = tuple(int(x) for x in m.group(1).split("."))
    assert declared_floor >= gen_ver, (
        f"pyproject.toml grpcio floor {m.group(1)} is lower than "
        f"GRPC_GENERATED_VERSION {grpc_mod.GRPC_GENERATED_VERSION} in _pb2_grpc.py"
    )


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
        blob = encode_event(ev)
        decode_event(blob)
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


# ---------------------------------------------------------------------------
# 7: Experiment.account relationship must be a list (one-to-many)
# ---------------------------------------------------------------------------

def test_experiment_account_relationship_is_collection():
    from bt_protocol.schema.trade import Experiment
    from sqlalchemy.inspection import inspect as sa_inspect
    mapper = sa_inspect(Experiment)
    rel = mapper.relationships["account"]
    assert rel.uselist is True, (
        "Experiment.account must be a one-to-many collection (uselist=True) "
        "because vtAccount is keyed by (datetime, experiment_id)."
    )


# ---------------------------------------------------------------------------
# 8: Foreign keys to experiment.experiment_id must have left-prefix indexes
# ---------------------------------------------------------------------------

def test_experiment_id_foreign_keys_are_indexed():
    from bt_protocol.schema.trade import vtOrder, vtPosition, vtAccount
    for model in (vtOrder, vtPosition, vtAccount):
        table = model.__table__
        has_leading_index = any(
            len(idx.columns) >= 1 and list(idx.columns)[0].name == "experiment_id"
            for idx in table.indexes
        )
        assert has_leading_index, (
            f"{table.name}.experiment_id must have an index with experiment_id "
            "as the leading column to avoid full-table scans on CASCADE deletes."
        )


# ---------------------------------------------------------------------------
# 9: Alembic migration chain integrity & regression guards
# ---------------------------------------------------------------------------

def test_alembic_script_directory_has_expected_branches():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = set(script.get_heads())
    # Three branches: feed (616545e13eb4), asset (79a49578303d), trade (b8c9d0e1f2a3)
    assert {"616545e13eb4", "79a49578303d", "b8c9d0e1f2a3"}.issubset(heads)
    # Verify branch labels resolve cleanly
    assert script.get_revision("feed@head").revision == "616545e13eb4"
    assert script.get_revision("asset@head").revision == "79a49578303d"
    assert script.get_revision("trade@head").revision == "b8c9d0e1f2a3"


def test_migration_28cdc82de517_does_not_corrupt_asset_name():
    mig_path = (
        REPO_ROOT
        / "alembic"
        / "versions"
        / "28cdc82de517_change_sid_and_name_from_str_to_bytes.py"
    )
    src = mig_path.read_text()
    assert 'alter_column("asset", "name"' in src
    assert "postgresql_using='name::bytea'" in src
    assert "'assets'" not in src


# ---------------------------------------------------------------------------
# 10: asset.Base column cache & no stray use_existing_column
# ---------------------------------------------------------------------------

def test_asset_models_to_dict_cache_and_clean_columns():
    from bt_protocol.schema.asset import Asset, Adjustment, Rightment
    a = Asset(sid=b"000001.SZ", name=b"PingAn", first_trading=19910403)
    d = a.serialize()
    assert d["sid"] == b"000001.SZ"
    assert "id" not in d
    assert Asset.__columns__, "Asset.__columns__ cache should be populated"

    adj = Adjustment(
        sid=b"000001.SZ", report_date=20200101, register_date=20200102,
        ex_date=20200103, bonus_share=0.0, transfer=0.0, bonus=1.0,
    )
    assert adj.to_dict()["bonus"] == 1.0
    rgt = Rightment(
        sid=b"000001.SZ", report_date=20200101, register_date=20200102,
        ex_date=20200103, price=5.0, ratio=0.2,
    )
    assert rgt.to_dict()["price"] == 5.0


# ---------------------------------------------------------------------------
# 11: PositionBody realized_pnl roundtrip & vtPosition.serialize
# ---------------------------------------------------------------------------

def test_vtposition_serialize_includes_realized_pnl():
    import uuid
    from bt_protocol.schema.trade import vtPosition, Experiment, vtAccount
    uid = uuid.uuid4()
    pos = vtPosition(
        sid=b"000001.SZ", datetime=20260101, created_dt=20260101,
        size=100, available=100, cost_basis=10.0, pnl=50.0,
        realized_pnl=125.5, experiment_id=uid,
    )
    resp = pos.serialize()
    back = decode_resp(encode_resp(resp))
    assert isinstance(back.body, PositionBody)
    assert back.body.realized_pnl == pytest.approx(125.5)
    assert back.body.pnl == pytest.approx(50.0)
    # pnl_ratio = (50.0 + 125.5) / (100 * 10.0) = 0.1755
    assert back.body.pnl_ratio == pytest.approx(0.1755)

    # Unflushed ORM instances (experiment_id=None) must not raise AttributeError
    unflushed_exp = Experiment(strategy="s", extra_info="{}")
    assert unflushed_exp.serialize().body.experiment_id == b""
    unflushed_acct = vtAccount(
        datetime=20260101, portfolio_value=1.0, cash=1.0, pnl=0.0,
        leverage=1.0, margin=0.0,
    )
    assert unflushed_acct.serialize().body.experiment_id == b""
    assert ErrMsg is ErrMSg


# ---------------------------------------------------------------------------
# 12: DuckDB template close > 0 filter placement guard
# ---------------------------------------------------------------------------

def test_duckdb_templates_close_filter_placement():
    from bt_protocol.template.duckdb_template import (
        _VALID_CLOSE_FILTER,
        CLOSE_TEMPLATE,
        DAILY_TEMPLATE,
        TICK_TEMPLATE,
    )
    assert _VALID_CLOSE_FILTER not in TICK_TEMPLATE
    assert _VALID_CLOSE_FILTER in CLOSE_TEMPLATE
    assert _VALID_CLOSE_FILTER in DAILY_TEMPLATE


def test_user_and_experiment_single_column_id_primary_key():
    from bt_protocol.schema.trade import Experiment, User
    assert [c.name for c in User.__table__.primary_key.columns] == ["id"]
    assert [c.name for c in Experiment.__table__.primary_key.columns] == ["id"]

