"""Reconstruct shot distribution from subcircuit cutting and compare with uncut baseline."""

import numpy as np
from qiskit_aer import AerSimulator
from qiskit_addon_cutting import reconstruct_expectation_values

from source.component.help_function.fidelity import compute_hellinger_fidelity


class CircuitReconstructor:
    """Reconstruct output bitstring probabilities from cutting subexperiments and evaluate fidelity."""

    @staticmethod
    def reconstruct_distribution(
        cutting_context,
        shots: int = 8192,
    ) -> tuple[dict[str, int], dict[str, int], float, float, float]:
        """Reconstruct the full circuit bitstring distribution and compare with uncut baseline.

        Returns:
            Tuple of:
            - uncut_counts: Dictionary of {bitstring: count} from uncut baseline execution.
            - reconstructed_counts: Dictionary of {bitstring: count} reconstructed from subcircuits.
            - fidelity: Hellinger fidelity score in [0.0, 1.0].
            - tvd: Total Variation Distance in [0.0, 1.0].
            - statistical_overlap: Statistical overlap sum_x min(p_u(x), p_r(x)) = 1 - TVD.
        """
        # 1. Reconstruct expectation values of all Pauli Z strings
        expvals = np.array(
            reconstruct_expectation_values(
                cutting_context.sub_results,
                cutting_context.coefficients,
                cutting_context.subobservables,
            )
        )

        num_qubits = cutting_context.clean_circuit.num_qubits
        all_z_strings = cutting_context.all_z_strings
        bitstrings = [bin(i)[2:].zfill(num_qubits) for i in range(2**num_qubits)]

        # 2. Fast Walsh-Hadamard Transform to compute probabilities P(x)
        probs = []
        for x_int in range(2**num_qubits):
            x_bits = [(x_int >> ((num_qubits - 1) - i)) & 1 for i in range(num_qubits)]
            prob_x = 0
            for idx, s in enumerate(all_z_strings):
                s_bits = [1 if c == "Z" else 0 for c in s]
                parity = sum(xb * sb for xb, sb in zip(x_bits, s_bits)) % 2
                sign = (-1) ** parity
                prob_x += sign * expvals[idx]
            probs.append(prob_x / float(2**num_qubits))

        probs = np.array(probs)
        # Clip quasi-probability sampling noise and normalize
        probs_clipped = np.clip(probs, 0, None)
        sum_clipped = np.sum(probs_clipped)
        probs_norm = probs_clipped / sum_clipped if sum_clipped > 0 else np.ones(len(bitstrings)) / len(bitstrings)

        reconstructed_counts = {
            bs: int(np.round(probs_norm[i] * shots)) for i, bs in enumerate(bitstrings)
        }

        # 3. Execute uncut circuit baseline on AerSimulator
        qc_uncut = cutting_context.clean_circuit.copy()
        qc_uncut.measure_all()
        uncut_job = AerSimulator().run(qc_uncut, shots=shots)
        uncut_counts = dict(uncut_job.result().get_counts())

        # 4. Metrics
        uncut_probs = np.array([uncut_counts.get(bs, 0) / shots for bs in bitstrings])
        tvd = float(0.5 * np.sum(np.abs(uncut_probs - probs_norm)))
        h_fidelity = compute_hellinger_fidelity(uncut_counts, reconstructed_counts)
        statistical_overlap = float(np.sum(np.minimum(uncut_probs, probs_norm)))

        return (
            uncut_counts,
            reconstructed_counts,
            h_fidelity,
            tvd,
            statistical_overlap,
        )
