from dataclasses import dataclass
from typing import Dict

from source.algorithm.heuristic.ffd_qpu import Job, QPU, ffd_pack
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


@dataclass
class FFDBin:
    """One machine's capacity in a packing round, retaining the original jobs."""

    machine_name: str
    num_qubits: int
    round_index: int
    jobs: Dict[str, SchedulerJobInfo]
    used_qubits: int

    @property
    def remaining_qubits(self) -> int:
        return self.num_qubits - self.used_qubits


class FFD:
    """Pack independent jobs and express their schedule as dispatch dependencies.

    Dictionary keys identify jobs and machines. Machine insertion order is the
    first-fit preference; equally wide jobs retain their insertion order.
    Arrival times and priorities do not affect this batch schedule.
    """

    @staticmethod
    def _job_qubits(job_name: str, job: SchedulerJobInfo) -> int:
        information = job.job_information
        if information is None:
            raise ValueError(f"Job {job_name!r} has no job information")
        width = information.num_qubits
        if width is None and information.circuit is not None:
            width = information.circuit.num_qubits
        if type(width) is not int or width <= 0:
            raise ValueError(f"Job {job_name!r} must have a positive integer qubit count")
        return width

    def pack(
        self,
        scheduler_job: Dict[str, SchedulerJobInfo],
        machines: Dict[str, MachineCharacteristic],
    ) -> list[FFDBin]:
        """Return full bins followed by open bins without modifying either input.

        Reuse the simulation's packing algorithm, including empty machine copies
        and backfilling earlier rounds. Reject jobs that cannot fit any machine.
        """
        if not machines:
            if scheduler_job:
                raise ValueError("At least one machine is required to schedule jobs")
            return []

        jobs = [
            Job(name, self._job_qubits(name, job))
            for name, job in scheduler_job.items()
        ]
        qpus = [QPU(name, machine.capacity) for name, machine in machines.items()]
        return [
            FFDBin(
                machine_name=packed.qpu.name,
                num_qubits=packed.qpu.num_qubits,
                round_index=packed.copy_index,
                jobs={job.name: scheduler_job[job.name] for job in packed.jobs},
                used_qubits=packed.used_qubits,
            )
            for packed in ffd_pack(jobs, qpus)
        ]

    @staticmethod
    def _estimated_duration(job_name: str, job: SchedulerJobInfo) -> float:
        information = job.job_information
        if information is None:
            raise ValueError(f"Job {job_name!r} has no job information")
        shots = 1024 if information.shots is None else information.shots
        if type(shots) is not int or shots <= 0:
            raise ValueError(f"Job {job_name!r} must have a positive integer shot count")
        depth = information.circuit.depth() if information.circuit is not None else 1
        return float(max(1, depth) * shots)

    def execute(
        self,
        scheduler_job: Dict[str, SchedulerJobInfo],
        machines: Dict[str, MachineCharacteristic],
    ) -> Dict[str, SchedulerJobInfo]:
        """Update and return the original jobs using the existing dataclass fields.

        Each bin runs for its longest estimated job duration, with independent
        machine clocks starting at zero. Convert these internal intervals into a
        zero-based dispatch order per machine and dependencies on every job in
        the preceding occupied bin on that machine. Jobs sharing an interval can
        run concurrently. No start/end attributes are added to the input objects.

        Dependencies contain the original JobInfo objects. Existing dependencies
        are retained; they do not influence packing of this independent batch.
        """
        if not scheduler_job:
            return scheduler_job

        bins = self.pack(scheduler_job, machines)
        # Validate all durations before changing any scheduling information.
        durations = {
            name: self._estimated_duration(name, job)
            for name, job in scheduler_job.items()
        }
        available_time = {name: 0.0 for name in machines}
        intervals: list[tuple[float, float, FFDBin]] = []
        # Full bins can close before an earlier round's partially occupied bin.
        for packed in sorted(bins, key=lambda item: item.round_index):
            if not packed.jobs:
                continue
            start_time = available_time[packed.machine_name]
            end_time = start_time + max(durations[name] for name in packed.jobs)
            intervals.append((start_time, end_time, packed))
            available_time[packed.machine_name] = end_time

        dispatch_order = {name: 0 for name in machines}
        previous_jobs: Dict[str, list[JobInfo]] = {name: [] for name in machines}
        for _, _, packed in sorted(intervals, key=lambda item: item[0]):
            machine_name = packed.machine_name
            for job in packed.jobs.values():
                dependencies: list[JobInfo | None] = []
                seen: set[int] = set()
                for predecessor in (job.depends_on or []) + previous_jobs[machine_name]:
                    if id(predecessor) not in seen:
                        dependencies.append(predecessor)
                        seen.add(id(predecessor))
                job.assigned_machine = machine_name
                job.dispatch_order = dispatch_order[machine_name]
                job.depends_on = dependencies
                dispatch_order[machine_name] += 1
            previous_jobs[machine_name] = [
                job.job_information
                for job in packed.jobs.values()
                if job.job_information is not None
            ]
        print(scheduler_job)
        return scheduler_job
