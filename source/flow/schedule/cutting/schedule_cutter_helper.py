"""Helper module allowing scheduling algorithms to autonomously make cutting decisions."""

from typing import Dict
from source.component.dataclass.job_info import SchedulerJobInfo
from source.flow.schedule.cutting.cutter_pipeline import CircuitCutter


class SchedulingCutterHelper:
    """Provides utilities for scheduling algorithms to cut, chop, and reorganize circuits."""

    @staticmethod
    def apply_half_cut_to_jobs(
        scheduler_job: Dict[str, SchedulerJobInfo],
        max_capacity: int,
        min_qubits: int = 2,
    ) -> Dict[str, SchedulerJobInfo]:
        """Apply half-cut to all eligible uncut circuits in the scheduler job pool.

        This function enables algorithms (e.g. FFD_v2) to proactively chop circuits into
        smaller subcircuits to improve bin packing, reduce makespan, or optimize QPU utilization.

        Args:
            scheduler_job: Current dictionary of SchedulerJobInfo.
            max_capacity: Maximum qubit capacity of the available machines.
            min_qubits: Minimum number of qubits required for a circuit to be split (default: 2).

        Returns:
            New dictionary of SchedulerJobInfo where eligible uncut circuits are replaced
            by their generated child subcircuits.
        """
        cutter = CircuitCutter()
        updated_jobs: Dict[str, SchedulerJobInfo] = {}

        for job_name, s_job in scheduler_job.items():
            job_info = s_job.job_information
            if job_info is None:
                updated_jobs[job_name] = s_job
                continue

            num_qubits = job_info.num_qubits
            if num_qubits is None and job_info.circuit is not None:
                num_qubits = job_info.circuit.num_qubits

            # Skip jobs that are already cut subcircuits (preserve 1-level parent-child relationship)
            # or jobs that have fewer qubits than min_qubits
            is_already_cut = job_info.parentJob is not None
            can_be_split = num_qubits is not None and num_qubits >= min_qubits

            if not is_already_cut and can_be_split:
                print(
                    f"[Scheduling Cutting Decision] Applying half-cut chopping: "
                    f"{job_name} ({num_qubits} qubits)..."
                )
                children_jobs = cutter.cut_circuit(
                    parent_job=job_info,
                    max_capacity=max_capacity,
                    policy="half",
                    force_cut=True,
                )
                sub_sizes = [c.num_qubits for c in children_jobs.values()]
                print(
                    f"  -> Chopped {job_name} into {len(children_jobs)} subcircuits: "
                    f"{sub_sizes} qubits (overhead: {job_info.cutting_overhead:g})"
                )

                for child_name, child_job in children_jobs.items():
                    updated_jobs[child_name] = SchedulerJobInfo(
                        job_information=child_job,
                        assigned_machine=None,
                        dispatch_order=None,
                        depends_on=None,
                    )
            else:
                updated_jobs[job_name] = s_job

        return updated_jobs

