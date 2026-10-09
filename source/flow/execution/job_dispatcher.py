"""Job dispatcher: queue management, DAG dependency checking, and candidate selection.

Handles candidate selection for quantum machines using configurable dispatching strategies:
- 'strict': Preserves strict Head-of-Line ordering. If the leading job cannot run, stops immediately.
- 'backfill': Skips blocked or oversized leading jobs to fit smaller queued jobs into remaining capacity.
"""

from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo


class JobDispatcher:
    """Manage queue candidate selection and dependency failure cascading."""

    @classmethod
    def select_jobs(
        cls,
        now: float,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        queue: list[str],
        active: list[str],
        capacity: int,
        policy: str,
    ) -> list[str]:
        """Select jobs from machine queue that can run at current simulation time.

        Args:
            now: Current simulation timestamp.
            scheduler_job: Dictionary of scheduled job information.
            results: Dictionary of current execution results.
            queue: List of job IDs waiting in machine queue (mutated by removing selected jobs).
            active: List of currently running job IDs on the machine.
            capacity: Physical qubit capacity of the target machine.
            policy: Queue dispatch policy ('strict' vs 'backfill').

        Returns:
            List of job IDs to run in the next batch.
        """
        policy_name = (policy or "strict").lower()
        active_jobs = [name for name in active if results[name].status == "RUNNING"]
        used_qubits = sum(scheduler_job[name].job_information.circuit.num_qubits for name in active_jobs)

        if policy_name == "backfill":
            return cls._select_backfill(now, scheduler_job, results, queue, active_jobs, used_qubits, capacity)
        return cls._select_strict(now, scheduler_job, results, queue, active_jobs, used_qubits, capacity)

    @classmethod
    def _select_strict(
        cls,
        now: float,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        queue: list[str],
        active_jobs: list[str],
        used_qubits: int,
        capacity: int,
    ) -> list[str]:
        """Strict dispatch: stops immediately when head of queue cannot proceed (Head-of-Line)."""
        to_remove = []
        for job_name in queue:
            if results[job_name].status != "PENDING":
                to_remove.append(job_name)
                continue

            # If any condition fails, stop scanning immediately
            if not cls._is_job_ready(now, job_name, scheduler_job, results):
                break

            qubits_needed = scheduler_job[job_name].job_information.circuit.num_qubits
            if used_qubits + qubits_needed > capacity:
                break

            # Job is ready and fits capacity
            active_jobs.append(job_name)
            used_qubits += qubits_needed
            to_remove.append(job_name)

        for name in to_remove:
            queue.remove(name)

        return active_jobs

    @classmethod
    def _select_backfill(
        cls,
        now: float,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        queue: list[str],
        active_jobs: list[str],
        used_qubits: int,
        capacity: int,
    ) -> list[str]:
        """Backfill dispatch: skips blocked jobs and searches for smaller eligible jobs to fill capacity."""
        to_remove = []
        for job_name in queue:
            if results[job_name].status != "PENDING":
                to_remove.append(job_name)
                continue

            # If not ready, skip this job and continue searching behind it
            if not cls._is_job_ready(now, job_name, scheduler_job, results):
                continue

            qubits_needed = scheduler_job[job_name].job_information.circuit.num_qubits
            if used_qubits + qubits_needed > capacity:
                continue

            # Job is ready and fits remaining capacity
            active_jobs.append(job_name)
            used_qubits += qubits_needed
            to_remove.append(job_name)

        for name in to_remove:
            queue.remove(name)

        return active_jobs

    @staticmethod
    def _is_job_ready(
        now: float,
        job_name: str,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
    ) -> bool:
        """Check whether a job satisfies both arrival time and DAG dependency constraints."""
        info = scheduler_job[job_name].job_information

        # 1. Arrival time constraint
        if now < (info.arrival_time or 0):
            return False

        # 2. DAG dependencies constraint (all parents must be SUCCEEDED)
        dependencies = scheduler_job[job_name].depends_on or []
        for dep_info in dependencies:
            for dep_name, dep_job in scheduler_job.items():
                if dep_job.job_information is dep_info:
                    if results[dep_name].status != "SUCCEEDED":
                        return False

        return True

    @staticmethod
    def block_failed_dependents(
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
    ) -> None:
        """Mark jobs as BLOCKED if their dependencies failed or were blocked.

        Cascades recursively through the dependency DAG until no further status changes occur.
        """
        while True:
            changed = False
            for job_name, job in scheduler_job.items():
                if results[job_name].status != "PENDING":
                    continue

                failed_deps = [
                    dep_name
                    for dep_info in (job.depends_on or [])
                    for dep_name, dep_job in scheduler_job.items()
                    if dep_job.job_information is dep_info and results[dep_name].status in {"FAILED", "BLOCKED"}
                ]

                if failed_deps:
                    results[job_name].status = "BLOCKED"
                    results[job_name].error_reason = f"Dependencies failed: {failed_deps}"
                    changed = True

            if not changed:
                break
