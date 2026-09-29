# Optimization log

1. Reused frozen bounded contract.
2. Added Numba numeric non-overlap economic kernel.
3. Replaced pandas timestamp lookup in fast event conversion with contiguous NumPy arrays.
4. Added exact parallel batch benchmark.
Remaining bottleneck: FastEvaluator signal/trade generation.
