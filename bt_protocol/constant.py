#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""Topic constants used on the wire (msgpack Event.topic / Event.sub_topic).

These are intentionally ``IntEnum`` so that:

* they are plain ints on the wire (msgspec / protobuf int32 interop),
* they support iteration, ``name``/``value`` introspection, and membership
  tests (``RpcTopic.Adjustment in RpcTopic``),
* static checkers can catch typos that a bare ``class`` namespace would
  silently allow.
"""

from enum import IntEnum


class RpcTopic(IntEnum):
    Instrument = 0
    Tick = 1
    Daily = 2
    Close = 3
    Adjustment = 4
    Rightment = 5


class FactorTopic(IntEnum):
    Raw = 0
    Qfq = 1  # forward-adjusted (前复权)
    Hfq = 2  # backward-adjusted (后复权)


__all__ = ["RpcTopic", "FactorTopic"]