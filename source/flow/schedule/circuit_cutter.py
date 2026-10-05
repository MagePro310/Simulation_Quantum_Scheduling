"""Circuit cutting for quantum jobs that exceed machine capacity (Greedy and Half cut policies)."""

import itertools
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import PauliList
from qiskit_addon_cutting import partition_problem, generate_cutting_experiments

from source.component.dataclass.job_info import JobInfo


@dataclass
class CuttingContext:
    """Store metadata needed to reconstruct a cut circuit after execution."""
    parent_job: JobInfo
    clean_circuit: QuantumCircuit
    all_z_strings: list[str]
    subcircuits: dict[str, QuantumCircuit]
    subobservables: dict[str, PauliList]
    coefficients: list[tuple[float, Any]]
    partition_labels: list[str]
    policy: str = "greedy"
    overhead: float = 0.0
    sub_results: dict[str, Any] = field(default_factory=dict)


class CircuitCutter:
    """Partition circuits into subcircuits matching machine capacity using greedy or half cut policies."""

    @staticmethod
    def can_fit(circuit_qubits: int, max_capacity: int) -> bool:
        """Check if circuit qubit count fits within maximum machine capacity."""
        return circuit_qubits <= max_capacity

    @staticmethod
    def get_greedy_partition_labels(num_qubits: int, max_capacity: int) -> list[str]:
        """Greedily allocate qubits into subcircuit partitions of size <= max_capacity.

        Takes maximum capacity chunks first.
        For example: 7 qubits with capacity 5 returns:
        ['A', 'A', 'A', 'A', 'A', 'B', 'B'] (partition sizes 5 and 2).
        """
        remaining = num_qubits
        labels = []
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        idx = 0

        while remaining > 0:
            take = min(remaining, max_capacity)
            partition_letter = letters[idx % len(letters)]
            labels.extend([partition_letter] * take)
            remaining -= take
            idx += 1

        return labels

    @staticmethod
    def get_half_partition_sizes(num_qubits: int, max_capacity: int) -> list[int]:
        """Recursively split qubits into balanced halves until all subcircuits fit within max_capacity.

        For example:
        - 7 qubits with capacity 5 -> [4, 3] (ceil/floor halves)
        - 12 qubits with capacity 5 -> [3, 3, 3, 3]
        """
        if num_qubits <= max_capacity:
            return [num_qubits]
        left = (num_qubits + 1) // 2
        right = num_qubits // 2
        return (
            CircuitCutter.get_half_partition_sizes(left, max_capacity)
            + CircuitCutter.get_half_partition_sizes(right, max_capacity)
        )

    @staticmethod
    def get_half_partition_labels(num_qubits: int, max_capacity: int) -> list[str]:
        """Allocate qubits into balanced half subcircuits of size <= max_capacity.

        Splits circuits into equal / near-equal halves.
        For example: 7 qubits with capacity 5 returns:
        ['A', 'A', 'A', 'A', 'B', 'B', 'B'] (partition sizes 4 and 3).
        """
        sizes = CircuitCutter.get_half_partition_sizes(num_qubits, max_capacity)
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        labels = []
        for idx, size in enumerate(sizes):
            partition_letter = letters[idx % len(letters)]
            labels.extend([partition_letter] * size)
        return labels

    @staticmethod
    def get_partition_labels(num_qubits: int, max_capacity: int, policy: str = "greedy") -> list[str]:
        """Get partition labels according to the specified policy ('greedy' or 'half')."""
        if policy.lower() == "half":
            return CircuitCutter.get_half_partition_labels(num_qubits, max_capacity)
        return CircuitCutter.get_greedy_partition_labels(num_qubits, max_capacity)

    def cut_circuit(
        self,
        parent_job: JobInfo,
        max_capacity: int,
        policy: str = "greedy",
    ) -> dict[str, JobInfo]:
        """Cut a circuit into subcircuits fitting within max_capacity qubits.

        Args:
            parent_job: The original job requiring cutting.
            max_capacity: The maximum number of qubits a machine can support.
            policy: Cutting policy ('greedy' or 'half').

        Returns:
            Dictionary of child JobInfo instances representing the subcircuits.
        """
        if parent_job.circuit is None:
            raise ValueError(f"Job {parent_job.job_name} has no circuit to cut.")

        original_circuit = parent_job.circuit
        num_qubits = original_circuit.num_qubits

        # Qiskit Addon Cutting requires circuit without classical measurement bits
        if original_circuit.num_clbits > 0:
            clean_circuit = original_circuit.remove_final_measurements(inplace=False)
        else:
            clean_circuit = original_circuit.copy()

        # Compute partition labels according to policy
        partition_labels = self.get_partition_labels(num_qubits, max_capacity, policy=policy)

        # Build computational basis observable: all 2^n Pauli Z/I combinations
        all_z_strings = ["".join(s) for s in itertools.product(["I", "Z"], repeat=num_qubits)]
        pauli_list = PauliList(all_z_strings)

        # Partition circuit problem
        partitioned = partition_problem(
            clean_circuit,
            partition_labels=partition_labels,
            observables=pauli_list,
        )

        # Generate subexperiments
        subexperiments, coefficients = generate_cutting_experiments(
            partitioned.subcircuits,
            partitioned.subobservables,
            num_samples=np.inf,
        )

        # Calculate cutting overhead: sampling overhead product from QPD bases
        import math
        if hasattr(partitioned, "bases") and partitioned.bases:
            overhead = float(math.prod(b.overhead for b in partitioned.bases))
        else:
            overhead = 0.0

        parent_job.cutting_overhead = overhead

        # Create cutting context
        context = CuttingContext(
            parent_job=parent_job,
            clean_circuit=clean_circuit,
            all_z_strings=all_z_strings,
            subcircuits=partitioned.subcircuits,
            subobservables=partitioned.subobservables,
            coefficients=coefficients,
            partition_labels=partition_labels,
            policy=policy,
            overhead=overhead,
        )
        parent_job.cutting_context = context

        # Create child jobs
        children_jobs: dict[str, JobInfo] = {}
        for label, sub_circuit in partitioned.subcircuits.items():
            child_name = f"{parent_job.job_name}_sub_{label}"
            child_job = JobInfo(
                job_name=child_name,
                circuit=sub_circuit,
                num_qubits=sub_circuit.num_qubits,
                shots=parent_job.shots,
                arrival_time=parent_job.arrival_time,
                priority=parent_job.priority,
                parentJob=parent_job,
                partition_label=label,
                subexperiments=subexperiments[label],
                cutting_overhead=overhead,
            )
            children_jobs[child_name] = child_job

        parent_job.childrenJobs = children_jobs
        return children_jobs


# Backwards compatibility alias
GreedyCircuitCutter = CircuitCutter
