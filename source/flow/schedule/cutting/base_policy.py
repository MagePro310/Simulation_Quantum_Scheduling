"""Base interface for circuit cutting partition policies."""

from abc import ABC, abstractmethod


class BaseCuttingPolicy(ABC):
    """Abstract base class for circuit cutting partition strategies."""

    name: str = "base"

    @abstractmethod
    def get_partition_labels(
        self,
        num_qubits: int,
        max_capacity: int,
        force_cut: bool = False,
    ) -> list[str]:
        """Generate partition labels (e.g. ['A', 'A', 'B', 'B']) for each qubit.

        Args:
            num_qubits: Total number of qubits in the circuit.
            max_capacity: Maximum qubit capacity supported by target machines.
            force_cut: If True, forces partitioning even if num_qubits <= max_capacity.

        Returns:
            List of string partition labels for qubits 0 to num_qubits - 1.
        """
        pass

    def convert_sizes_to_labels(self, partition_sizes: list[int]) -> list[str]:
        """Utility helper: Convert a list of subcircuit sizes into alphabet partition labels.

        For example:
            [4, 3] -> ['A', 'A', 'A', 'A', 'B', 'B', 'B']
            [1, 1] -> ['A', 'B']
        """
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        labels: list[str] = []
        for idx, size in enumerate(partition_sizes):
            partition_letter = letters[idx % len(letters)]
            labels.extend([partition_letter] * size)
        return labels
