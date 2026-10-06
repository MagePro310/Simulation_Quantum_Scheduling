"""Half cutting policy: recursively splits circuits into balanced halves."""

from source.flow.schedule.cutting.base_policy import BaseCuttingPolicy


class HalfCuttingPolicy(BaseCuttingPolicy):
    """Partition circuits into balanced halves [ceil(n/2), floor(n/2)].

    Subcircuits are recursively split until each subcircuit fits within max_capacity.
    """

    name: str = "half"

    def get_partition_labels(
        self,
        num_qubits: int,
        max_capacity: int,
        force_cut: bool = False,
    ) -> list[str]:
        """Generate balanced partition labels for half cut."""
        sizes = self.calculate_subcircuit_sizes(num_qubits, max_capacity, force_cut=force_cut)
        return self.convert_sizes_to_labels(sizes)

    def calculate_subcircuit_sizes(
        self,
        num_qubits: int,
        max_capacity: int,
        force_cut: bool = False,
    ) -> list[int]:
        """Calculate list of subcircuit qubit counts by recursive half-splitting.

        Args:
            num_qubits: Number of qubits to partition.
            max_capacity: Machine capacity limit.
            force_cut: If True, split even when num_qubits <= max_capacity (requires num_qubits >= 2).

        Returns:
            List of integers representing the size of each subcircuit.
            Example:
                7 qubits, capacity 5 -> [4, 3]
                12 qubits, capacity 5 -> [3, 3, 3, 3]
                2 qubits, capacity 5, force_cut=True -> [1, 1]
        """
        if not force_cut and num_qubits <= max_capacity:
            return [num_qubits]
        if num_qubits < 2:
            return [num_qubits]

        left, right = self._split_qubits_in_half(num_qubits)
        # After initial split, subsequent sub-branches only split if they exceed max_capacity
        return (
            self.calculate_subcircuit_sizes(left, max_capacity, force_cut=False)
            + self.calculate_subcircuit_sizes(right, max_capacity, force_cut=False)
        )

    @staticmethod
    def _split_qubits_in_half(num_qubits: int) -> tuple[int, int]:
        """Helper function: split n qubits into balanced halves (left >= right)."""
        left = (num_qubits + 1) // 2
        right = num_qubits // 2
        return (left, right)
