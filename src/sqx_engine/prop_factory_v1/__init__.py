"""Phase A infrastructure for PROP_V1 short-horizon metrics."""

from .lineage import (
    GENERAL_LINEAGE,
    PROP_FACTORY_VERSION,
    PROP_LINEAGE_SCHEMA_VERSION,
    PROP_METRICS_VERSION,
    StrategyLineageMetadata,
    resolve_lineage,
)
from .metrics import ShortHorizonOpportunityVector, compute_prop_metrics, select_validation_sample

__all__ = [
    "GENERAL_LINEAGE", "PROP_FACTORY_VERSION", "PROP_LINEAGE_SCHEMA_VERSION", "PROP_METRICS_VERSION",
    "StrategyLineageMetadata", "resolve_lineage", "ShortHorizonOpportunityVector",
    "compute_prop_metrics", "select_validation_sample",
]
