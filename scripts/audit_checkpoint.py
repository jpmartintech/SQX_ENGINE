#!/usr/bin/env python3
"""Read-only forensic summary for a SQX checkpoint."""
import argparse, json, hashlib, sys
from collections import Counter
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("checkpoint", type=Path); p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not args.checkpoint.exists():
        print(json.dumps({"status": "MISSING", "path": str(args.checkpoint)})); return 2
    with args.checkpoint.open() as f: state = json.load(f)
    hashes = state.get("canonical_hashes", [])
    counters = state.get("counters", {})
    attempts = int(counters.get("attempts", counters.get("generated", 0)))
    unique = int(counters.get("unique", state.get("evaluations", len(hashes))))
    population = state.get("generator", {}).get("population", [])
    pop_hashes = []
    families = Counter()
    for raw, _score in population:
        try:
            item = json.loads(raw); ps = item.get("predicates", [])
            pop_hashes.append(hashlib.sha256(raw.encode()).hexdigest())
            families[tuple(sorted(x.get("feature", "") for x in ps))] += 1
        except (TypeError, ValueError, json.JSONDecodeError): pass
    out = {
        "path": str(args.checkpoint), "size_bytes": args.checkpoint.stat().st_size,
        "status": state.get("status"), "evaluations": state.get("evaluations"),
        "attempts": attempts, "unique": unique, "duplicates": int(counters.get("duplicates", max(0, attempts - unique))),
        "duplicate_rate": max(0, attempts - unique) / max(1, attempts),
        "attempts_per_unique": attempts / max(1, unique), "canonical_hashes_count": len(hashes),
        "basic_pass": counters.get("basic_pass", 0), "rejection_counts": state.get("rejection_counts", {}),
        "population_size": len(population), "population_unique": len(set(pop_hashes)),
        "population_unique_ratio": len(set(pop_hashes)) / max(1, len(population)),
        "generation": state.get("generator", {}).get("generation", 0),
        "family_counts": {"|".join(k): v for k, v in families.items()},
        "generator_telemetry": state.get("generator", {}).get("telemetry", {}),
    }
    if args.output: args.output.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True)); return 0
if __name__ == "__main__": sys.exit(main())
