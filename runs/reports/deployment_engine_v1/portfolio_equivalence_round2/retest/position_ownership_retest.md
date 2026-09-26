# Corrected position ownership retest

The corrected Journal contains 60 complete entry/exit pairs and 7 explicit `SQX_POSITION_CLOSE ... TIME_EXIT` events.

All 60 exits map to the entry ticket and its originating strategy. The 7 strategy-controlled closes are:

| Requester | Ticket | Owner | Result |
|---|---:|---|---|
| `1320ad51f2e8` | 22 | `1320ad51f2e8` | MATCH |
| `108300962057` | 20 | `108300962057` | MATCH |
| `73f2fc6ba7b5` | 18 | `73f2fc6ba7b5` | MATCH |
| `6d1cb5fa1910` | 23 | `6d1cb5fa1910` | MATCH |
| `108300962057` | 36 | `108300962057` | MATCH |
| `21e4d7fab033` | 38 | `21e4d7fab033` | MATCH |
| `108300962057` | 60 | `108300962057` | MATCH |

Cross-strategy closes after the ticket fix: **0**.
Orphan/repeated TIME_EXIT logs after the fix: **0**.
STOP/TARGET exits are broker-managed against the same reconstructed entry tickets; ownership mismatches: **0**.

The historical control changed from the broken run's `1320... TIME_EXIT -> close #23 (owner 6d1...)` to the corrected run's `1320... TIME_EXIT -> close #22 (owner 1320...)`.

Gate: **POSITION_OWNERSHIP = PASS**.
