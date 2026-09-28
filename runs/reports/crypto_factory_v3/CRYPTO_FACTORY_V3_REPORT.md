# SQX CRYPTO FACTORY V3 — FINAL STATUS

STARTING COMMIT: `53efba3`  
PRE-VALIDATION COMMIT: `4882c3e`  
FINAL COMMIT: `d8efed1`  
DECISION: `CRYPTO_V3_PORTFOLIO_NOT_ROBUST`

## Hypothesis

The existing frozen PRICE_ONLY factory might generalize if noisy extreme VAL
winners were replaced by uncertainty-aware robust selection and portfolio
economics were evaluated with true chronological concurrent replay.

## Evidence status

V2 DEV, VAL, and OOS were used as burned design evidence. The V2 LOCKBOX was
identified as the first protected layer but was never accessed. No additional
compatible protected M15 layer was identified from metadata-only inspection.

## Selection

- DEV-eligible records: 10,936.
- Unique asset/hash definitions: 7,017.
- Robust region: 400.
- Final V3 library: 12 strategies.
- Selection inputs: burned DEV and former VAL only.
- Policy: uncertainty/concentration-aware score, minimum active windows and
  trade support, deterministic caps of 4 per asset and 8 per direction.

The library contained SOL, BTC, LINK, AVAX, and TRX, with 4 LONG and 8 SHORT
strategies. No protected strategy performance entered selection.

## True concurrent portfolio result on burned data

The engine processed chronological overlapping events, floating equity,
realized PnL, same-timestamp exit-before-entry ordering, risk budgets, and
drawdown. Golden tests passed.

| Segment | Return | PF | Expectancy | MaxDD | Minimum equity | Valid |
|---|---:|---:|---:|---:|---:|---|
| DEV | -273.88 | 0.174 | +0.274R | -106.9% | -289.74 | No |
| VAL | +104,425.16 | 4.950 | +0.137R | -124.4% | -157,875.63 | No |
| OOS | +183.09 | 2.150 | +0.012R | -109.1% | -0.184 | No |

All burned segments produced negative-equity paths under the true concurrent
engine. The economic-validity gate therefore failed before protected
validation.

## Protected validation

Protected strategy accesses: `0`  
LOCKBOX access count before: `0`  
LOCKBOX access count after: `0`  
Final holdout: Not opened

The V2 LOCKBOX remains untouched.

## Conclusion

Uncertainty-aware selection did not earn promotion because the true concurrent
portfolio was economically invalid on burned data. This is stronger evidence
against the current portfolio/risk construction than the prior V2 arithmetic
mean result. No claim is made about protected performance because no protected
data were accessed.
