from __future__ import annotations

import json
import os
from pathlib import Path


class CheckpointManager:
    """Atomic JSON checkpoint persistence for long factory runs."""

    def __init__(self, path, context=None):
        self.context = context
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state):
        if self.context is not None:
            state = {**state, "discovery_context": self.context}
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp.open("w") as handle:
            json.dump(state, handle, default=str, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)

    def load(self):
        if not self.path.exists():
            return None
        state = json.loads(self.path.read_text())
        if state.get("discovery_context") != self.context:
            raise ValueError("Checkpoint discovery context mismatch; cannot mix full-data and Development runs")
        return state
