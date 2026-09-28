# SQX Strategy Economic Contract V1

This is the single executable accounting contract used by candidate validation
and intended for later Library/Portfolio replay.

- Initial equity is 1.0 normalized units.
- Each entry requests `current_equity * 0.01` risk capital.
- Total open intended risk for one strategy may not exceed
  `current_equity * 0.01` at the entry decision. Existing open risk is
  reserved first; a new entry receives only remaining capacity. If no
  capacity remains, the entry is skipped. If capacity is partial, it is
  deterministically resized.
- Entry and exit timestamps are causal evaluator timestamps. Exits are
  processed before entries at equal timestamps; same-timestamp entries are
  resolved immediately after sizing. Events are stably ordered.
- Realized PnL is `allocated_risk * evaluator_net_R`. It is never clamped.
  Losses below -1R therefore remain possible and are recorded as overshoot.
- Floating PnL is marked from the entry/exit prices using the last available
  closed market bar at each event or market timestamp. Cash plus floating PnL
  is equity; wins and losses compound through current equity sizing.
- Fees and slippage are already included in the frozen evaluator net-R stream.
  No funding is fabricated because no valid causal funding series is present.
- `equity <= 0` is RUIN. New entries stop immediately after ruin; existing
  positions are only closed deterministically for accounting.
- MaxDD is measured from the running peak of marked equity. Minimum equity,
  intended risk, realized loss, overshoot loss, skipped entries, and resized
  entries are retained.

The 1% value is an intended open-heat cap, not a guarantee that realized loss
cannot exceed 1%: gaps, slippage, and evaluator R overshoot remain honest.
