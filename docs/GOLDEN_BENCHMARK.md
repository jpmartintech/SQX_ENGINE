# V1.7 EURUSD H1 golden benchmark

The official V1.7 code commit is
`e7aae6b279ace1dba47ae395fad5156201acb2f1`. Both `v1.7` and the immutable
`benchmark-v1.7-eurusd-h1` tag point to that commit. The benchmark tag must never be
moved. V1.8 changes orchestration and cooperative lifecycle handling, not the
frozen trading semantics.

`benchmarks/v1.7/benchmark.json` was extracted from actual existing configs,
checkpoint and SQLite results. It records code identity, dataset SHA, source and
validation run IDs, seed, engine/grammar, costs, exact split boundaries, counts,
source DB fingerprints and the digest of all sorted canonical hashes. Configs and
validation summary are copied into the benchmark directory. Historical originals
are preserved; `protected_hashes.json` fingerprints the 88 pre-existing artifacts.

```text
Market / timeframe: EURUSD H1
Seed: 1301
Grammar / engine: v1.7 / numba
Dataset SHA256: 7afd8f9af21360ee01deeef78aeba3ff8fcd62c3764c2b6f01244f84ee1c212c
Source run: 169d1631-8254-4b10-b17f-d914c7b21b0d
Validation run: 6ce25038-09fc-47d3-8666-ce4d0f185e8b
Generated unique: 250000
Basic: 22132
Stability: 3610
Plateau: 3608
Cost: 3607
Execution: 2637
Development: 2133
Validation: 605
OOS: 299
Final diversity: 134
Diagnostic portfolio: 10
```

The split remains 100,237 Development bars through 2019-05-22 16:00 UTC,
21,479 Validation bars through 2022-10-31 21:00 UTC and 21,481 OOS bars through
2026-04-14 02:00 UTC. Spread=0.00008, slippage=0.00002, initial capital=10000.

## FAST: normal CI / pytest

```bash
sqx benchmark v1.7 --mode fast
python -m pytest -q
```

A 600-bar fixture and 128-step evolving genetic trajectory were generated using
an archived checkout of the official V1.7 code, before architecture changes.
FAST replays it twice and checks definitions, canonical hashes, metrics and
determinism. It also verifies fixture fingerprints and the byte hashes of frozen
strategy, grammar, feature, generator, predicate, simulator and funnel modules.
Numeric metrics use rtol=1e-10, atol=1e-12; definitions/hashes are exact.

The CLI checks the real dataset SHA. The CI test deliberately disables that one
large local-dataset check, so it runs without private/ignored production data.
FAST **does not claim to recompute 250K funnel/Validation/OOS counts**.

## AUDIT: immutable production evidence

```bash
sqx benchmark v1.7 --mode audit
```

AUDIT opens historical SQLite files read-only. It checks dataset/DB hashes,
integrity, the 250K generation count, reconstructs all canonical definitions,
checks the canonical-set digest, Development/funnel counts, Validation/OOS counts
and TRUE_OOS provenance. It does not generate or re-evaluate strategies. The V1.8
release passed both FAST and AUDIT.

## FULL: explicit expensive replay

```bash
sqx benchmark v1.7 --mode full --output runs/benchmarks/v18_full_manual
```

FULL requires a fresh output directory and explicitly runs 250K with frozen
V1.7 config, then Validation/OOS. It compares canonical-set digest, all funnel
counts, Development/Validation/OOS counts and final diversity. It never writes to
the historical databases. This mode is separate from pytest and factory status;
**it was not run for V1.8**, whose authorized bounded benchmarks were 1K and 10K.

In addition, V1.8 replayed the actual EURUSD H1 1K/10K benchmarks. All 11,000
SQLite strategy definitions, metric values, statuses, quality scores and rejection
reasons matched V1.7 exactly, as did all counters. Measured runtime was 3.626 s
(1K, +0.07%) and 18.324 s (10K, +2.36%) versus the recorded V1.7 local runs.
These are individual local measurements, not statistical speed guarantees.

No new trading criteria, costs fitted from OOS, indicators or portfolio optimizer
were introduced. The historical validation YAML already contained its actual run
ID when this task started; its bytes were preserved and recorded with the golden
metadata rather than resetting it to the older placeholder template.
