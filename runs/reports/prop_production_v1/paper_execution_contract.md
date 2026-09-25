# Paper execution contract

```text
Market Data → Strategy Signal → Portfolio Risk Manager → Position Size → Order Request → Broker Adapter → Fill → Position State → Account State
```

Every order request carries portfolio ID, strategy ID, market specification, direction, requested R risk, allocated R risk, quantity, stop reference, timestamp and reason. The Risk Manager returns `ACCEPT_FULL`, `ACCEPT_REDUCED` or `REJECT_RISK_LIMIT`. V1 remains realized-only for historical certification; live/paper MTM must be supplied by the next execution layer.
