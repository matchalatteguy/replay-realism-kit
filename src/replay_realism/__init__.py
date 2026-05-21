"""Offline execution-realism primitives for deterministic market replay."""

from replay_realism.assumptions import ExecutionAssumptionProfile, SafetyLevel
from replay_realism.events import BookEvent, DecisionEvent, ReplayEvent, TradeEvent, load_events_csv
from replay_realism.fees import FeeModel
from replay_realism.fills import (
    BookSnapshot,
    FillPolicy,
    FillRequest,
    FillResult,
    OrderSide,
    OrderType,
    simulate_maker_fill,
    simulate_taker_fill,
)
from replay_realism.gates import GateSeverity, QualityGateResult, validate_replay_report
from replay_realism.latency import FixedLatencyModel, apply_latency
from replay_realism.markout import MarkoutResult, compute_markout, future_midpoint
from replay_realism.reports import ReplayReport, write_json_report, write_markdown_report

__all__ = [
    "BookEvent",
    "BookSnapshot",
    "DecisionEvent",
    "ExecutionAssumptionProfile",
    "FeeModel",
    "FillPolicy",
    "FillRequest",
    "FillResult",
    "FixedLatencyModel",
    "GateSeverity",
    "MarkoutResult",
    "OrderSide",
    "OrderType",
    "QualityGateResult",
    "ReplayEvent",
    "ReplayReport",
    "SafetyLevel",
    "TradeEvent",
    "apply_latency",
    "compute_markout",
    "future_midpoint",
    "load_events_csv",
    "simulate_maker_fill",
    "simulate_taker_fill",
    "validate_replay_report",
    "write_json_report",
    "write_markdown_report",
]
