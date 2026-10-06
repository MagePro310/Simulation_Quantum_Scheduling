"""Greedy cutting policy: allocates maximum machine capacity chunks first."""

from source.flow.schedule.cutting.base_policy import BaseCuttingPolicy


class GreedyCuttingPolicy(BaseCuttingPolicy):
    """Partition circuits greedily by taking maximum capacity chunks first.

    For example: 7 qubits with capacity 5 yields [5, 2] -> ['A','A','A','A','A','B','B'].
    """

    name: str = "greedy"

    def get_partition_labels(
        self,
        num_qubits: int,
        max_capacity: int,
        force_cut: bool = False,
    ) -> list[str]:
        """Generate partition labels using greedy chunking."""
        sizes = self.calculate_greedy_sizes(num_qubits, max_capacity)
        return self.convert_sizes_to_labels(sizes)

    def calculate_greedy_sizes(
        self,
        num_qubits: int,
        max_capacity: int,
    ) -> list[int]:
        """Calculate list of subcircuit sizes greedily taking max_capacity.

        Args:
            num_qubits: Number of qubits to partition.
            max_capacity: Maximum capacity per chunk.

        Returns:
            List of subcircuit sizes (e.g. [5, 2] or [5, 5, 2]).
        """
        remaining = num_qubits
        sizes: list[int] = []
        while remaining > 0:
            take = min(remaining, max_capacity)
            sizes.append(take)
            remaining -= take
        return sizes
