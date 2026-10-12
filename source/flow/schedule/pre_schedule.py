"""Pre-schedule phase: ensures physical hardware feasibility by cutting oversized circuits."""

import sys
from typing import Any, Dict

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper


class PreSchedulePhase:
    """Pre-schedule preparation phase for quantum circuits.

    Ensures physical hardware feasibility:
    - ALWAYS executed for oversized circuits (num_qubits > max_capacity).
    - Strategy parameter: exceed_cutting_policy ('greedy' or 'half', default: 'greedy').
    - Calculates target cluster sizes externally and calls the cutting tool.
    - Guarantees 100% of circuits fit within max_capacity (capacity invariant).

    Note: Optional cutting for workload optimization is handled autonomously
    by scheduling algorithms during the algorithm phase.
    """

    def __init__(self, exceed_cutting_policy: str = "greedy"):
        """Initialize PreSchedulePhase with mandatory cutting configuration.

        Args:
            exceed_cutting_policy: Strategy for oversized circuits ('greedy' or 'half').
        """
        self.exceed_cutting_policy = exceed_cutting_policy.lower()

    def set_exceed_cutting_policy(self, policy: str) -> None:
        """Set mandatory cutting policy for oversized circuits: 'greedy' or 'half'."""
        self.exceed_cutting_policy = policy.lower()

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Prepares jobs for scheduling through mandatory exceed cut.

        Args:
            origin_job_info: Dictionary of original JobInfo objects.
            machines: Dictionary of available MachineCharacteristic instances.

        Returns:
            Dictionary of SchedulerJobInfo objects ready for scheduling, all guaranteed
            to satisfy num_qubits <= max_capacity.
        """
        max_capacity = SchedulingCutterHelper.get_max_capacity(machines)
        return self.execute_mandatory_cut(origin_job_info, max_capacity)

    def execute_mandatory_cut(
        self,
        origin_job_info: Dict[str, JobInfo],
        max_capacity: int,
    ) -> Dict[str, SchedulerJobInfo]:
        """Cut all circuits exceeding maximum machine capacity using exceed_cutting_policy."""
        scheduler_job: Dict[str, SchedulerJobInfo] = {}

        for job_name, job_info in origin_job_info.items():
            if self._is_oversized(job_info, max_capacity):
                num_qubits = job_info.num_qubits or (job_info.circuit.num_qubits if job_info.circuit else 0)
                # Calculate cluster sizes outside and pass desired qubit cluster sizes into cutting tool
                mode = "half" if self.exceed_cutting_policy == "half" else "greedy"
                cluster_sizes = SchedulingCutterHelper.calculate_cluster_sizes(
                    num_qubits=num_qubits,
                    target_qubits=max_capacity,
                    mode=mode,
                )
                sub_jobs = SchedulingCutterHelper.cut_job(job_info, cluster_sizes=cluster_sizes)
                scheduler_job.update(sub_jobs)
            else:
                scheduler_job[job_name] = self._wrap_uncut_job(job_info)

        # Invariant check: verify that no circuit exceeds machine capacity
        self._verify_capacity_invariant(scheduler_job, max_capacity)
        return scheduler_job

    @staticmethod
    def _is_oversized(job_info: JobInfo, max_capacity: int) -> bool:
        """Check whether a circuit exceeds machine capacity and requires mandatory cutting."""
        if max_capacity <= 0:
            return False
        qubits = job_info.num_qubits or getattr(job_info.circuit, "num_qubits", 0)
        return qubits > max_capacity

    @staticmethod
    def _wrap_uncut_job(job_info: JobInfo) -> SchedulerJobInfo:
        """Wrap an uncut JobInfo into a SchedulerJobInfo."""
        return SchedulerJobInfo(
            job_information=job_info,
            assigned_machine=None,
            dispatch_order=None,
            depends_on=None,
        )

    @staticmethod
    def _verify_capacity_invariant(
        scheduler_jobs: Dict[str, SchedulerJobInfo],
        max_capacity: int,
    ) -> None:
        """Validate invariant: no job exceeds maximum machine capacity after PreSchedulePhase."""
        if max_capacity <= 0:
            return

        for name, job in scheduler_jobs.items():
            qubits = getattr(job.job_information, "num_qubits", 0) or getattr(getattr(job.job_information, "circuit", None), "num_qubits", 0)
            if qubits > max_capacity:
                raise ValueError(
                    f"Invariant violated: job '{name}' has {qubits} qubits, "
                    f"exceeding max capacity {max_capacity}."
                )