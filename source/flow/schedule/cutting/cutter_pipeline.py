"""Pipeline for cutting quantum circuits and generating subcircuit jobs."""

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import PauliList
from qiskit_addon_cutting import generate_cutting_experiments, partition_problem

from source.models.job import JobInfo
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
    overhead: float = 0.0
    sub_results: dict[str, Any] = field(default_factory=dict)


class CircuitCutter:
    """Orchestrates circuit cutting into subcircuits into caller-specified partition sizes."""

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def cut_by_partition_sizes(
        self,
        parent_job: JobInfo,
        partition_sizes: list[int],
    ) -> dict[str, JobInfo]:
        """Cut a circuit directly according to specified cluster/partition sizes.

        Args:
            parent_job: Original JobInfo requiring cutting.
            partition_sizes: List of qubit counts for each subcircuit (e.g. [5, 2] or [4, 3]).

        Returns:
            Dictionary mapping child job name to child JobInfo instance.
        """
        if parent_job.circuit is None:
            raise ValueError(f"Job {parent_job.job_name} has no circuit to cut.")

        clean_circuit = self._prepare_clean_circuit(parent_job.circuit)
        num_qubits = clean_circuit.num_qubits

        if sum(partition_sizes) != num_qubits:
            raise ValueError(
                f"Sum of partition sizes ({sum(partition_sizes)}) must match "
                f"circuit qubit count ({num_qubits})."
            )

        # Generate partition labels from sizes: ['A']*size_A + ['B']*size_B + ...
        partition_labels: list[str] = []
        for i, size in enumerate(partition_sizes):
            label = chr(65 + i) if i < 26 else f"P{i}"
            partition_labels.extend([label] * size)

        observables, all_z_strings = self._build_computational_observables(num_qubits)
        partitioned, subexperiments, coefficients = self._partition_and_generate_experiments(
            clean_circuit=clean_circuit,
            partition_labels=partition_labels,
            observables=observables,
        )

        overhead = self._calculate_overhead(partitioned)
        parent_job.cutting_overhead = overhead

        return self._build_child_jobs(
            parent_job=parent_job,
            clean_circuit=clean_circuit,
            partitioned=partitioned,
            subexperiments=subexperiments,
            coefficients=coefficients,
            partition_labels=partition_labels,
            overhead=overhead,
            all_z_strings=all_z_strings,
        )

    def estimate_overhead_by_partition_sizes(
        self,
        parent_job: JobInfo,
        partition_sizes: list[int],
    ) -> float:
        """Estimate QPD sampling overhead without generating subexperiments or Pauli observables.

        Fast, lightweight method allowing algorithms to evaluate cutting costs before deciding.

        Args:
            parent_job: Original JobInfo requiring cutting evaluation.
            partition_sizes: List of qubit counts for each subcircuit.

        Returns:
            Sampling overhead factor (e.g. 9.0 for 1 cut two-qubit gate, 81.0 for 2 cuts).
        """
        if parent_job.circuit is None:
            return 0.0

        clean_circuit = self._prepare_clean_circuit(parent_job.circuit)
        num_qubits = clean_circuit.num_qubits

        if sum(partition_sizes) != num_qubits:
            return 0.0

        partition_labels: list[str] = []
        for i, size in enumerate(partition_sizes):
            label = chr(65 + i) if i < 26 else f"P{i}"
            partition_labels.extend([label] * size)

        partitioned = partition_problem(clean_circuit, partition_labels=partition_labels)
        return self._calculate_overhead(partitioned)

    # -------------------------------------------------------------------------
    # Dedicated Sub-functions (Single Responsibility)
    # -------------------------------------------------------------------------

    def _prepare_clean_circuit(self, circuit: QuantumCircuit) -> QuantumCircuit:
        """Prepare circuit without classical measurement bits for qiskit-addon-cutting."""
        if circuit.num_clbits > 0:
            return circuit.remove_final_measurements(inplace=False)
        return circuit.copy()

    def _build_computational_observables(self, num_qubits: int) -> tuple[PauliList, list[str]]:
        """Generate all 2^n Pauli Z/I strings and PauliList for full distribution reconstruction.

        Note on Computational Observables & Fidelity:
            Full quasi-probability distribution reconstruction and Hellinger fidelity computation
            require the complete computational Z-basis expectations (all 2^n Pauli strings) to perform
            the inverse Walsh-Hadamard transform. For cost estimation without reconstruction, use
            `estimate_overhead_by_partition_sizes` which skips observable generation entirely.
        """
        all_z_strings = ["".join(s) for s in itertools.product(["I", "Z"], repeat=num_qubits)]
        return PauliList(all_z_strings), all_z_strings

    def _partition_and_generate_experiments(
        self,
        clean_circuit: QuantumCircuit,
        partition_labels: list[str],
        observables: PauliList,
    ) -> tuple[Any, dict[str, list], list[tuple[float, Any]]]:
        """Partition circuit graph and generate cutting subexperiments."""
        partitioned = partition_problem(
            clean_circuit,
            partition_labels=partition_labels,
            observables=observables,
        )
        subexperiments, coefficients = generate_cutting_experiments(
            partitioned.subcircuits,
            partitioned.subobservables,
            num_samples=np.inf,
        )
        return partitioned, subexperiments, coefficients

    def _calculate_overhead(self, partitioned: Any) -> float:
        """Calculate QPD sampling overhead from cut bases."""
        if hasattr(partitioned, "bases") and partitioned.bases:
            return float(math.prod(b.overhead for b in partitioned.bases))
        return 0.0

    def _build_child_jobs(
        self,
        parent_job: JobInfo,
        clean_circuit: QuantumCircuit,
        partitioned: Any,
        subexperiments: dict[str, list],
        coefficients: list[tuple[float, Any]],
        partition_labels: list[str],
        overhead: float,
        all_z_strings: list[str],
    ) -> dict[str, JobInfo]:
        """Instantiate child JobInfo objects and link them with CuttingContext."""
        context = CuttingContext(
            parent_job=parent_job,
            clean_circuit=clean_circuit,
            all_z_strings=all_z_strings,
            subcircuits=partitioned.subcircuits,
            subobservables=partitioned.subobservables,
            coefficients=coefficients,
            partition_labels=partition_labels,
            overhead=overhead,
        )
        parent_job.cutting_context = context

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
                parent_job=parent_job,
                partition_label=label,
                subexperiments=subexperiments[label],
                cutting_overhead=overhead,
            )
            children_jobs[child_name] = child_job

        parent_job.children_jobs = children_jobs
        return children_jobs
