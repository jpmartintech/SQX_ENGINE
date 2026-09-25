# Portfolio Factory V1.0

This is a downstream selector for immutable Strategy Library identities. It never generates or mutates strategies. The pilot is labelled `RETROSPECTIVE_PORTFOLIO_RESEARCH`: the 2024–2026 OOS period was already observed by Strategy Factory and Replay.

The common clock is the union of realized trade-exit timestamps in UTC. PnL is realized-only; mark-to-market and floating PnL are not invented. Correlations are computed on aligned realized-return vectors. `EQUAL_WEIGHT` and `EQUAL_RISK` are implemented. Search controls are explicit and reproducible.
