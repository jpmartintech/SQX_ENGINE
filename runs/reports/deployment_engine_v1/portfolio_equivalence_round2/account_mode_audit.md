# Account mode audit

The HTML and Journal show independent same-symbol position tickets and independent closes for simultaneous EURUSD positions (for example tickets #14/#15 and #38/#39). This is consistent with HEDGING mode, not a single netted symbol position. The EA source did not log `ACCOUNT_MARGIN_MODE`, so the exact enum value is not directly recorded; operational behavior proves independent-ticket/hedging semantics for this run.

Gate: PARTIAL pending explicit runtime `ACCOUNT_MARGIN_MODE` instrumentation; ownership still fails because the close call was symbol-scoped even in the compatible account mode.
