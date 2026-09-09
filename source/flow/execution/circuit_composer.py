"""Circuit preparation: compose and transpile quantum circuits."""

import math
from qiskit.circuit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.compiler import transpile

from source.component.dataclass.execution_info import PreparedBatch
from source.component.dataclass.job_info import JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class CircuitPreparation:
    """Compose individual circuits and transpile for quantum backend."""

    def prepare_batch(
        self,
        machine: MachineCharacteristic,
        jobs: dict[str, JobInfo],
        *,
        seed: int,
    ) -> PreparedBatch:
        """Compose circuits and transpile for target backend."""
        total_qubits = sum(job.circuit.num_qubits for job in jobs.values())
        total_clbits = sum(job.circuit.num_clbits for job in jobs.values())
        merged_circuit, classical_bits = self._compose_circuits(jobs, total_qubits, total_clbits)

        # Transpile for backend
        transpiled_circuit = transpile(
            merged_circuit,
            backend=machine.quantum_machine,
            scheduling_method="alap",
            optimization_level=1,
            seed_transpiler=seed,
        )
        duration_per_shot = float(transpiled_circuit.estimate_duration(machine.quantum_machine.target, unit="s"))

        return PreparedBatch(
            job_ids=tuple(jobs),
            merged_circuit=merged_circuit,
            transpiled_circuit=transpiled_circuit,
            classical_bits=classical_bits,
            logical_qubits=total_qubits,
            duration_per_shot=duration_per_shot,
        )

    @staticmethod
    def _compose_circuits(
        jobs: dict[str, JobInfo], total_qubits: int, total_clbits: int
    ) -> tuple[QuantumCircuit, dict[str, tuple[int, ...]]]:
        """Compose jobs on disjoint bits."""
        merged_circuit = QuantumCircuit(
            QuantumRegister(total_qubits, "q"),
            ClassicalRegister(total_clbits, "meas")
        )
        classical_bits = {}
        qubit_offset = clbit_offset = 0

        for job_id, job in jobs.items():
            bit_indices = tuple(range(clbit_offset, clbit_offset + job.circuit.num_clbits))
            merged_circuit.compose(
                job.circuit,
                qubits=range(qubit_offset, qubit_offset + job.circuit.num_qubits),
                clbits=bit_indices,
                inplace=True,
            )
            classical_bits[job_id] = bit_indices
            qubit_offset += job.circuit.num_qubits
            clbit_offset += job.circuit.num_clbits

        return merged_circuit, classical_bits
