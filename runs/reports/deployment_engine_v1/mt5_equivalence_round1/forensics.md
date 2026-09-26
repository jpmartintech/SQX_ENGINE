# Forensics

Strategy `SQX-EURUSD-H1-1320ad51f2e8` canonical hash `1320ad51f2e8f9579ad8543f669926cd6fe2b79923be06d2b7b3d6dd9313e765` produced 5 Python trades and 6 operator-reported MT5 trades. All Python signals in the window are at 2024-01-05T20:00:00+00:00, 2024-01-23T07:00:00+00:00, 2024-01-25T08:00:00+00:00, 2024-01-30T14:00:00+00:00, 2024-01-31T14:00:00+00:00 plus the 2024-01-08 16:00 signal that is blocked in the Python position state by the first trade. The first MT5 trade closes at a near-entry TP, allowing the extra 2024-01-08 trade.

The Python definition explicitly contains `target_atr=4.0`; therefore the near-entry MT5 TP is a translation error, not time_exit reinterpretation. Python uses stop + target + time exit, in that priority. Costs and feed differences are secondary to this logical mismatch.
