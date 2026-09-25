# Position sizing semantics

`POSITION_SIZING_SEMANTICS = FIXED_ONE_PRICE_UNIT`.

The evaluator does not size quantity from account capital or stop distance. The $10,000 value only normalizes return and initializes the bookkeeping balance. Therefore original evaluator PnL cannot be interpreted as a 1% account-risk trade without downstream reconstruction.
