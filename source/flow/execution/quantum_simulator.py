"""Quantum simulator execution."""

from source.flow.execution.crosstalk import apply_crosstalk, noisy_simulator
from source.models.execution import BatchCounts, PreparedBatch
from source.models.machine import MachineCharacteristic


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
        """Run the transpiled composite circuit on the backend's noisy simulator, with
        conditional crosstalk channels added (flow/execution/crosstalk.py).

        Only the noisy counts are sampled. The ideal reference is exact and computed
        per job from its own circuit (BatchExecutor), so distribution_no_noise is empty.
        """
        simulator = noisy_simulator(machine.quantum_machine)
        circuit, exposed, two_qubit = apply_crosstalk(
            prepared_batch.transpiled_circuit, machine.quantum_machine, machine.crosstalk_factor
        )
        noisy_result = simulator.run(circuit, shots=shots, seed_simulator=seed).result()

        return BatchCounts(
            distribution_no_noise={},
            distribution_with_noise=dict(noisy_result.get_counts()),
            crosstalk_exposed_gates=exposed,
            two_qubit_gates=two_qubit,
        )
