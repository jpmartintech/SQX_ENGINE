from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib, json, yaml

@dataclass(frozen=True)
class EngineConfig:
    raw: dict
    source: str = "inline"
    @classmethod
    def from_yaml(cls, path: str | Path):
        p = Path(path); return cls(yaml.safe_load(p.read_text()), str(p))
    @property
    def config_hash(self):
        return hashlib.sha256(json.dumps(self.raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    def get(self, key, default=None):
        value = self.raw
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value: return default
            value = value[part]
        return value

    @property
    def project_root(self):
        if self.source != "inline":
            source = Path(self.source).resolve()
            return source.parent.parent if source.parent.name == "configs" else source.parent
        return Path(__file__).resolve().parents[2]

    def resolve_path(self, key, default=None):
        value = self.get(key, default)
        if value is None:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.project_root / path
