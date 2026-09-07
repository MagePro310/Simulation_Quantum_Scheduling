import sys
from copy import deepcopy
from typing import Dict, List

from qiskit import QuantumCircuit

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo

class PreSchedulePhase:
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
                composed.append(PreSchedulePhase.compose_multiple_circuits(*circuits))

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

            qc_combined = PreSchedulePhase.compose_multiple_circuits(qc_a, qc_b, qc_c)
        """
        if len(circuits) < 2:
            raise ValueError("At least 2 circuits are required for composition")

        result = circuits[0]
        for circuit in circuits[1:]:
            result = circuit.tensor(result)

        return result

    def execute(self, origin_job_info: Dict[str, JobInfo]) -> Dict[str, SchedulerJobInfo]:
        """
        Prepares the jobs for scheduling by deep copying original job info.
        """
        print("Preschedule: Not change")
        scheduler_job: Dict[str, SchedulerJobInfo] = {}
        for job_name, job_info in origin_job_info.items():
            scheduler_job[job_name] = SchedulerJobInfo(job_information=deepcopy(job_info))
        return scheduler_job