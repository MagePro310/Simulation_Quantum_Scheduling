"""Job dispatcher: select jobs from queue based on capacity and dependencies."""

from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo


class JobDispatcher:
    """Dispatch jobs from queue to active execution."""

    @staticmethod
    def dispatch_jobs(
        now: float,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        queue: list[str],
        active: list[str],
        capacity: int,
        queue_policy: str,
    ) -> list[str]:
        """Select jobs from queue based on capacity, dependencies, and policy.

        Returns:
            Updated active job list
        """
        # Keep running jobs with remaining shots
        active_jobs = [name for name in active if results[name].status == "RUNNING"]
        active_qubits = sum(
            scheduler_job[name].job_information.circuit.num_qubits
            for name in active_jobs
        )

        # Try to add new jobs from queue
        to_remove = []
        for job_name in queue:
            job = scheduler_job[job_name]
            info = job.job_information
            result = results[job_name]

            if result.status != "PENDING":
                to_remove.append(job_name)
                continue

            # Check arrival time
            if now < (info.arrival_time or 0):
                if queue_policy == "strict":
                    break
                continue

            # Check dependencies
            deps_ready = all(
                results[dep_name].status == "SUCCEEDED"
                for dep_info in job.depends_on
                for dep_name, dep_job in scheduler_job.items()
                if dep_job.job_information is dep_info
            )
            if not deps_ready:
                if queue_policy == "strict":
                    break
                continue

            # Check capacity
            if active_qubits + info.circuit.num_qubits > capacity:
                if queue_policy == "strict":
                    break
                continue

            # Dispatch
            active_jobs.append(job_name)
            active_qubits += info.circuit.num_qubits
            to_remove.append(job_name)

        # Update queue
        for name in to_remove:
            queue.remove(name)

        return active_jobs
