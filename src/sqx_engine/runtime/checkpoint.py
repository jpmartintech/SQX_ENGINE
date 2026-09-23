from __future__ import annotations

import json
import os
from pathlib import Path


class CheckpointManager:
    """Atomic JSON checkpoint persistence for long factory runs."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state):
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp.open("w") as handle:
            json.dump(state, handle, default=str, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)

    def load(self):
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text())
