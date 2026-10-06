"""Hellinger fidelity and distance calculation utilities.

References:
    hellinger_fidelity.py
    qiskit.quantum_info.hellinger_fidelity
"""

from qiskit.quantum_info import hellinger_fidelity


def compute_hellinger_fidelity(
    counts_ideal: dict[str, int | float] | None,
    counts_noisy: dict[str, int | float] | None,
) -> float:
    """Calculate Hellinger fidelity between ideal and noisy counts distributions.

    Args:
        counts_ideal: Dict of ideal measurement counts or probabilities {bitstring: count}.
        counts_noisy: Dict of noisy measurement counts or probabilities {bitstring: count}.

    Returns:
        float: Hellinger fidelity bounded in [0.0, 1.0].
    """
    if not counts_ideal or not counts_noisy:
        if not counts_ideal and not counts_noisy:
            return 1.0
        return 0.0

    try:
        fidelity = float(hellinger_fidelity(counts_ideal, counts_noisy))
        return max(0.0, min(1.0, fidelity))
    except Exception:
        return 0.0


def compute_total_variation_distance(
    counts_ideal: dict[str, int | float] | None,
    counts_noisy: dict[str, int | float] | None,
) -> float:
    """Calculate Total Variation Distance (TVD) between two count distributions.

    TVD = 0.5 * sum_x |p_ideal(x) - p_noisy(x)| in [0.0, 1.0].

    Args:
        counts_ideal: Dict of ideal measurement counts {bitstring: count}.
        counts_noisy: Dict of noisy measurement counts {bitstring: count}.

    Returns:
        float: Total Variation Distance bounded in [0.0, 1.0].
    """
    if not counts_ideal or not counts_noisy:
        if not counts_ideal and not counts_noisy:
            return 0.0
        return 1.0

    sum_ideal = sum(counts_ideal.values()) or 1.0
    sum_noisy = sum(counts_noisy.values()) or 1.0
    all_keys = set(counts_ideal) | set(counts_noisy)

    tvd = 0.5 * sum(
        abs(counts_ideal.get(k, 0) / sum_ideal - counts_noisy.get(k, 0) / sum_noisy)
        for k in all_keys
    )
    return float(max(0.0, min(1.0, tvd)))

