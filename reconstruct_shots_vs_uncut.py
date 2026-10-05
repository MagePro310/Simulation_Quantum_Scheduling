"""
Reconstruct overall shot distribution from subcircuit cutting and compare with uncut circuit.
"""

import itertools
import numpy as np
import matplotlib.pyplot as plt
from qiskit.circuit.library import efficient_su2
from qiskit.quantum_info import PauliList
from qiskit_addon_cutting import (
    partition_problem,
    generate_cutting_experiments,
    reconstruct_expectation_values,
)
from qiskit_ibm_runtime.fake_provider import FakeManilaV2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime import SamplerV2, Batch


def run_experiment(shots=8192):
    # -------------------------------------------------------------------------
    # 1. Target Circuit Setup
    # -------------------------------------------------------------------------
    num_qubits = 4
    qc = efficient_su2(num_qubits, entanglement="linear", reps=2)
    qc.assign_parameters([0.4] * len(qc.parameters), inplace=True)

    backend = FakeManilaV2()
    pass_manager = generate_preset_pass_manager(optimization_level=1, backend=backend)

    # -------------------------------------------------------------------------
    # 2. Execute Uncut Circuit Directly
    # -------------------------------------------------------------------------
    print(f"--- Running Uncut Circuit ({shots} shots) ---")
    qc_uncut = qc.copy()
    qc_uncut.measure_all()
    isa_uncut = pass_manager.run(qc_uncut)

    sampler = SamplerV2(mode=backend)
    job_uncut = sampler.run([isa_uncut], shots=shots)
    uncut_counts = job_uncut.result()[0].data.meas.get_counts()

    # -------------------------------------------------------------------------
    # 3. Circuit Cutting Flow
    # -------------------------------------------------------------------------
    print("--- Partitioning & Generating Cutting Experiments ---")
    # All 2^4 = 16 Pauli Z/I strings (computational basis observable)
    all_z_strings = ["".join(s) for s in itertools.product(["I", "Z"], repeat=num_qubits)]
    pauli_list = PauliList(all_z_strings)

    partitioned_problem = partition_problem(
        circuit=qc, partition_labels="AABB", observables=pauli_list
    )
    subcircuits = partitioned_problem.subcircuits
    subobservables = partitioned_problem.subobservables

    # Generate cutting subexperiments
    subexperiments, coefficients = generate_cutting_experiments(
        circuits=subcircuits,
        observables=subobservables,
        num_samples=np.inf,
    )

    print(f"Subexperiments in A: {len(subexperiments['A'])}")
    print(f"Subexperiments in B: {len(subexperiments['B'])}")

    # Transpile subexperiments
    isa_subexperiments = {
        label: pass_manager.run(partition_subexpts)
        for label, partition_subexpts in subexperiments.items()
    }

    # Execute subexperiments
    print(f"--- Running Subexperiments on {backend.name} ---")
    with Batch(backend=backend) as batch:
        batch_sampler = SamplerV2(mode=batch)
        jobs = {
            label: batch_sampler.run(subsystem_subexpts, shots=shots)
            for label, subsystem_subexpts in isa_subexperiments.items()
        }
    sub_results = {label: job.result() for label, job in jobs.items()}

    # -------------------------------------------------------------------------
    # 4. Reconstruct Expectation Values of Pauli Z Strings
    # -------------------------------------------------------------------------
    expvals = np.array(
        reconstruct_expectation_values(sub_results, coefficients, subobservables)
    )

    # -------------------------------------------------------------------------
    # 5. Walsh-Hadamard Transform: Pauli Z Expvals -> Bitstring Probabilities P(x)
    #    P(x) = (1 / 2^n) * sum_s (-1)^{x . s} <s_z>
    # -------------------------------------------------------------------------
    bitstrings = [bin(i)[2:].zfill(num_qubits) for i in range(2**num_qubits)]
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

    # Clip negative values due to quasi-probability noise and normalize
    probs_clipped = np.clip(probs, 0, None)
    probs_norm = probs_clipped / np.sum(probs_clipped)

    # Reconstructed shot counts
    reconstructed_counts = {
        bs: int(np.round(probs_norm[i] * shots)) for i, bs in enumerate(bitstrings)
    }

    # -------------------------------------------------------------------------
    # 6. Comparison & Metrics
    # -------------------------------------------------------------------------
    print("\n" + "=" * 62)
    print(f"{'Bitstring':<10} | {'Uncut Counts':<14} | {'Reconstructed Counts':<22} | {'Diff':<8}")
    print("-" * 62)
    for bs in bitstrings:
        c_uncut = uncut_counts.get(bs, 0)
        c_recon = reconstructed_counts.get(bs, 0)
        diff = c_recon - c_uncut
        print(f"{bs:<10} | {c_uncut:<14} | {c_recon:<22} | {diff:<8}")
    print("=" * 62)

    uncut_probs = np.array([uncut_counts.get(bs, 0) / shots for bs in bitstrings])
    tvd = 0.5 * np.sum(np.abs(uncut_probs - probs_norm))
    fidelity = np.sum(np.sqrt(uncut_probs * probs_norm)) ** 2

    print(f"\nTotal Variation Distance (TVD): {tvd:.4f} (lower is better, 0 = identical)")
    print(f"Classical Fidelity (Bhattacharyya): {fidelity:.4f} (1.0 = identical)")

    # -------------------------------------------------------------------------
    # 7. Plotting Comparison
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    x_indices = np.arange(len(bitstrings))
    width = 0.35

    ax.bar(x_indices - width / 2, [uncut_counts.get(bs, 0) for bs in bitstrings], width, label="Uncut (Actual)", color="#1f77b4")
    ax.bar(x_indices + width / 2, [reconstructed_counts.get(bs, 0) for bs in bitstrings], width, label="Reconstructed from Subcircuits", color="#ff7f0e")

    ax.set_xlabel("Bitstring Outcome")
    ax.set_ylabel("Shot Counts")
    ax.set_title(f"Uncut vs. Reconstructed Shot Distribution (Shots = {shots})")
    ax.set_xticks(x_indices)
    ax.set_xticklabels(bitstrings, rotation=45)
    ax.legend()
    plt.tight_layout()

    output_plot = "results/reconstructed_vs_uncut_shots.png"
    plt.savefig(output_plot, dpi=300)
    print(f"\nComparison chart saved to: {output_plot}")


if __name__ == "__main__":
    run_experiment(shots=8192)
