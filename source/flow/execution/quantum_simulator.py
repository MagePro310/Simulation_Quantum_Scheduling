"""Quantum simulator execution."""

from collections.abc import Mapping
from numbers import Integral

from qiskit_aer import AerSimulator

from source.component.dataclass.execution_info import BatchCounts, PreparedBatch
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class QuantumExecutor:
    """Execute quantum circuits on simulator."""

    @staticmethod
    def max_shots(machine: MachineCharacteristic) -> int | None:
        """Return backend shot limit if available."""
        backend = machine.quantum_machine
        candidates = [getattr(backend, "max_shots", None)]

        configuration = getattr(backend, "configuration", None)
        if callable(configuration):
            config = configuration()
            candidates.append(
                config.get("max_shots") if isinstance(config, Mapping)
                else getattr(config, "max_shots", None)
            )

        options = getattr(backend, "options", None)
        validators = getattr(options, "validator", None)
        if isinstance(validators, Mapping):
            shots_validator = validators.get("shots")
            if isinstance(shots_validator, tuple) and len(shots_validator) == 2:
                candidates.append(shots_validator[1])

        limits = [
            int(value) for value in candidates
            if isinstance(value, Integral) and not isinstance(value, bool) and value > 0
        ]
        return min(limits) if limits else None

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
