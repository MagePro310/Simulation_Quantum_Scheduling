"""Quantum simulator execution."""

from qiskit_aer import AerSimulator

from source.component.dataclass.execution_info import BatchCounts, PreparedBatch
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class QuantumExecutor:
    """Execute quantum circuits on simulator."""

    @staticmethod
    def max_shots(machine: MachineCharacteristic) -> int | None:
        """Return backend shot limit if available."""
        backend = machine.quantum_machine
        shots = getattr(backend, "max_shots", None) or getattr(getattr(backend, "configuration", lambda: None)(), "max_shots", None)
        return int(shots) if shots and isinstance(shots, (int, float)) and shots > 0 else None

    def execute_batch(
        self,
        machine: MachineCharacteristic,
        prepared_batch: PreparedBatch,
        shots: int,
        *,
        seed: int,
    ) -> BatchCounts:
        """Execute transpiled circuit on quantum simulator."""
        ideal_simulator = AerSimulator()
        noisy_simulator = AerSimulator.from_backend(machine.quantum_machine)
        circuit = prepared_batch.transpiled_circuit

        ideal_result = ideal_simulator.run(circuit, shots=shots, seed_simulator=seed).result()
        noisy_result = noisy_simulator.run(circuit, shots=shots, seed_simulator=seed).result()

        return BatchCounts(
            distribution_no_noise=dict(ideal_result.get_counts()),
            distribution_with_noise=dict(noisy_result.get_counts()),
        )
