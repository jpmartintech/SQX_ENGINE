#!/usr/bin/env python3
"""Generator-only scale benchmark; no data, backtest, SQLite, or checkpoint writes."""
import argparse, json, time
from pathlib import Path
from sqx_engine.generators import GeneticGenerator

def run(n, mode, seed, population, mutation, crossover, retry):
    gen = GeneticGenerator("EURUSD", "H1", seed=seed, max_predicates=2,
                           population_size=population, mutation_rate=mutation,
                           crossover_rate=crossover, mode=mode,
                           novelty_retry_limit=retry)
    seen = set(); attempts = 0; windows = []; start = time.perf_counter(); mark = start
    while len(seen) < n and attempts < n * 20:
        attempts += 1; s = gen.ask(known_hashes=seen); key = s.canonical_hash
        if key in seen: continue
        seen.add(key)
        class Score: expectancy_r = 1.0; sharpe = 1.0; max_drawdown = .1
        gen.tell(s, Score())
        if len(seen) % max(1, n // 5) == 0:
            now = time.perf_counter(); windows.append({"unique": len(seen), "attempts": attempts, "unique_per_sec": (len(seen) - (len(seen)-n//5)) / max(1e-9, now-mark)}); mark = now
    elapsed = time.perf_counter() - start
    return {"requested": n, "mode": mode, "attempts": attempts, "unique": len(seen), "duplicates": attempts-len(seen), "duplicate_rate": (attempts-len(seen))/max(1, attempts), "attempts_per_unique": attempts/max(1,len(seen)), "runtime": elapsed, "unique_per_sec": len(seen)/max(1e-9,elapsed), "windows": windows, "telemetry": gen.telemetry}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--sizes", default="1000,10000,50000,100000"); p.add_argument("--mode", default="scale"); p.add_argument("--output", type=Path)
    a=p.parse_args(); result={str(n):run(int(n),a.mode,1301,40,.35,.70,8) for n in a.sizes.split(",")}
    if a.output: a.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
if __name__ == "__main__": main()
