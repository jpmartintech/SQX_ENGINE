# Multi-asset compatibility audit — AUDIT_ONLY

|Area|Status|Finding|
|---|---|---|
|market/timeframe identity|READY|First-class in StrategyDefinition/library identity|
|pip/tick scale|CONFIG_ONLY|Execution profiles carry pip/tick scale; new instruments need reviewed profiles|
|point value/contract size|UNRESOLVED|Not represented as a general futures contract model|
|quote currency/conversion|CODE_CHANGE_REQUIRED|No general multi-currency accounting layer|
|sessions/24-7 calendars|CODE_CHANGE_REQUIRED|Current temporal/data handling is bar-series based|
|commission/funding|CODE_CHANGE_REQUIRED|Frozen model has no general commission/funding/rollover abstraction|
|futures expiry/rollover|UNRESOLVED|No continuous-contract policy|
|timezone|CONFIG_ONLY|Dataset provenance preserves timestamp convention; per-market audit required|
|crypto|CODE_CHANGE_REQUIRED|No production-ready crypto execution model|
