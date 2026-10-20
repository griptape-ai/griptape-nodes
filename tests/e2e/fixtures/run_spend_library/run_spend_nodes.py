"""Fixture node for the run-spend e2e tests.

``SpendingNode`` reports a fixed cost from inside ``process()``, the way the standard library's
``report_model_usage_sync`` does after a direct provider call. It passes only what the library
passes -- the model, the cost and its own class name -- so every other tag on the report, the run
id among them, is the engine's to add.
"""

from __future__ import annotations

from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.budget_events import ReportUsageRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

COST_MICRO_USD = 400_000


class SpendingNode(ControlNode):
    """Reports one direct model call's cost each time it runs."""

    def process(self) -> None:
        GriptapeNodes.handle_request(
            ReportUsageRequest(
                declared_cost_micro_usd=COST_MICRO_USD,
                provider="openai",
                model="gpt-5-nano",
                activity_type="chat_completion",
                node_type=type(self).__name__,
            )
        )
