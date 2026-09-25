# Portfolio Factory data contract (downstream, not implemented)

Replay outputs provide `strategy_id`, `canonical_hash`, market, timeframe, direction, family, timestamped sparse net returns, trade ledger, baseline metrics, cost scenario metrics, temporal slices, and behavioral cluster IDs. Portfolio Factory can consume `replay.sqlite` and the CSV summaries without invoking Strategy Factory. No portfolio selection, weighting or optimization is implemented here.
