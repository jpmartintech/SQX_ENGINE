from .fast import FastEvaluator

class ReferenceEvaluator(FastEvaluator):
    """Clear correctness path for V1; FastEvaluator is deterministic and side-effect free."""
    pass

