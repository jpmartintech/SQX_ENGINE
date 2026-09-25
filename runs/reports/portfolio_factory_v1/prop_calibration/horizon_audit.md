# Horizon audit — RETROSPECTIVE_PROP_RESEARCH

The original 30-day horizon comes directly from `FtmoConfig.max_days=30` in `src/sqx_engine/portfolio_factory/ftmo.py` and the default `FtmoSimulator` call used by `scripts/portfolio_factory_pilot.py`. It was a local pilot assumption, counted observed event-days, and was not sourced from a verified prop-firm rule.

The simulator now supports `max_calendar_days=N` and `max_calendar_days=null`. A finite calendar horizon can end in `TIMEOUT`; an unlimited run ends in `DATA_END` if the historical observations finish first. Legacy `max_days=30` remains available for compatibility and is not silently rewritten.
