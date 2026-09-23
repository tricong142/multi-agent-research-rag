"""LangGraph-compatible callable returning a partial state update, never Command."""
from __future__ import annotations

from typing import Any, Mapping
from .loop_controller import WriterLoopController


class WriterNode:
    def __init__(self, controller: WriterLoopController | None = None):
        self.controller = controller if controller is not None else WriterLoopController()

    def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        warning = state.get("low_confidence_warning", False)
        # Treat malformed warning input conservatively; do not coerce "false".
        output = self.controller.run(state.get("verified_claims", []), state.get("intent", ""),
                                     upstream_warning=warning is not False)
        data = output.model_dump(mode="json")
        return {
            "final_report": data.pop("final_report"),
            "low_confidence_warning": data.pop("low_confidence_warning"),
            "writer_diagnostics": data,
        }

    def run(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return self(state)
