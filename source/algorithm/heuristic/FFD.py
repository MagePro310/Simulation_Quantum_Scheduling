from dataclasses import dataclass

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.help_function.estimated_time import EstimatedTime


@dataclass
class FFDBin:
    """A group of jobs that share one machine's qubit capacity.

    Each packing round adds one empty bin for every machine. The round index
    identifies a copy of that machine's capacity, not a start time.

    Args:
        machine_name: Name of the machine.
        num_qubits: Total qubit capacity of the machine.
        round_index: The packing round index.
        jobs: Dictionary of SchedulerJobInfo objects assigned to this bin.
        used_qubits: Total qubits used by the jobs in this bin.
    """

    machine_name: str
    num_qubits: int
    round_index: int
    jobs: dict[str, SchedulerJobInfo]
    used_qubits: int

    @property
    def remaining_qubits(self) -> int:
        return self.num_qubits - self.used_qubits


class FFD:
    """First Fit Decreasing: place the largest jobs first.

    Start reading at execute() for the overall scheduling flow.
    Read pack() for the FFD algorithm itself.

    Dictionary keys identify jobs and machines. Machine insertion order is the
    first-fit preference; equally wide jobs retain their insertion order.
    Arrival times and priorities do not affect this batch schedule.
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

        # 1. Group jobs into machine bins using First Fit Decreasing.
        packed_bins = self.pack(scheduler_job, machines)

        # 2. Use estimated durations to order the occupied bins by start time.
        bins_in_execution_order = self._order_bins_by_start_time(
            packed_bins, scheduler_job, machines
        )

        # 3. Write each job's machine, dispatch order, and dependencies.
        self._assign_jobs(bins_in_execution_order, machines)
        return scheduler_job

    def pack(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> list[FFDBin]:
        """Group jobs into bins without changing the jobs or machines.

        Example: one 6-qubit machine, jobs A=4, B=3, C=2 qubits.
            A goes into round 0: [A], with 2 qubits left.
            B cannot fit there, so open round 1: [B].
            C fits back into round 0: [A, C].

        Earlier bins stay available until full. Return full bins first, followed
        by bins with free capacity, including empty bins.
        """
        # 1. Read how many qubits each job needs.
        job_qubits: dict[str, int] = {}
        for job_name, job in scheduler_job.items():
            job_info = job.job_information
            if job_info.num_qubits is not None:
                job_qubits[job_name] = job_info.num_qubits
            else:
                job_qubits[job_name] = job_info.circuit.num_qubits

        # 2. Decreasing: largest jobs first; equal sizes keep their input order.
        jobs_largest_first = sorted(
            scheduler_job,
            key=lambda job_name: job_qubits[job_name],
            reverse=True,
        )

        # 3. Start round 0 with one empty bin per machine.
        round_index = 0
        open_bins = self._create_round_bins(machines, round_index)
        full_bins: list[FFDBin] = []

        # 4. First fit: place each job in the first bin with enough free qubits.
        for job_name in jobs_largest_first:
            required_qubits = job_qubits[job_name]
            selected_bin = None

            # Search ALL open bins, including those from earlier rounds.
            for candidate_bin in open_bins:
                if required_qubits <= candidate_bin.remaining_qubits:
                    selected_bin = candidate_bin
                    break

            # No existing bin fits: add one fresh bin for every machine.
            if selected_bin is None:
                round_index += 1
                new_bins = self._create_round_bins(machines, round_index)
                open_bins.extend(new_bins)

                for candidate_bin in new_bins:
                    if required_qubits <= candidate_bin.remaining_qubits:
                        selected_bin = candidate_bin
                        break

            # Add the original job object and consume its qubit capacity.
            selected_bin.jobs[job_name] = scheduler_job[job_name]
            selected_bin.used_qubits += required_qubits

            # Full bins cannot accept another job; partially filled bins stay open.
            if selected_bin.remaining_qubits == 0:
                open_bins.remove(selected_bin)
                full_bins.append(selected_bin)

        # 5. Keep the packing result order: full bins, then remaining open bins.
        return full_bins + open_bins

    @staticmethod
    def _create_round_bins(
        machines: dict[str, MachineCharacteristic], round_index: int
    ) -> list[FFDBin]:
        """Create one empty bin per machine, preserving machine order."""
        return [
            FFDBin(
                machine_name=machine_name,
                num_qubits=machine.capacity,
                round_index=round_index,
                jobs={},
                used_qubits=0,
            )
            for machine_name, machine in machines.items()
        ]

    def _order_bins_by_start_time(
        self,
        packed_bins: list[FFDBin],
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> list[FFDBin]:
        """Each machine runs its bins sequentially; different machines may overlap.

        Jobs in a bin share a start time, so the bin lasts as long as its longest
        job. These times only order bins; they are not stored on the jobs.
        """
        job_durations = {
            job_name: self._estimated_duration(job)
            for job_name, job in scheduler_job.items()
        }
        machine_available_at = {machine_name: 0.0 for machine_name in machines}
        bins_by_start_time: list[tuple[float, FFDBin]] = []

        # pack() returns full bins first. Restore round order before timing them.
        bins_by_round = sorted(packed_bins, key=lambda packed_bin: packed_bin.round_index)
        for packed_bin in bins_by_round:
            if not packed_bin.jobs:
                continue
            machine_name = packed_bin.machine_name
            start_time = machine_available_at[machine_name]
            bin_duration = max(job_durations[job_name] for job_name in packed_bin.jobs)
            machine_available_at[machine_name] = start_time + bin_duration
            bins_by_start_time.append((start_time, packed_bin))
        bins_by_start_time.sort(key=lambda item: item[0])
        return [packed_bin for _, packed_bin in bins_by_start_time]

    def _assign_jobs(
        self,
        bins_in_execution_order: list[FFDBin],
        machines: dict[str, MachineCharacteristic],
    ) -> None:
        """Update jobs with the dispatch sequence and barriers between bins."""
        next_dispatch_order = {machine_name: 0 for machine_name in machines}
        previous_bin_jobs: dict[str, list[JobInfo]] = {
            machine_name: [] for machine_name in machines
        }
        for packed_bin in bins_in_execution_order:
            machine_name = packed_bin.machine_name

            # All jobs here wait for the preceding bin on this same machine.
            # Existing dependencies are also retained.
            for job in packed_bin.jobs.values():
                dependencies = self._merge_dependencies(
                    job.depends_on or [], previous_bin_jobs[machine_name]
                )
                job.assigned_machine = machine_name
                job.dispatch_order = next_dispatch_order[machine_name]
                job.depends_on = dependencies
                next_dispatch_order[machine_name] += 1

            # Update only after the whole bin, so its jobs can run together.
            previous_bin_jobs[machine_name] = [
                job.job_information
                for job in packed_bin.jobs.values()
                if job.job_information is not None
            ]

    @staticmethod
    def _estimated_duration(job: SchedulerJobInfo) -> float:
        """Estimate duration using default shots and a minimum depth of one."""
        return EstimatedTime().estimate_execution_time_without_machine(job.job_information)

    @staticmethod
    def _merge_dependencies(
        existing_dependencies: list[JobInfo | None],
        previous_bin_jobs: list[JobInfo],
    ) -> list[JobInfo | None]:
        """Keep dependency order and deduplicate by identity, not dataclass values."""
        dependencies: list[JobInfo | None] = []
        seen_ids: set[int] = set()
        for dependency in existing_dependencies + previous_bin_jobs:
            dependency_id = id(dependency)
            if dependency_id not in seen_ids:
                dependencies.append(dependency)
                seen_ids.add(dependency_id)
        return dependencies
