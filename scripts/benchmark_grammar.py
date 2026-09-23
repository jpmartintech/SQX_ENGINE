#!/usr/bin/env python3
"""Bounded Development-only V1.7 factory benchmark (never starts 250K)."""
import argparse
import json
from pathlib import Path
import platform
import resource
import time

from sqx_engine.config import EngineConfig
from sqx_engine.engine import StrategyFactory
from sqx_engine.grammar import search_space


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    config = EngineConfig.from_yaml(args.config)
    n = config.get('generator.evaluations')
    if not isinstance(n, int) or not 1 <= n <= 50000:
        raise ValueError('Benchmark limited to 1–50,000 evaluations')
    if config.get('data_split') != {'method': 'chronological', 'development': .7, 'validation': .15, 'oos': .15}:
        raise ValueError('Benchmark requires frozen Development-only 70/15/15 split')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Audit is published before invoking the factory, including before 50K.
    audit_path = args.output.parent / 'search_space.json'
    audit_path.write_text(json.dumps(search_space(config.get('strategy.min_predicates', 1), config.get('strategy.max_predicates', 4)), indent=2) + '\n')
    started = time.perf_counter()
    result = StrategyFactory(config).run()
    result['wall_time_including_checkpoint'] = time.perf_counter() - started
    result['peak_rss_mb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    result['python'] = platform.python_version()
    result['scope'] = 'DEVELOPMENT_ONLY'
    result['attempts_per_unique'] = result['attempts'] / max(1, result['unique'])
    result['duplicate_rate'] = result['duplicates'] / max(1, result['attempts'])
    args.output.write_text(json.dumps(result, indent=2, default=str) + '\n')
    if result['unique'] != n or result['backtested'] != n:
        raise RuntimeError('Benchmark did not reach requested unique strategies')
    print(json.dumps({k: result[k] for k in ['unique', 'runtime', 'strategies_per_sec', 'peak_rss_mb', 'duplicates', 'counters']}, indent=2))


if __name__ == '__main__': main()
