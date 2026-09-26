"""Parser for MetaTrader 5 Strategy Tester HTML reports."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd


class _Rows(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.table = 0
        self.row: list[str] | None = None
        self.cell: str | None = None
        self.rows: list[tuple[int, list[str]]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table += 1
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = ""

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.row is not None and self.cell is not None:
            self.row.append(" ".join(self.cell.split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append((self.table, self.row))
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def _number(value: str) -> float:
    value = value.strip().replace(" ", "")
    if not value or value == "-":
        return 0.0
    return float(value.replace(",", "."))


def _volume(value: str) -> float:
    return _number(value.split("/")[0])


def parse_report(path: str | Path) -> dict[str, object]:
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-16")
    parser = _Rows()
    parser.feed(text)
    rows = parser.rows
    order_header = ["Hora de apertura", "Orden", "Símbolo"]
    deal_header = ["Fecha/Hora", "Transacción", "Símbolo", "Tipo"]
    order_i = next(i for i, (_, r) in enumerate(rows) if r[:3] == order_header)
    deal_i = next(i for i, (_, r) in enumerate(rows) if r[:4] == deal_header)
    orders = [r for _, r in rows[order_i + 1:deal_i] if len(r) == 11]
    deals = [r for _, r in rows[deal_i + 1:] if len(r) == 13]
    od = pd.DataFrame(orders, columns=["open_time", "order_id", "symbol", "type", "volume_text", "price", "sl", "tp", "time", "status", "comment"])
    dd = pd.DataFrame(deals, columns=["time", "deal_id", "symbol", "type", "direction", "volume", "price", "order_id", "commission", "swap", "profit", "balance", "comment"])
    if not od.empty:
        for c in ["open_time", "time"]:
            od[c] = pd.to_datetime(od[c], format="%Y.%m.%d %H:%M:%S", utc=True)
        od["order_id"] = pd.to_numeric(od["order_id"], errors="coerce").astype("Int64")
        for c in ["price", "sl", "tp"]:
            od[c] = od[c].map(_number)
        od["volume"] = od.volume_text.map(_volume)
    if not dd.empty:
        dd["time"] = pd.to_datetime(dd.time, format="%Y.%m.%d %H:%M:%S", utc=True)
        dd["deal_id"] = pd.to_numeric(dd["deal_id"], errors="coerce").astype("Int64")
        dd["order_id"] = pd.to_numeric(dd["order_id"], errors="coerce").astype("Int64")
        for c in ["volume", "price", "commission", "swap", "profit", "balance"]:
            dd[c] = dd[c].map(_number)
    balance = dd[dd.direction == ""].copy()
    transactional = dd[dd.direction.isin(["in", "out"])].copy()
    return {"text": text, "rows": rows, "orders": od, "deals": transactional, "balance": balance, "all_deals": dd, "order_header_index": order_i, "deal_header_index": deal_i}


def parse_config(text: str) -> dict[str, str]:
    def between(label: str, next_label: str | None = None) -> str:
        pattern = re.escape(label) + r".*?<b>(.*?)</b>"
        match = re.search(pattern, text, flags=re.S)
        return " ".join(re.sub(r"<.*?>", "", match.group(1)).split()) if match else ""
    values = {
        "expert": between("Experto:"), "symbol": between("Símbolo:"),
        "period": between("Período:"), "initial_deposit": between("Depósito inicial:"),
        "leverage": between("Apalancamiento:"), "base_risk": "0.01" if "InpBaseRisk=0.01" in text else "",
        "max_open_risk": "0.02" if "InpMaxOpenRisk=0.02" in text else "",
        "daily_limit": "0.0" if "InpInternalDailyLimit=0.0" in text else "",
        "total_limit": "0.0" if "InpInternalTotalLimit=0.0" in text else "",
        "diagnostic_trace": "false" if "InpDiagnosticTrace=false" in text else "",
        "history_quality": re.search(r"Calidad del historial:</td>.*?<b>(.*?)</b>", text, re.S).group(1) if re.search(r"Calidad del historial:</td>.*?<b>(.*?)</b>", text, re.S) else "",
    }
    return values
