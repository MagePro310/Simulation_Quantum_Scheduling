from dataclasses import dataclass

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.help_function.estimated_time import EstimatedTime


@dataclass
class LPTMachine:
    """Tracks a machine's assigned jobs and completion time for LPT scheduling.

    Args:
        machine_name: Name of the machine.
        num_qubits: Total qubit capacity of the machine.
        jobs: List of SchedulerJobInfo objects assigned to this machine.
        completion_time: The time when this machine will finish all assigned jobs.
    """

    machine_name: str
    num_qubits: int
    jobs: list[SchedulerJobInfo]
    completion_time: float


class LPT:
    """Longest Processing Time first: assign longest jobs to least-loaded machines.

    Start reading at execute() for the overall scheduling flow.
    Read schedule() for the LPT algorithm itself.

    The LPT algorithm sorts jobs by processing time (longest first), then assigns
    each job to the machine that will finish earliest. This minimizes makespan
    (total schedule length) for parallel machine scheduling.

    Dictionary keys identify jobs and machines. Machine insertion order breaks ties
    when multiple machines have the same completion time.
    Inputs are assumed to be valid, with every job fitting at least one machine.
    """

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Build a schedule and update the original jobs; no circuits run here."""
        if not scheduler_job:
            return scheduler_job

        # 1. Assign jobs to machines using Longest Processing Time first.
        machine_assignments = self.schedule(scheduler_job, machines)

        # 2. Write each job's machine and dispatch order.
        self._assign_jobs(machine_assignments, scheduler_job)
        return scheduler_job

    def schedule(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> list[LPTMachine]:
        """Assign jobs to machines to minimize makespan.

        Example: two machines (M1, M2), jobs A=10s, B=8s, C=5s, D=3s.
            M1 gets A (10s), then C (15s total), then D (18s total).
            M2 gets B (8s).
            Makespan is 18s (max of 18s and 8s).

        Returns list of LPTMachine objects with assigned jobs.
        """
        # 1. Calculate duration for each job.
        job_durations: dict[str, float] = {}
        job_qubits: dict[str, int] = {}
        for job_name, job in scheduler_job.items():
            job_durations[job_name] = self._estimated_duration(job)
            job_info = job.job_information
            if job_info.num_qubits is not None:
                job_qubits[job_name] = job_info.num_qubits
            else:
                job_qubits[job_name] = job_info.circuit.num_qubits

        # 2. Longest first: sort jobs by duration in descending order.
        jobs_longest_first = sorted(
            scheduler_job,
            key=lambda job_name: job_durations[job_name],
            reverse=True,
        )

        # 3. Initialize machine trackers with zero completion time.
        machine_list = [
            LPTMachine(
                machine_name=machine_name,
                num_qubits=machine.capacity,
                jobs=[],
                completion_time=0.0,
            )
            for machine_name, machine in machines.items()
        ]

        # 4. Assign each job to the machine with earliest completion time.
        for job_name in jobs_longest_first:
            required_qubits = job_qubits[job_name]
            job_duration = job_durations[job_name]

            # Find machines that can fit this job.
            eligible_machines = [
                machine for machine in machine_list
                if machine.num_qubits >= required_qubits
            ]

            if not eligible_machines:
                # No machine can fit this job - skip it.
                continue

            # Select the machine with the earliest completion time.
            # If multiple machines tie, the first one in insertion order wins.
            selected_machine = min(
                eligible_machines,
                key=lambda machine: machine.completion_time
            )

            # Assign the job to this machine.
            selected_machine.jobs.append(scheduler_job[job_name])
            selected_machine.completion_time += job_duration

        return machine_list

    def _assign_jobs(
        self,
        machine_assignments: list[LPTMachine],
        scheduler_job: dict[str, SchedulerJobInfo],
    ) -> None:
        """Update jobs with machine assignment and dispatch order.

        Jobs on the same machine run sequentially in the order they were added.
        Each job depends on the previous job on the same machine.
        """
        for machine in machine_assignments:
            previous_job: JobInfo | None = None

            for dispatch_order, job in enumerate(machine.jobs):
                job.assigned_machine = machine.machine_name
                job.dispatch_order = dispatch_order

                # Each job waits for the previous job on this machine.
                if previous_job is not None:
                    job.depends_on = self._merge_dependencies(
                        job.depends_on or [], [previous_job]
                    )
                else:
                    # Initialize depends_on to existing dependencies or empty list.
                    job.depends_on = job.depends_on or []

                previous_job = job.job_information

    @staticmethod
    def _estimated_duration(job: SchedulerJobInfo) -> float:
        """Estimate duration using default shots and a minimum depth of one."""
        return EstimatedTime().estimate_execution_time_without_machine(job.job_information)

    @staticmethod
    def _merge_dependencies(
        existing_dependencies: list[JobInfo | None],
        previous_jobs: list[JobInfo],
    ) -> list[JobInfo | None]:
        """Keep dependency order and deduplicate by identity, not dataclass values."""
        dependencies: list[JobInfo | None] = []
        seen_ids: set[int] = set()
        for dependency in existing_dependencies + previous_jobs:
            dependency_id = id(dependency)
            if dependency_id not in seen_ids:
                dependencies.append(dependency)
                seen_ids.add(dependency_id)
        return dependencies
