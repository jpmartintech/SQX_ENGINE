# SQX MULTI-COIN STRATEGY FACTORY V1 — FINAL STATUS

Starting commit: `a1a4da7`
Current assembly commit: `0d6312af86950d69f23bc5879524cdd0362d213d`

## Decision
Raw material: **MULTI_COIN_RAW_MATERIAL_STRONG**

OOS for new assets is burned research only. No LOCKBOX was accessed.

## Per-asset results

### ADA
Random unique: 50000; Genetic unique: 200000; DEV candidates: 5
Library: 2 (0 LONG / 2 SHORT)
OOS positive: 0.000; median return: -0.06476389025778628; median PF: 0.0
Rejected-valid OOS positive: 0.008

### AVAX
Random unique: 50000; Genetic unique: 200000; DEV candidates: 55751
Library: 46424 (1442 LONG / 44982 SHORT)
OOS positive: 0.883; median return: 0.3557792949351426; median PF: 1.083512405758615
Rejected-valid OOS positive: 0.375

### BNB
Random unique: 50000; Genetic unique: 200000; DEV candidates: 21288
Library: 10978 (1727 LONG / 9251 SHORT)
OOS positive: 0.475; median return: -0.01000103822123094; median PF: 0.996399702709093
Rejected-valid OOS positive: 0.447

### DOGE
Random unique: 50000; Genetic unique: 200000; DEV candidates: 0
Library: 0 (0 LONG / 0 SHORT)
OOS positive: 0.000; median return: None; median PF: None
Rejected-valid OOS positive: 0.062

### ETH
Random unique: 50000; Genetic unique: 200000; DEV candidates: 24850
Library: 7837 (1839 LONG / 5998 SHORT)
OOS positive: 0.692; median return: 0.1060734760962585; median PF: 1.0494794182124179
Rejected-valid OOS positive: 0.534

### LINK
Random unique: 50000; Genetic unique: 200000; DEV candidates: 12156
Library: 6651 (1755 LONG / 4896 SHORT)
OOS positive: 0.627; median return: 0.06446689143419482; median PF: 1.0373424368906219
Rejected-valid OOS positive: 0.410

### SOL
Random unique: 50000; Genetic unique: 200000; DEV candidates: 48505
Library: 23847 (2491 LONG / 21356 SHORT)
OOS positive: 0.783; median return: 0.21307213639051126; median PF: 1.0601683509878919
Rejected-valid OOS positive: 0.405

### TRX
Random unique: 50000; Genetic unique: 200000; DEV candidates: 0
Library: 0 (0 LONG / 0 SHORT)
OOS positive: 0.000; median return: None; median PF: None
Rejected-valid OOS positive: 0.001

## Firewall

New asset VAL/OOS were accessed only after their respective freezes. All LOCKBOX counts are zero. BTC OOS is previously burned; BTC LOCKBOX remains protected.

## Next product action

Build the multi-coin Portfolio Factory on the frozen per-asset libraries, with cross-asset event-aligned behavioral fingerprints computed before optimization.
