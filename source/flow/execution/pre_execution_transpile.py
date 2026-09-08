"""Prepare one concurrent group of jobs for a target quantum machine."""

import math

from qiskit.circuit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.compiler import transpile

from source.component.dataclass.execution_info import PreparedBatch
from source.component.dataclass.job_info import JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class PreExecution:
    def prepare_batch(
        self,
        machine: MachineCharacteristic,
        jobs: dict[str, JobInfo],
        *,
        seed: int,
    ) -> PreparedBatch:
        """Compose disjoint jobs and estimate one shot's QPU time in seconds.

        Dictionary order defines the merged logical and classical bit order.
        The backend may allocate routing ancillas during transpilation; these
        do not change the jobs' logical admission capacity or result mapping.
        """
        total_qubits, total_clbits = self._validate_batch(machine, jobs)
        merged_circuit, classical_bits = self._compose_circuits(jobs, total_qubits, total_clbits)

        backend = machine.quantum_machine
        transpiled_circuit = transpile(
            merged_circuit,
            backend=backend,
            scheduling_method="alap",
            optimization_level=1,
            seed_transpiler=seed,
        )
        duration_per_shot = float(
            transpiled_circuit.estimate_duration(backend.target, unit="s")
        )
        if not math.isfinite(duration_per_shot) or duration_per_shot <= 0:
            raise ValueError(
                f"Machine '{machine.name}' produced an invalid per-shot duration: "
                f"{duration_per_shot!r} seconds."
            )

        return PreparedBatch(
            job_ids=tuple(jobs),
            merged_circuit=merged_circuit,
            transpiled_circuit=transpiled_circuit,
            classical_bits=classical_bits,
            logical_qubits=total_qubits,
            duration_per_shot=duration_per_shot,
        )

    @staticmethod
    def _validate_batch(
        machine: MachineCharacteristic, jobs: dict[str, JobInfo],
    ) -> tuple[int, int]:
        """Validate each circuit and capacity, then return the combined bit widths."""
        if not jobs:
            raise ValueError("At least one job is required to prepare a batch.")

        for job_id, job in jobs.items():
            if not isinstance(job.circuit, QuantumCircuit):
                raise ValueError(f"Job '{job_id}' requires a QuantumCircuit.")
            if job.circuit.num_qubits <= 0:
                raise ValueError(f"Job '{job_id}' requires at least one qubit.")
            if not job.circuit.num_clbits or not job.circuit.count_ops().get("measure"):
                raise ValueError(f"Job '{job_id}' requires a measured circuit.")
            if job.circuit.num_parameters:
                raise ValueError(f"Job '{job_id}' has unbound circuit parameters.")

        total_qubits = sum(job.circuit.num_qubits for job in jobs.values())
        total_clbits = sum(job.circuit.num_clbits for job in jobs.values())
        if total_qubits > machine.capacity:
            raise ValueError(
                f"Batch requires {total_qubits} logical qubits, but machine "
                f"'{machine.name}' has capacity {machine.capacity}."
            )
        return total_qubits, total_clbits

    @staticmethod
    def _compose_circuits(
        jobs: dict[str, JobInfo], total_qubits: int, total_clbits: int,
    ) -> tuple[QuantumCircuit, dict[str, tuple[int, ...]]]:
        """Compose jobs on disjoint bits and record their classical mapping."""
        merged_circuit = QuantumCircuit(
            QuantumRegister(total_qubits, "q"), ClassicalRegister(total_clbits, "meas")
        )
        classical_bits: dict[str, tuple[int, ...]] = {}
        qubit_offset = 0
        clbit_offset = 0
        for job_id, job in jobs.items():
            circuit = job.circuit
            bit_indices = tuple(range(clbit_offset, clbit_offset + circuit.num_clbits))
            merged_circuit.compose(
                circuit,
                qubits=range(qubit_offset, qubit_offset + circuit.num_qubits),
                clbits=bit_indices,
                inplace=True,
            )
            classical_bits[job_id] = bit_indices
            qubit_offset += circuit.num_qubits
            clbit_offset += circuit.num_clbits
        return merged_circuit, classical_bits
