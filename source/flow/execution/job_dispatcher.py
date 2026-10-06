"""Job dispatcher: queue management, DAG dependency checking, and candidate selection."""

from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo


class JobDispatcher:
    """Manage queue candidate selection and dependency failure cascading."""

    @staticmethod
    def select_jobs(
        now: float,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        queue: list[str],
        active: list[str],
        capacity: int,
        policy: str,
    ) -> list[str]:
        """Select jobs from machine queue that can run at current time.

        Args:
            now: Current simulation timestamp.
            scheduler_job: Dictionary of scheduled job information.
            results: Dictionary of current execution results.
            queue: List of job IDs waiting in machine queue.
            active: List of currently running job IDs on the machine.
            capacity: Physical qubit capacity of the target machine.
            policy: Queue dispatch policy ('strict' vs 'backfill').

        Returns:
            List of job IDs to run in the next batch.
        """
        policy = (policy or "strict").lower()

        active_jobs = [name for name in active if results[name].status == "RUNNING"]
        used_qubits = sum(scheduler_job[name].job_information.circuit.num_qubits for name in active_jobs)

        to_remove = []
        for job_name in queue:
            if results[job_name].status != "PENDING":
                to_remove.append(job_name)
                continue

            info = scheduler_job[job_name].job_information

            # Check arrival time
            if now < (info.arrival_time or 0):
                if policy == "strict":
                    break
                continue

            # Check dependencies
            if not all(
                results[dep_name].status == "SUCCEEDED"
                for dep_info in (scheduler_job[job_name].depends_on or [])
                for dep_name, dep_job in scheduler_job.items()
                if dep_job.job_information is dep_info
            ):
                if policy == "strict":
                    break
                continue

            # Check capacity
            if used_qubits + info.circuit.num_qubits > capacity:
                if policy == "strict":
                    break
                continue

            # Add job to active batch
            active_jobs.append(job_name)
            used_qubits += info.circuit.num_qubits
            to_remove.append(job_name)

        for name in to_remove:
            queue.remove(name)

        return active_jobs

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

