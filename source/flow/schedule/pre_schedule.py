"""Pre-schedule phase: ensures physical hardware feasibility by cutting oversized circuits."""

import sys
from typing import Any, Dict

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.flow.schedule.circuit_cutter import CircuitCutter, SchedulingCutterHelper


class PreSchedulePhase:
    """Pre-schedule preparation phase for quantum circuits.

    Executes a structured 2-stage circuit preparation pipeline:

    Stage 1: Mandatory Exceed Cut (Hardware Feasibility):
        - ALWAYS executed by default for oversized circuits (num_qubits > max_capacity).
        - Strategy parameter: exceed_cutting_policy ('greedy' or 'half', default: 'greedy').
        - Guarantees 100% of circuits fit within max_capacity (capacity invariant).

    Stage 2: Optional Cutting (Workload & Packing Optimization):
        - OPTIONAL (controlled via enable_optional_cutting: bool).
        - Strategy parameter: optional_cutting_policy (default: 'half', extensible).
        - Applied only to remaining uncut circuits (num_qubits >= 2).
        - Preserves already-cut subcircuits from Stage 1 (no nested subcircuits).
    """

    def __init__(
        self,
        exceed_cutting_policy: str = "greedy",
        enable_optional_cutting: bool = False,
        optional_cutting_policy: str = "half",
    ):
        """Initialize PreSchedulePhase with mandatory and optional cutting configurations.

        Args:
            exceed_cutting_policy: Strategy for oversized circuits ('greedy' or 'half').
            enable_optional_cutting: Whether to apply optional cutting to remaining circuits.
            optional_cutting_policy: Strategy for optional cut (default: 'half', extensible).
        """
        self.exceed_cutting_policy = exceed_cutting_policy.lower()
        self.enable_optional_cutting = enable_optional_cutting
        self.optional_cutting_policy = optional_cutting_policy.lower()
        self.circuit_cutter = CircuitCutter()

    # -------------------------------------------------------------------------
    # Configuration Setters
    # -------------------------------------------------------------------------

    def set_exceed_cutting_policy(self, policy: str) -> None:
        """Set mandatory cutting policy for oversized circuits: 'greedy' or 'half'."""
        self.exceed_cutting_policy = policy.lower()

    def set_optional_cutting(self, enable: bool = True, policy: str = "half") -> None:
        """Configure optional cutting stage."""
        self.enable_optional_cutting = enable
        self.optional_cutting_policy = policy.lower()

    # -------------------------------------------------------------------------
    # Execution Pipeline
    # -------------------------------------------------------------------------

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Prepares jobs for scheduling through mandatory exceed cut and optional cut.

        Args:
            origin_job_info: Dictionary of original JobInfo objects.
            machines: Dictionary of available MachineCharacteristic instances.

        Returns:
            Dictionary of SchedulerJobInfo objects ready for scheduling, all guaranteed
            to satisfy num_qubits <= max_capacity.
        """
        max_capacity = self._get_max_capacity(machines)

        # Stage 1: Mandatory Exceed Cut (Always executed for oversized circuits)
        scheduler_job = self.execute_mandatory_cut(origin_job_info, max_capacity)

        # Stage 2: Optional Cut (Executed only if enabled)
        if self.enable_optional_cutting and max_capacity is not None:
            scheduler_job = self.execute_optional_cut(scheduler_job, max_capacity)

        return scheduler_job

    def execute_mandatory_cut(
        self,
        origin_job_info: Dict[str, JobInfo],
        max_capacity: int | None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Cut all circuits exceeding maximum machine capacity using exceed_cutting_policy."""
        policy_name = "half" if self.exceed_cutting_policy == "half" else "greedy"
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

    def execute_optional_cut(
        self,
        scheduler_job: Dict[str, SchedulerJobInfo],
        max_capacity: int,
    ) -> Dict[str, SchedulerJobInfo]:
        """Apply optional_cutting_policy to all eligible uncut circuits."""
        return SchedulingCutterHelper.apply_cutting_to_jobs(
            scheduler_job=scheduler_job,
            max_capacity=max_capacity,
            policy=self.optional_cutting_policy,
            min_qubits=2,
        )


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
        if not max_capacity:
            return False
        qubits = job_info.num_qubits or getattr(job_info.circuit, "num_qubits", 0)
        return qubits > max_capacity

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
        if not max_capacity:
            return

        for name, job in scheduler_jobs.items():
            qubits = getattr(job.job_information, "num_qubits", 0) or getattr(getattr(job.job_information, "circuit", None), "num_qubits", 0)
            if qubits > max_capacity:
                raise ValueError(
                    f"Invariant violated: job '{name}' has {qubits} qubits, "
                    f"exceeding max capacity {max_capacity}."
                )