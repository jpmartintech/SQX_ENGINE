# Multi-asset contract

Production separates Strategy Logic, Market Specification, Execution Specification and Risk Specification. `MarketSpec` reserves tick size/value, point value, contract multiplier, lot step, minimum quantity, currency, margin, session and commission models. Forex currently uses configurable relative sizing. Futures, stocks and crypto require explicit adapters; no new asset discovery or execution was run.
