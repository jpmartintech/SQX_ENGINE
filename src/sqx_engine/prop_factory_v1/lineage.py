"""Versioned, backward-compatible factory lineage metadata.

Lineage is sidecar metadata. It is deliberately excluded from canonical
StrategyDefinition serialization and therefore cannot change existing IDs.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Mapping, Any

PROP_FACTORY_VERSION = "PROP_FACTORY_V1_PHASE_A"
PROP_METRICS_VERSION = "PROP_METRICS_V1"
PROP_LINEAGE_SCHEMA_VERSION = "PROP_LINEAGE_SCHEMA_V1"
GENERAL_LINEAGE = "GENERAL"


@dataclass(frozen=True)
class StrategyLineageMetadata:
    factory_lineage: str = GENERAL_LINEAGE
    factory_version: str = "GENERAL_UNKNOWN"
    grammar_version: str = "GENERAL_UNKNOWN"
    fitness_version: str = "NOT_IMPLEMENTED"
    metrics_version: str = PROP_METRICS_VERSION
    economic_spec_version: str = "UNIVERSAL_ECONOMICS_V1"
    generation_campaign_id: str = "UNKNOWN"
    generation_seed: int | None = None
    data_provenance_id: str = "UNKNOWN"
    execution_profile_id: str = "UNKNOWN"
    created_at: str = ""
    canonical_strategy_id: str = ""
    lineage_schema_version: str = PROP_LINEAGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def prop_v1(cls, canonical_strategy_id: str, **kwargs: Any) -> "StrategyLineageMetadata":
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        values = dict(factory_lineage="PROP_V1", factory_version=PROP_FACTORY_VERSION,
                      grammar_version="NOT_IMPLEMENTED", fitness_version="NOT_IMPLEMENTED",
                      metrics_version=PROP_METRICS_VERSION, generation_campaign_id="UNSPECIFIED",
                      data_provenance_id="UNSPECIFIED", execution_profile_id="UNSPECIFIED",
                      created_at=now, canonical_strategy_id=canonical_strategy_id)
        values.update(kwargs)
        return cls(**values)


def resolve_lineage(record: Mapping[str, Any] | None, canonical_strategy_id: str = "") -> StrategyLineageMetadata:
    """Resolve old records without mutation; absent fields deterministically mean GENERAL."""
    record = dict(record or {})
    allowed = set(StrategyLineageMetadata.__dataclass_fields__)
    values = {k: record[k] for k in allowed if k in record and record[k] is not None}
    values.setdefault("factory_lineage", GENERAL_LINEAGE)
    values.setdefault("canonical_strategy_id", canonical_strategy_id)
    values.setdefault("metrics_version", PROP_METRICS_VERSION)
    values.setdefault("lineage_schema_version", PROP_LINEAGE_SCHEMA_VERSION)
    return StrategyLineageMetadata(**values)
