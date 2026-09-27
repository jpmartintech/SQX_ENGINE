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
from .fitness import (
    CHEAP_OBJECTIVES,
    FULL_OBJECTIVES,
    OBJECTIVE_DIRECTIONS,
    PROP_FITNESS_SCHEMA_VERSION,
    PROP_FITNESS_VERSION,
    PropFitnessVector,
    dominates,
    evaluate_cheap,
    evaluate_full,
    fitness_vector,
    normalize_objectives,
    pareto_rank,
)

__all__ = [
    "GENERAL_LINEAGE", "PROP_FACTORY_VERSION", "PROP_LINEAGE_SCHEMA_VERSION", "PROP_METRICS_VERSION",
    "StrategyLineageMetadata", "resolve_lineage", "ShortHorizonOpportunityVector",
    "compute_prop_metrics", "select_validation_sample",
    "CHEAP_OBJECTIVES", "FULL_OBJECTIVES", "OBJECTIVE_DIRECTIONS",
    "PROP_FITNESS_VERSION", "PROP_FITNESS_SCHEMA_VERSION", "PropFitnessVector",
    "evaluate_cheap", "evaluate_full", "dominates", "normalize_objectives",
    "pareto_rank", "fitness_vector",
]
