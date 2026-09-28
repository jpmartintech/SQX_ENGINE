"""Metadata-only completion of the Crypto Factory V2 dataset inventory."""
from pathlib import Path
import sys
import json
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.crypto_factory_v2 import ROOT, OUT, WIN, ASSETS, inspect_csv


def main():
    rows = [inspect_csv(p) for p in sorted(WIN.glob("*USDT_*.csv")) if p.name.split("USDT")[0] in ASSETS]
    admitted = [x for x in rows if x["timeframe"] == "15M" and x["quality_status"] == "PASS" and x["duration_days"] >= 1460]
    rejected = [{**x, "admission_reason": "1H deferred from bounded M15 V2 search"} for x in rows if x not in admitted]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data_inventory.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")
    pd.DataFrame(rows).to_csv(OUT / "data_inventory.csv", index=False)
    (OUT / "dataset_admission.json").write_text(json.dumps({"admitted": admitted, "rejected": rejected, "criteria": {"duration_days": 1460, "resolution": "15M", "valid_ohlc": True, "source": "mounted metadata-only intake"}}, indent=2, default=str) + "\n")
    print(json.dumps({"found": len(rows), "admitted": len(admitted), "rejected_deferred": len(rejected)}, indent=2))


if __name__ == "__main__":
    main()
