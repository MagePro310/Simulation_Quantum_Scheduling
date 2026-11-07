import sys
from pathlib import Path

# Ensure project root is available in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.component.dataclass.job_info import JobInfo


class EstimatedTime:
    """
    Class to estimate the execution time of a quantum job on a given machine.
    """
    def estimate_execution_time_without_machine(self, job_info: JobInfo) -> float:
        """
        Estimate the execution time of a quantum job without considering the machine's characteristics.
        
        Args:
            job_info: The job information containing the quantum circuit and other details.

        Returns:
            Estimated execution time in seconds.
        """
        # Placeholder logic for estimating execution time without machine characteristics
        # This should be replaced with actual logic based on the circuit's properties
        value : float = job_info.circuit.depth() * job_info.shots
        return value