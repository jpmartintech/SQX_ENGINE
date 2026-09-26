"""Conservative MT5 Journal ingestion helper.

The MT5 Journal format varies slightly by terminal/build. This parser keeps
only explicit SQX events and market deal lines, never invents a position
relationship. It emits UNRESOLVED fields when the journal does not provide a
complete entry/exit chain, which is preferable to silently matching tickets.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

EVENT = re.compile(r"(?P<ts>\d{4}[.]\d{2}[.]\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)")
STRATEGY = re.compile(r"strategy(?:=|\s+)(?P<id>SQX-[A-Za-z0-9-]+)")
ORDER = re.compile(r"(?:order|deal|position)[ =#:]*(?P<num>\d+)", re.I)

FIELDS = ["record_type", "timestamp", "strategy_id", "order_id", "deal_id",
          "position_id", "direction", "volume", "price", "stop", "target",
          "exit_reason", "message", "source"]


def parse(path: Path):
    rows = []
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    for line in raw.decode(encoding, errors="replace").splitlines():
        if "SQX_" not in line and not re.search(r"market (buy|sell)", line, re.I):
            continue
        ts = EVENT.search(line)
        sid = STRATEGY.search(line)
        nums = ORDER.findall(line)
        direction = "BUY" if re.search(r"\b(?:market\s+)?buy\b", line, re.I) else "SELL" if re.search(r"\b(?:market\s+)?sell\b", line, re.I) else "UNRESOLVED"
        event = next((x for x in ("SQX_ORDER_SENT", "SQX_POSITION_CLOSE", "SQX_SIGNAL",
                                  "SQX_ORDER_FAILED") if x in line), "MARKET_DEAL")
        rows.append({"record_type": event, "timestamp": ts.group("ts") if ts else "UNRESOLVED",
                     "strategy_id": sid.group("id") if sid else "UNRESOLVED",
                     "order_id": nums[0] if nums else "UNRESOLVED",
                     "deal_id": nums[1] if len(nums) > 1 else "UNRESOLVED",
                     "position_id": nums[2] if len(nums) > 2 else "UNRESOLVED",
                     "direction": direction, "volume": "UNRESOLVED", "price": "UNRESOLVED",
                     "stop": "UNRESOLVED", "target": "UNRESOLVED",
                     "exit_reason": "TIME" if "TIME_EXIT" in line else "STOP" if "stop" in line.lower() else "TARGET" if "take profit" in line.lower() else "UNRESOLVED",
                     "message": line, "source": "MT5_JOURNAL"})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("journal", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    rows = parse(args.journal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    print(f"parsed_records={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
