"""Pipeline for cutting quantum circuits and generating subcircuit jobs."""

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import PauliList
from qiskit_addon_cutting import generate_cutting_experiments, partition_problem

from source.component.dataclass.job_info import JobInfo
from source.flow.schedule.cutting.base_policy import BaseCuttingPolicy
from source.flow.schedule.cutting.greedy_policy import GreedyCuttingPolicy
from source.flow.schedule.cutting.half_policy import HalfCuttingPolicy

# -----------------------------------------------------------------------------
# Qiskit 2.x compatibility patch for qiskit-addon-cutting
# In Qiskit 2.x, circuit.cregs constructs new wrapper objects on access,
# causing `circuit.cregs[-1] is reg` to fail identity check in qiskit-addon-cutting.
# We patch it safely at import time using value equality (==).
# -----------------------------------------------------------------------------
try:
    import qiskit_addon_cutting.qpd.decompose as _qpd_decompose
    from qiskit.circuit import ClassicalRegister, CircuitInstruction
    from qiskit.circuit.library import Measure

    def _safe_decompose_qpd_measurements(circuit: QuantumCircuit, inplace: bool = True) -> QuantumCircuit:
        if not inplace:
            circuit = circuit.copy()
        qpd_measure_ids = [
            i
            for i, instruction in enumerate(circuit.data)
            if instruction.operation.name.lower() == "qpd_measure"
        ]
        reg = ClassicalRegister(max(1, len(qpd_measure_ids)), name="qpd_measurements")
        circuit.add_register(reg)
        for idx, i in enumerate(qpd_measure_ids):
            gate = circuit.data[i]
            inst = CircuitInstruction(
                operation=Measure(), qubits=[gate.qubits], clbits=[reg[idx]]
            )
            circuit.data[i] = inst
        assert circuit.cregs[-1] == reg
        return circuit

    _qpd_decompose._decompose_qpd_measurements = _safe_decompose_qpd_measurements
except Exception:
    pass


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
    force_cut: bool = False
    overhead: float = 0.0
    sub_results: dict[str, Any] = field(default_factory=dict)


def get_cutting_policy(policy: str | BaseCuttingPolicy) -> BaseCuttingPolicy:
    """Factory function to resolve a policy name or instance into a BaseCuttingPolicy."""
    if isinstance(policy, BaseCuttingPolicy):
        return policy
    policy_lower = str(policy).strip().lower()
    if policy_lower == "half":
        return HalfCuttingPolicy()
    if policy_lower == "greedy":
        return GreedyCuttingPolicy()
    raise ValueError(f"Unknown cutting policy '{policy}'. Available policies: 'greedy', 'half'.")


