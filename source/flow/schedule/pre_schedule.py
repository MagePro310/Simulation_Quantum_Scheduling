"""Pre-schedule phase: prepares and cuts circuits before scheduling."""

import sys
from typing import Any, Dict

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.flow.schedule.circuit_cutter import CircuitCutter


class PreSchedulePhase:
    """Prepares jobs for scheduling, cutting circuits that exceed machine capacities."""

    def __init__(
        self,
        cutting_policy: str = "greedy",
        cutting_scope: str = "exceed",
        cut_all: bool | None = None,
    ):
        self.cutting_policy = cutting_policy.lower()
        if cut_all is not None:
            self.cutting_scope = "all" if cut_all else "exceed"
        else:
            self.cutting_scope = cutting_scope.lower()
        self.circuit_cutter = CircuitCutter()

    # -------------------------------------------------------------------------
    # Option Functions (Configuration)
    # -------------------------------------------------------------------------

    def set_cutting_scope(self, scope: str) -> None:
        """Option function to set cutting scope: 'all' (all circuits) or 'exceed' (only circuits > max capacity)."""
        self.cutting_scope = scope.lower()

    def set_cut_all(self, cut_all: bool = True) -> None:
        """Option function to toggle cutting all circuits (True) vs only exceeding capacity (False)."""
        self.cutting_scope = "all" if cut_all else "exceed"

    def set_cutting_policy(self, policy: str) -> None:
        """Option function to set cutting policy: 'greedy' or 'half'."""
        self.cutting_policy = policy.lower()

    def configure_cutting(
        self,
        policy: str | None = None,
        scope: str | None = None,
        cut_all: bool | None = None,
    ) -> None:
        """Option function to configure circuit cutting policy and scope."""
        if policy is not None:
            self.set_cutting_policy(policy)
        if cut_all is not None:
            self.set_cut_all(cut_all)
        elif scope is not None:
            self.set_cutting_scope(scope)

    # -------------------------------------------------------------------------
    # Execution Pipeline
    # -------------------------------------------------------------------------

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Prepares jobs for scheduling and applies circuit cutting if necessary.

        Args:
            origin_job_info: Dictionary of original JobInfo objects.
            machines: Dictionary of available MachineCharacteristic instances.

        Returns:
            Dictionary of SchedulerJobInfo objects ready for scheduling.
        """
        max_capacity = self._get_max_capacity(machines)
        policy_name = "half" if self.cutting_policy == "half" else "greedy"
        scheduler_job: Dict[str, SchedulerJobInfo] = {}

        for job_name, job_info in origin_job_info.items():
            should_cut, force_cut = self._determine_cutting_action(job_info, max_capacity, policy_name)

            if should_cut:
                sub_jobs = self._process_cut_job(job_info, max_capacity, policy_name, force_cut)
                scheduler_job.update(sub_jobs)
            else:
                scheduler_job[job_name] = self._wrap_uncut_job(job_info)

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

    def _determine_cutting_action(
        self,
        job_info: JobInfo,
        max_capacity: int | None,
        policy_name: str,
    ) -> tuple[bool, bool]:
        """Check whether a circuit requires cutting and if it should be force-cut.

        Returns:
            Tuple of (should_cut: bool, force_cut: bool).
        """
        num_qubits = job_info.num_qubits
        if num_qubits is None and job_info.circuit is not None:
            num_qubits = job_info.circuit.num_qubits

        if max_capacity is None or num_qubits is None:
            return False, False

        # If circuit exceeds machine capacity, it MUST be cut
        if num_qubits > max_capacity:
            return True, False

        # In half cutting policy with 'all' scope, cut any circuit with >= 2 qubits
        if policy_name == "half" and self.cutting_scope == "all" and num_qubits >= 2:
            return True, True

        return False, False

    def _process_cut_job(
        self,
        job_info: JobInfo,
        max_capacity: int,
        policy_name: str,
        force_cut: bool,
    ) -> Dict[str, SchedulerJobInfo]:
        """Cut a job into subcircuits and wrap each into SchedulerJobInfo."""
        num_qubits = job_info.num_qubits or (job_info.circuit.num_qubits if job_info.circuit else 0)
        job_name = job_info.job_name

        if force_cut:
            print(f"Applying {policy_name} circuit cutting (all circuits): {job_name} ({num_qubits} qubits)...")
        else:
            print(
                f"Applying {policy_name} circuit cutting: {job_name} ({num_qubits} qubits > "
                f"machine capacity {max_capacity} qubits)..."
            )

        children_jobs = self.circuit_cutter.cut_circuit(
            job_info, max_capacity, policy=policy_name, force_cut=force_cut
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