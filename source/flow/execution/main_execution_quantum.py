"""Local ideal and backend-noise simulations for an execution batch."""

from collections.abc import Mapping
from numbers import Integral

from qiskit_aer import AerSimulator

from source.component.dataclass.execution_info import BatchCounts, PreparedBatch
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class MainExecutionQuantum:
    @staticmethod
    def max_shots(machine: MachineCharacteristic) -> int | None:
        """Return the smallest advertised shot limit, without imposing a chunk size.

        Backend options such as ``shots`` and Aer's ``max_shot_size`` are
        defaults or internal splitting settings, not submission limits.
        """
        backend = machine.quantum_machine
        candidates = [getattr(backend, "max_shots", None)]
        configuration = getattr(backend, "configuration", None)
        if callable(configuration):
            config = configuration()
            candidates.append(
                config.get("max_shots")
                if isinstance(config, Mapping)
                else getattr(config, "max_shots", None)
            )

        options = getattr(backend, "options", None)
        validators = getattr(options, "validator", None)
        if isinstance(validators, Mapping):
            shots_validator = validators.get("shots")
            if isinstance(shots_validator, tuple) and len(shots_validator) == 2:
                candidates.append(shots_validator[1])

        limits = [
            int(value)
            for value in candidates
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
        """Run the same compiled circuit locally with and without backend noise.

        Results are returned together so the coordinator can validate both
        count totals before committing any progress to participating jobs.
        Exceptions propagate to its batch-failure handling.
        """
        shots = self._validate_batch_shots(machine, shots)

        ideal_simulator = AerSimulator()
        noisy_simulator = AerSimulator.from_backend(machine.quantum_machine)
        circuit = prepared_batch.transpiled_circuit
        ideal_result = ideal_simulator.run(
            circuit, shots=shots, seed_simulator=seed
        ).result()
        noisy_result = noisy_simulator.run(
            circuit, shots=shots, seed_simulator=seed
        ).result()
        return BatchCounts(
            distribution_no_noise=dict(ideal_result.get_counts()),
            distribution_with_noise=dict(noisy_result.get_counts()),
        )

    def _validate_batch_shots(self, machine: MachineCharacteristic, shots: int) -> int:
        """Validate and normalize shots before creating either simulator."""
        if not isinstance(shots, Integral) or isinstance(shots, bool) or shots <= 0:
            raise ValueError("Batch shots must be a positive integer.")
        shots = int(shots)
        limit = self.max_shots(machine)
        if limit is not None and shots > limit:
            raise ValueError(
                f"Batch requests {shots} shots, exceeding machine "
                f"'{machine.name}' limit of {limit}."
            )
        return shots
