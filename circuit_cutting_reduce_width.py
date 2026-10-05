import numpy as np
from qiskit.circuit.library import efficient_su2
from qiskit.quantum_info import PauliList
from qiskit_addon_cutting import partition_problem, generate_cutting_experiments
from qiskit_ibm_runtime.fake_provider import FakeManilaV2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime import SamplerV2, Batch

# 1. Define circuit
qc = efficient_su2(4, entanglement="linear", reps=2)
qc.assign_parameters([0.4] * len(qc.parameters), inplace=True)

# 2. Partition with computational basis (Z on all qubits) instead of Hamiltonian observables
partitioned_problem = partition_problem(
    circuit=qc,
    partition_labels="AABB",
    observables=PauliList(["ZZZZ"])  # All-Z measures every qubit in computational basis
)
subcircuits = partitioned_problem.subcircuits
subobservables = partitioned_problem.subobservables
# subobservables will be: {'A': PauliList(['ZZ']), 'B': PauliList(['ZZ'])}

# 3. Generate subexperiments
# num_samples can be finite (e.g., 10 or 100) or np.inf for exhaustive basis sampling
subexperiments, coefficients = generate_cutting_experiments(
    circuits=subcircuits,
    observables=subobservables,
    num_samples=10
)

# 4. Transpile subcircuits for backend
backend = FakeManilaV2()
pass_manager = generate_preset_pass_manager(optimization_level=1, backend=backend)
isa_subexperiments = {
    label: pass_manager.run(partition_subexpts)
    for label, partition_subexpts in subexperiments.items()
}

# 5. Run subcircuits on SamplerV2
with Batch(backend=backend) as batch:
    sampler = SamplerV2(mode=batch)
    jobs = {
        label: sampler.run(subsystem_subexpts, shots=2**10)
        for label, subsystem_subexpts in isa_subexperiments.items()
    }

results = {label: job.result() for label, job in jobs.items()}

# 6. Extract the shot distribution of each subcircuit variant
for label, partition_result in results.items():
    print(f"\n=== Partition {label} ({len(partition_result)} subexperiments) ===")
    for idx, pub_res in enumerate(partition_result):
        # observable_measurements contains the computational basis shot counts
        counts = pub_res.data.observable_measurements.get_counts()
        print(f"Subcircuit {label} variant {idx} shot distribution: {counts}")
        
        # If the subcircuit has QPD mid-circuit cut measurements:
        if hasattr(pub_res.data, "qpd_measurements"):
            qpd_counts = pub_res.data.qpd_measurements.get_counts()
            # print(f"  QPD cut measurement counts: {qpd_counts}")