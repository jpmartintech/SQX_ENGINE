# Search pool policy

The pool is selected before portfolio search using only frozen DEV+VAL metrics. Each primary asset contributes at most 40 definitions, with deterministic top and middle quality tiers separately for LONG and SHORT. Asset identity is retained; cross-asset hashes are never deduplicated. OOS is excluded. The smaller pool is an explicit measured-compute tradeoff, not an OOS reduction.
