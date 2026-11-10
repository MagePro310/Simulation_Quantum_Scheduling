"""Reconstruct shot distribution from subcircuit cutting and compare with uncut baseline."""

import numpy as np
from qiskit_addon_cutting import reconstruct_expectation_values

from source.utils.fidelity import compute_hellinger_fidelity
from source.utils.ideal_distribution import (
    UnsupportedIdealCircuit,
    ideal_counts,
    measurement_map,
    project_to_clbits,
)
from source.utils.seeding import derive_seed


class CircuitReconstructor:
    """Reconstruct output bitstring probabilities from cutting subexperiments and evaluate fidelity."""

    @staticmethod
    def reconstruct_distribution(
        cutting_context,
        shots: int = 8192,
        seed: int = 0,
    ) -> tuple[dict[str, int], dict[str, int], float, float, float]:
        """Reconstruct the cut circuit's output distribution and compare it with the exact ideal one.

        Both distributions are keyed by the parent circuit's own classical bits, with
        its own qubit -> clbit mapping (clbit 0 rightmost), exactly like an uncut job's:
        the reconstruction covers every qubit, so it is projected onto the measured ones
        (unmeasured qubits such as an ancilla are marginalised out). The ideal side is
        `ideal_counts` of the parent circuit, the reference uncut jobs use. Only if the
        parent's measurements can't be read (non-terminal ones) does the comparison fall
        back to every qubit, against the unmeasured circuit with measure_all().

        Returns:
            Tuple of:
            - uncut_counts: Exact ideal distribution of the parent circuit, as expected counts for `shots`.
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

        # 2. Inverse Walsh-Hadamard sum, computed directly in O(4^n), to get probabilities P(x)
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

        reconstructed_probs = {bs: float(probs_norm[i]) for i, bs in enumerate(bitstrings)}

        # 3. Exact ideal distribution, both sides keyed by the parent's own clbits
        parent_circuit = cutting_context.parent_job.circuit
        baseline_seed = derive_seed(seed, "reconstruction", cutting_context.parent_job.job_name or "")
        try:
            clbit_map, width = measurement_map(parent_circuit)
            reconstructed_probs = project_to_clbits(reconstructed_probs, num_qubits, clbit_map, width)
            uncut_counts = ideal_counts(parent_circuit, shots, seed=baseline_seed)
        except UnsupportedIdealCircuit:
            qc_uncut = cutting_context.clean_circuit.copy()
            qc_uncut.measure_all()
            uncut_counts = ideal_counts(qc_uncut, shots, seed=baseline_seed)

        reconstructed_counts = {
            key: int(np.round(p * shots)) for key, p in reconstructed_probs.items()
        }

        # 4. Metrics
        keys = sorted(set(reconstructed_probs) | set(uncut_counts))
        uncut_probs = np.array([uncut_counts.get(k, 0) / shots for k in keys])
        recon_probs = np.array([reconstructed_probs.get(k, 0.0) for k in keys])
        tvd = float(0.5 * np.sum(np.abs(uncut_probs - recon_probs)))
        h_fidelity = compute_hellinger_fidelity(uncut_counts, reconstructed_counts)
        statistical_overlap = float(np.sum(np.minimum(uncut_probs, recon_probs)))

        return (
            uncut_counts,
            reconstructed_counts,
            h_fidelity,
            tvd,
            statistical_overlap,
        )
