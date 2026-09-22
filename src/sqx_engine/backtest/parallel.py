"""Persistent process evaluation with ordered deterministic results."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import os

from .fast import FastEvaluator

_WORKER_EVALUATOR = None


def _init_worker(data, features, initial_capital, spread, slippage, cache_size, engine):
    global _WORKER_EVALUATOR
    _WORKER_EVALUATOR = FastEvaluator(
        data, features, initial_capital, spread, slippage, cache_size=cache_size, engine=engine
    )


def _evaluate_worker(payload):
    strategy, kwargs = payload
    return _WORKER_EVALUATOR.evaluate(strategy, **kwargs)


class ParallelEvaluator:
    def __init__(self, data, features, initial_capital, spread, slippage, workers, cache_size=4096, engine="auto"):
        self.workers = max(1, int(workers))
        methods = mp.get_all_start_methods()
        # Linux/WSL fork avoids a forkserver socket and shares read-only market
        # pages efficiently. Spawn remains the portable fallback.
        context = mp.get_context("fork" if "fork" in methods else "spawn")
        self.executor = ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=context,
            initializer=_init_worker,
            initargs=(data, dict(features), initial_capital, spread, slippage, cache_size, engine),
        )

    def evaluate_batch(self, strategies, **kwargs):
        return list(self.executor.map(
            _evaluate_worker, ((strategy, kwargs) for strategy in strategies), chunksize=1
        ))

    def shutdown(self):
        self.executor.shutdown(wait=True, cancel_futures=False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.shutdown()


def resolve_workers(value, reserved=1):
    visible = os.cpu_count() or 1
    if value is None or str(value).lower() == "auto":
        return max(1, visible - int(reserved))
    return max(1, min(visible, int(value)))
