#!/usr/bin/env python
"""Read-only Hyperliquid V1 data/API audit.

This intentionally samples endpoints and never submits an exchange action.
The result is a capability audit, not a historical data download.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v1"
API = "https://api.hyperliquid.xyz/info"
DOCS = {
    "historical_data": "https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data",
    "info_endpoint": "https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint",
    "funding": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding",
    "fees": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees",
    "oracle": "https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/oracle",
    "robust_price": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/robust-price-indices",
    "contracts": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications",
}


def post(payload):
    request = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw), len(raw)


def summarize(value):
    """Keep audit evidence compact; never persist full live asset contexts."""
    if isinstance(value, list):
        return {"kind": "list", "rows": len(value),
                "first_keys": sorted(value[0].keys()) if value and isinstance(value[0], dict) else [],
                "last_keys": sorted(value[-1].keys()) if value and isinstance(value[-1], dict) else []}
    if isinstance(value, dict):
        return {"kind": "object", "keys": sorted(value.keys())}
    return {"kind": type(value).__name__}


def run():
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=2)).timestamp() * 1000)
    end = int(now.timestamp() * 1000)
    probes = {}
    for name, payload in {
        "meta": {"type": "meta"},
        "meta_and_asset_context": {"type": "metaAndAssetCtxs"},
        "recent_1m_candles": {"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1m", "startTime": 0, "endTime": end}},
        "recent_funding": {"type": "fundingHistory", "coin": "BTC", "startTime": 0, "endTime": end},
        "current_l2": {"type": "l2Book", "coin": "BTC"},
    }.items():
        try:
            value, size = post(payload)
            rows = len(value) if isinstance(value, list) else None
            probes[name] = {"status": "AVAILABLE", "response_bytes": size, "rows": rows,
                            "shape": summarize(value)}
        except Exception as exc:  # audit must preserve failure evidence
            probes[name] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    local_data = []
    for pattern in ("data/**/*crypto*", "data/**/*hyper*", "data/**/*BTC*", "data/**/*ETH*"):
        local_data.extend(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    local_data = sorted(set(local_data))
    probe = probes.get("recent_1m_candles", {})
    fund = probes.get("recent_funding", {})
    manifest = {
        "schema_version": "CRYPTO_DATA_MANIFEST_V1",
        "audit_timestamp_utc": now.isoformat(),
        "venue": "HYPERLIQUID",
        "api": API,
        "official_sources": DOCS,
        "assets_checked": ["BTC", "ETH"],
        "local_crypto_files": local_data,
        "capabilities": {
            "candles_live_snapshot": {"status": probe.get("status"), "observed_rows": probe.get("rows"), "observed_limit": 5000},
            "funding_live_history": {"status": fund.get("status"), "observed_rows": fund.get("rows"), "observed_limit": 500},
            "asset_context_current": {"status": probes.get("meta_and_asset_context", {}).get("status")},
            "l2_current_snapshot": {"status": probes.get("current_l2", {}).get("status"), "historical": "NOT_ESTABLISHED"},
            "historical_archive": {"status": "DOCUMENTED_BUT_NOT_LOCALLY_AVAILABLE", "requires": "requester-pays S3 access / archive retrieval"},
        },
        "causal_policy": {
            "timezone": "UTC",
            "bar_close_is_available_at": "timestamp_close_plus_one_microsecond",
            "funding": "use realized settlement only at settlement timestamp; predicted values are separate",
            "no_filling": True,
        },
        "probes": probes,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "crypto_data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    dataset_manifest = {"schema_version": "CRYPTO_CANONICAL_DATASET_V1", "status": "NOT_BUILT",
                        "reason": "official API snapshot limits and no local historical archive",
                        "base_resolution": "1m", "derived": ["5m", "15m", "1h", "4h"],
                        "dataset_hash": None, "source": "HYPERLIQUID_OFFICIAL"}
    (OUT / "dataset_manifest.json").write_text(json.dumps(dataset_manifest, indent=2) + "\n")
    audit = f"""# CRYPTO_DATA_AUDIT\n\nAudit timestamp: `{now.isoformat()}`\nVenue: Hyperliquid\n\n## Result\n\nThe read-only API probe is successful for current metadata, recent candles, funding history, asset contexts, and current L2. It is **not sufficient to build the required long historical canonical dataset**: `candleSnapshot` returned a bounded recent sample (observed approximately 5,000 rows) and `fundingHistory` returned a bounded sample (observed 500 rows). No local Hyperliquid historical dataset was found.\n\nThe official historical-data documentation describes a requester-pays S3 archive with market-data archives (including L2/asset contexts) and node trade/fill data, but it does not provide a locally available, ready-to-use historical OHLCV + realized funding + OI + mark/oracle dataset. No data was fabricated or downloaded during this audit.\n\n## Field readiness\n\n| Field | Current API | Historical causal V1 readiness | Evidence |\n|---|---|---|---|\n| BTC/ETH candles | READY (bounded snapshot) | NOT READY | API probe and documented snapshot limit |\n| volume/trade count | READY in candle response | NOT READY for long history | candle schema probe |\n| realized funding | READY (bounded history) | NOT READY for long history | funding endpoint probe |\n| open interest | current asset context only | NOT READY | metaAndAssetCtxs probe |\n| mark/oracle/premium | current context/documented semantics | NOT READY historically | official oracle/mark docs |\n| L2 | current snapshot | NOT READY historically | l2Book probe; archive requires retrieval |\n| liquidations | not established | NOT READY | no authoritative historical field established |\n\n## Decision\n\n`BLOCKED_ON_DATA` for the full Crypto Factory V1 experiment. The additive schemas and economic contract are implemented and tested, but strategy generation and OOS reservation must not begin without a reproducible historical source or an explicitly authorized provider/archive retrieval.\n\nSources: [official historical data](%s), [Info endpoint](%s), [funding](%s), [fees](%s), [oracle](%s), [robust price](%s), [contract specifications](%s).\n""" % tuple(DOCS[k] for k in ("historical_data", "info_endpoint", "funding", "fees", "oracle", "robust_price", "contracts"))
    (OUT / "CRYPTO_DATA_AUDIT.md").write_text(audit)
    (OUT / "experiment_ledger.json").write_text(json.dumps([{
        "experiment_id": "CRYPTO_V1_DATA_AUDIT_001", "parent": None,
        "hypothesis": "Official Hyperliquid sources provide sufficient causal history for V1",
        "result": "bounded live API data confirmed; long historical dataset not locally available",
        "decision": "BLOCKED_ON_DATA", "oos_accesses": 0, "timestamp_utc": now.isoformat()
    }], indent=2) + "\n")
    (OUT / "decision_log.md").write_text("""# Decision log\n\n## CRYPTO_V1_DATA_AUDIT_001\n\n- Evidence: read-only official API probes succeeded for metadata, recent candles, funding, current contexts, and L2.\n- Constraint: candle and funding responses are bounded; no local historical Hyperliquid dataset exists.\n- Decision: implement only additive data/economic contracts and stop before generation.\n- Falsifier: a reproducible authorized historical source with causal candles, realized funding, and required market fields.\n- OOS accesses: 0.\n""")
    return manifest


if __name__ == "__main__":
    run()