class CircuitCutter:
    """Orchestrates circuit cutting into subcircuits using modular partition strategies."""

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    @staticmethod
    def can_fit(circuit_qubits: int, max_capacity: int) -> bool:
        """Check if circuit qubit count fits within maximum machine capacity."""
        return circuit_qubits <= max_capacity

    def cut_circuit(
        self,
        parent_job: JobInfo,
        max_capacity: int,
        policy: str | BaseCuttingPolicy = "greedy",
        force_cut: bool = False,
    ) -> dict[str, JobInfo]:
        """Cut a circuit into subcircuits matching machine capacity.

        Pipeline stages:
            1. Prepare clean circuit (strip measurement bits).
            2. Generate partition labels using the selected strategy.
            3. Build computational basis Pauli observables (all 2^n strings).
            4. Partition circuit problem and generate subexperiments.
            5. Calculate QPD sampling overhead.
            6. Instantiate child JobInfo instances and attach CuttingContext.

        Args:
            parent_job: Original JobInfo requiring cutting.
            max_capacity: Maximum qubit capacity supported by target machines.
            policy: Cutting strategy ('greedy' or 'half' or BaseCuttingPolicy).
            force_cut: If True, split even if circuit already fits within capacity.

        Returns:
            Dictionary mapping child job name to child JobInfo instance.
        """
        if parent_job.circuit is None:
            raise ValueError(f"Job {parent_job.job_name} has no circuit to cut.")

        # Stage 1: Prepare clean circuit
        clean_circuit = self._prepare_clean_circuit(parent_job.circuit)
        num_qubits = clean_circuit.num_qubits

        # Stage 2: Generate partition labels
        strategy = self._resolve_policy(policy)
        partition_labels = strategy.get_partition_labels(
            num_qubits, max_capacity, force_cut=force_cut
        )

        # Stage 3: Build computational basis observables
        observables, all_z_strings = self._build_computational_observables(num_qubits)

        # Stage 4: Partition problem & generate subexperiments
        partitioned, subexperiments, coefficients = self._partition_and_generate_experiments(
            clean_circuit=clean_circuit,
            partition_labels=partition_labels,
            observables=observables,
        )

        # Stage 5: Calculate sampling overhead
        overhead = self._calculate_overhead(partitioned)
        parent_job.cutting_overhead = overhead

        # Stage 6: Build child jobs & cutting context
        return self._build_child_jobs(
            parent_job=parent_job,
            clean_circuit=clean_circuit,
            partitioned=partitioned,
            subexperiments=subexperiments,
            coefficients=coefficients,
            partition_labels=partition_labels,
            policy_name=strategy.name,
            force_cut=force_cut,
            overhead=overhead,
            all_z_strings=all_z_strings,
        )

    # -------------------------------------------------------------------------
    # Dedicated Sub-functions (Single Responsibility)
    # -------------------------------------------------------------------------

    def _resolve_policy(self, policy: str | BaseCuttingPolicy) -> BaseCuttingPolicy:
        """Resolve policy argument to a BaseCuttingPolicy instance."""
        return get_cutting_policy(policy)

    def _prepare_clean_circuit(self, circuit: QuantumCircuit) -> QuantumCircuit:
        """Prepare circuit without classical measurement bits for qiskit-addon-cutting."""
        if circuit.num_clbits > 0:
            return circuit.remove_final_measurements(inplace=False)
        return circuit.copy()

    def _build_computational_observables(self, num_qubits: int) -> tuple[PauliList, list[str]]:
        """Generate all 2^n Pauli Z/I strings and PauliList for full distribution reconstruction."""
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
        policy_name: str,
        force_cut: bool,
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
            policy=policy_name,
            force_cut=force_cut,
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
                parentJob=parent_job,
                partition_label=label,
                subexperiments=subexperiments[label],
                cutting_overhead=overhead,
            )
            children_jobs[child_name] = child_job

        parent_job.childrenJobs = children_jobs
        return children_jobs

    # -------------------------------------------------------------------------
    # Backward Compatibility Static Methods
    # -------------------------------------------------------------------------

    @staticmethod
    def get_greedy_partition_labels(num_qubits: int, max_capacity: int) -> list[str]:
        """Backward compatibility: delegate to GreedyCuttingPolicy."""
        return GreedyCuttingPolicy().get_partition_labels(num_qubits, max_capacity)

    @staticmethod
    def get_half_partition_sizes(
        num_qubits: int,
        max_capacity: int,
        force_cut: bool = False,
    ) -> list[int]:
        """Backward compatibility: delegate to HalfCuttingPolicy."""
        return HalfCuttingPolicy().calculate_subcircuit_sizes(
            num_qubits, max_capacity, force_cut=force_cut
        )

    @staticmethod
    def get_half_partition_labels(
        num_qubits: int,
        max_capacity: int,
        force_cut: bool = False,
    ) -> list[str]:
        """Backward compatibility: delegate to HalfCuttingPolicy."""
        return HalfCuttingPolicy().get_partition_labels(
            num_qubits, max_capacity, force_cut=force_cut
        )

    @staticmethod
    def get_partition_labels(
        num_qubits: int,
        max_capacity: int,
        policy: str = "greedy",
        force_cut: bool = False,
    ) -> list[str]:
        """Backward compatibility: delegate to appropriate policy."""
        strategy = get_cutting_policy(policy)
        return strategy.get_partition_labels(num_qubits, max_capacity, force_cut=force_cut)


# Backward compatibility alias
GreedyCircuitCutter = CircuitCutter
