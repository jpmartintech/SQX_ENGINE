# SQX CRYPTO FACTORY V2 — FINAL STATUS

STARTING COMMIT: `5725c4d`
FINAL DECISION: `CRYPTO_V2_OOS_FAILED`

## Experimental protocol

- DEV / VAL / OOS / LOCKBOX: 60% / 15% / 15% / 10% by elapsed time.
- Six equal-duration internal DEV windows per admitted dataset.
- Frozen grammar: v1.7 PRICE_ONLY; causal next-bar execution.
- Search: 10,000 Genetic candidates per admitted M15 asset; 90,000 total.
- Fitness: predeclared multi-window expectancy, positive-window ratio,
  activity support, and worst-window penalty.
- No volume/funding signal, portfolio optimization, leverage, or real orders.

## Datasets

Metadata intake found 18 crypto USDT files: 9 M15 and 9 companion 1H files.
The 9 M15 files were admitted; the 1H files were explicitly deferred from this
bounded M15 experiment. The short EURUSD test file was rejected. Admitted
assets: ADA, AVAX, BNB, BTC, DOGE, ETH, LINK, SOL, TRX. All admitted files
have 0 duplicate timestamps, monotonic UTC timestamps, valid positive
OHLC, nonnegative volume, and at least four years of history. Source is
`/mnt/c/Users/xaume/Documents/DATOS SQX 15 MINS/crypto/`; venue/product is
probable Binance-derived USDT market, not independently verified. Missing-grid
intervals were retained as gaps; no price filling was used.

Coverage ranges: BTC 2017-08-17 → 2026-05-02; ETH 2017-08-17 → 2026-06-04;
BNB 2017-11-06 → 2026-06-04; ADA 2018-04-17 → 2026-06-04; TRX 2018-06-11 →
2026-06-04; LINK 2019-01-16 → 2026-06-04; DOGE 2019-07-05 → 2026-06-04;
AVAX 2020-09-22 → 2026-06-04; SOL 2020-08-11 → 2026-06-04.

The per-file SHA256 values are in `data_inventory.json` and the canonical
hashes are in `temporal_splits.json` / `canonical_data_manifest.json`.

## Factory results

- Generated: 90,000; unique: 51,786; DEV eligible: 10,936.
- DEV eligible by asset: ADA 24, AVAX 1,011, BNB 2,500, BTC 405, DOGE 2,031,
  ETH 176, LINK 3,101, SOL 1,457, TRX 231.
- VAL evaluated: 10,936; VAL positive: 6,716; median VAL PF 1.022;
  median VAL expectancy +0.012R.
- Frozen VAL library: 100 records; deterministic top-by-VAL-expectancy,
  equal-risk baseline, no OOS selection.

## Firewall and OOS

Access ledger counts: DEV 9, VAL 9, OOS 9, LOCKBOX 0; unauthorized accesses
0. OOS was opened once after Strategy Factory, library, portfolio baseline,
risk, data, and boundary freezes. The OOS sample contained 20 selected
strategies: median PF 0.522, median expectancy -0.301R, median MaxDD 68.8%,
and 5 positive strategies. The predeclared positive-fraction criterion was
not met. The normalized unit-capital aggregate return was -66.8%.

LOCKBOX was not opened. This is a valid terminal failure, not a data blocker:
the dataset gate passed and the frozen system failed its OOS exam.

## Limitations

This bounded V2 run searched M15 cells only; H1 was not added to the first
experiment to avoid an unplanned multiple-testing expansion. Funding was not
fabricated. The source is signal-market history, not Hyperliquid execution
history. No V2 strategy or portfolio result may be promoted to production.

## Terminal decision

`CRYPTO_V2_OOS_FAILED`
