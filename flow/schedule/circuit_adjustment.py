from qiskit import QuantumCircuit
from typing import Any, Dict, List, Tuple
import sys

sys.path.append('./')

from component.dataclass.job_info import SchedulerJobInfo, TranspiledJob
from qiskit.compiler import transpile

class Circuit_adjustment:
    """
    A class for automatic quantum circuit composition operations.
    Supports combining multiple quantum circuits using tensor product.
    """

    @staticmethod
    def get_circuit_for_compose(scheduler_job: Dict[str, SchedulerJobInfo]) -> List[QuantumCircuit]:
        """Return circuits grouped by overlapping execution windows.

        Jobs whose scheduled intervals overlap are composed together via
        tensor products while non-overlapping jobs remain standalone.

        Args:
            scheduler_job: Dictionary of job name to `SchedulerJobInfo`.

        Returns:
            List of `QuantumCircuit` objects ready for downstream transpilation.
        """

        if not scheduler_job:
            return []

        # Sort jobs by start time to build contiguous overlapping windows.
        jobs = sorted(
            (job for job in scheduler_job.values() if job.job_information),
            key=lambda job: job.scheduled_start_time,
        )

        composed: List[QuantumCircuit] = []
        current_group: List[SchedulerJobInfo] = []
        current_end: float | None = None

        def flush_group() -> None:
            if not current_group:
                return
            circuits = [info.job_information.circuit for info in current_group if info.job_information.circuit]
            if not circuits:
                return
            if len(circuits) == 1:
                composed.append(circuits[0])
            else:
                composed.append(Circuit_adjustment.compose_multiple_circuits(*circuits))

        for job in jobs:
            start = job.scheduled_start_time
            end = job.scheduled_end_time

            if not current_group:
                current_group = [job]
                current_end = end
                continue

            # Overlap occurs when the next job begins before the current window ends.
            if current_end is not None and start < current_end:
                current_group.append(job)
                current_end = max(current_end, end)
            else:
                flush_group()
                current_group = [job]
                current_end = end

        flush_group()
        return composed

    @staticmethod
    def compose_multiple_circuits(*circuits: QuantumCircuit) -> QuantumCircuit:
        """
        Automatically compose multiple quantum circuits using tensor product.
        
        Args:
            *circuits: Variable number of QuantumCircuit objects
            
        Returns:
            QuantumCircuit: Combined circuit using sequential tensor products
            
        Raises:
            ValueError: If less than 2 circuits are provided
            
        Example:
            qc_a = QuantumCircuit(4)
            qc_a.x(0)
            
            qc_b = QuantumCircuit(2, name="qc_b")
            qc_b.y(0)
            
            qc_c = QuantumCircuit(3, name="qc_c")
            qc_c.h(0)
            
            qc_combined = Circuit_adjustment.compose_multiple_circuits(qc_a, qc_b, qc_c)
        """
        if len(circuits) < 2:
            raise ValueError("At least 2 circuits are required for composition")
        
        result = circuits[0]
        for circuit in circuits[1:]:
            result = circuit.tensor(result)
        
        return result
    
    @staticmethod
    def get_qubit_mapping(transpiled_circuit: Any) -> Tuple[Dict[int, int], List[int]]:
        """Return logical→physical qubit mapping and register ordering for a transpiled circuit."""

        layout = getattr(transpiled_circuit, "layout", None)
        if layout is None or layout.initial_layout is None:
            raise ValueError("Transpiled circuit does not contain an initial_layout.")

        virtual_to_physical = layout.initial_layout.get_virtual_bits()
        logical_mapping: Dict[int, int] = {}
        physical_order: List[int] = []

        def _register(bit: Any) -> Any:
            return getattr(bit, "register", getattr(bit, "_register", None))

        def _bit_index(bit: Any) -> int:
            register = _register(bit)
            if register is not None:
                try:
                    return register.index(bit)
                except ValueError:
                    pass
            idx = getattr(bit, "_index", None)
            if idx is None:
                raise ValueError("Unable to determine qubit index.")
            return idx

        def _physical_index(value: Any) -> int:
            if isinstance(value, int):
                return value
            if hasattr(value, "index"):
                return value.index
            idx = getattr(value, "_index", None)
            if idx is None:
                raise ValueError("Unable to determine physical qubit index.")
            return idx

        ordered_virtuals = sorted(
            virtual_to_physical.items(),
            key=lambda item: (
                getattr(_register(item[0]), "name", ""),
                _bit_index(item[0]),
            ),
        )

        for virtual_bit, physical_bit in ordered_virtuals:
            physical_idx = _physical_index(physical_bit)
            physical_order.append(physical_idx)

            register = _register(virtual_bit)
            if register and register.name == "q":
                logical_mapping[_bit_index(virtual_bit)] = physical_idx

        return logical_mapping, physical_order