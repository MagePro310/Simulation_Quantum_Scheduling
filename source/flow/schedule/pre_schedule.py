"""Pre-schedule phase: ensures physical hardware feasibility by cutting oversized circuits."""

import sys
from typing import Any, Dict

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.flow.schedule.circuit_cutter import CircuitCutter


class PreSchedulePhase:
    """Prepares jobs for scheduling, cutting circuits that exceed machine capacities.

    Responsibilities:
        - Hardware feasibility only: circuits with num_qubits > max_capacity MUST be cut.
        - Supported mandatory policies: 'greedy' (default) or 'half'.
        - Guarantees 100% of output jobs fit within max_capacity (capacity invariant).
        - Circuits that already fit machine capacity remain uncut in this phase.
    """

    def __init__(
        self,
        cutting_policy: str = "greedy",
        **kwargs: Any,
    ):
        """Initialize PreSchedulePhase with mandatory cutting policy.

        Args:
            cutting_policy: Strategy to cut oversized circuits ('greedy' or 'half').
            **kwargs: Ignored keyword arguments for backward compatibility.
        """
        self.cutting_policy = cutting_policy.lower()
        self.circuit_cutter = CircuitCutter()

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def set_cutting_policy(self, policy: str) -> None:
        """Set mandatory cutting policy: 'greedy' or 'half'."""
        self.cutting_policy = policy.lower()

    # -------------------------------------------------------------------------
    # Execution Pipeline
    # -------------------------------------------------------------------------

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Prepares jobs for scheduling by applying mandatory cutting to oversized circuits.

        Args:
            origin_job_info: Dictionary of original JobInfo objects.
            machines: Dictionary of available MachineCharacteristic instances.

        Returns:
            Dictionary of SchedulerJobInfo objects ready for scheduling, all guaranteed
            to satisfy num_qubits <= max_capacity.
        """
        max_capacity = self._get_max_capacity(machines)
        policy_name = "half" if self.cutting_policy == "half" else "greedy"
        scheduler_job: Dict[str, SchedulerJobInfo] = {}

        for job_name, job_info in origin_job_info.items():
            if self._is_oversized(job_info, max_capacity):
                sub_jobs = self._process_cut_job(job_info, max_capacity, policy_name)
                scheduler_job.update(sub_jobs)
            else:
                scheduler_job[job_name] = self._wrap_uncut_job(job_info)

        # Invariant check: verify that no circuit exceeds machine capacity
        self._verify_capacity_invariant(scheduler_job, max_capacity)
        return scheduler_job

    # -------------------------------------------------------------------------
    # Helper Functions (Single Responsibility)
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_max_capacity(machines: Dict[str, Any] | None) -> int | None:
        """Extract the maximum qubit capacity across all available machines."""
        if not machines:
            return None
        return max(
            (getattr(m, "capacity", 0) for m in machines.values()),
            default=None,
        )

    @staticmethod
    def _is_oversized(job_info: JobInfo, max_capacity: int | None) -> bool:
        """Check whether a circuit exceeds machine capacity and requires mandatory cutting."""
        if max_capacity is None:
            return False

        num_qubits = job_info.num_qubits
        if num_qubits is None and job_info.circuit is not None:
            num_qubits = job_info.circuit.num_qubits

        if num_qubits is None:
            return False

        return num_qubits > max_capacity

    def _process_cut_job(
        self,
        job_info: JobInfo,
        max_capacity: int,
        policy_name: str,
    ) -> Dict[str, SchedulerJobInfo]:
        """Cut an oversized job into subcircuits and wrap each into SchedulerJobInfo."""
        num_qubits = job_info.num_qubits or (job_info.circuit.num_qubits if job_info.circuit else 0)
        job_name = job_info.job_name

        print(
            f"Applying {policy_name} circuit cutting: {job_name} ({num_qubits} qubits > "
            f"machine capacity {max_capacity} qubits)..."
        )

        children_jobs = self.circuit_cutter.cut_circuit(
            job_info, max_capacity, policy=policy_name, force_cut=False
        )
        sub_qubit_sizes = [c.num_qubits for c in children_jobs.values()]
        print(
            f"  -> Cut {job_name} into {len(children_jobs)} subcircuits: "
            f"{sub_qubit_sizes} qubits (overhead: {job_info.cutting_overhead:g})"
        )

        wrapped_sub_jobs: Dict[str, SchedulerJobInfo] = {}
        for child_name, child_job in children_jobs.items():
            wrapped_sub_jobs[child_name] = SchedulerJobInfo(
                job_information=child_job,
                assigned_machine=None,
                dispatch_order=None,
                depends_on=None,
            )
        return wrapped_sub_jobs

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
        max_capacity: int | None,
    ) -> None:
        """Validate invariant: no job exceeds maximum machine capacity after PreSchedulePhase."""
        if max_capacity is None:
            return

        for name, job in scheduler_jobs.items():
            info = job.job_information
            qubits = info.num_qubits if info and info.num_qubits is not None else (
                info.circuit.num_qubits if info and info.circuit else 0
            )
            if qubits > max_capacity:
                raise ValueError(
                    f"Invariant violated: job '{name}' has {qubits} qubits, "
                    f"exceeding max capacity {max_capacity}."
                )