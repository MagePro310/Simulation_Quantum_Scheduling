"""Helper module providing a tool library for scheduling algorithms and pre-scheduling to cut circuits."""

import math
from typing import Any, Dict, List
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.flow.schedule.cutting.cutter_pipeline import CircuitCutter


class SchedulingCutterHelper:
    """Provides tools for cutting circuits and automatically updating parameters and constraints."""

    # Reusable shared CircuitCutter instance to avoid repetitive object instantiations
    _cutter: CircuitCutter = CircuitCutter()

    @staticmethod
    def get_max_capacity(machines: Dict[str, Any] | None) -> int:
        """Extract the maximum qubit capacity across available machines."""
        if not machines:
            return 0
        return max((getattr(m, "capacity", 0) for m in machines.values()), default=0)

    @staticmethod
    def can_cut(job: SchedulerJobInfo | JobInfo, min_qubits: int = 2) -> bool:
        """Check if a circuit is eligible for cutting.

        Eligible circuits must be uncut root circuits (parentJob is None) and have
        qubits >= min_qubits.
        """
        job_info = job.job_information if isinstance(job, SchedulerJobInfo) else job
        if not job_info:
            return False
        qubits = getattr(job_info, "num_qubits", 0) or getattr(getattr(job_info, "circuit", None), "num_qubits", 0)
        return job_info.parentJob is None and qubits >= min_qubits

    @classmethod
    def estimate_overhead(
        cls,
        job: SchedulerJobInfo | JobInfo,
        cluster_sizes: List[int] | int | None = None,
    ) -> float:
        """Estimate QPD sampling overhead factor before committing to cut.

        Args:
            job: SchedulerJobInfo or JobInfo.
            cluster_sizes: Desired partition sizes (list of ints or integer target).

        Returns:
            Sampling overhead (float, e.g. 9.0 for 1 cut, 81.0 for 2 cuts). Returns 0.0 if not cuttable.
        """
        job_info = job.job_information if isinstance(job, SchedulerJobInfo) else job
        if not job_info or not job_info.circuit or not cls.can_cut(job):
            return 0.0

        num_qubits = getattr(job_info, "num_qubits", 0) or getattr(job_info.circuit, "num_qubits", 0)

        if cluster_sizes is None:
            half = math.ceil(num_qubits / 2)
            resolved_sizes = [half, num_qubits - half]
        elif isinstance(cluster_sizes, int):
            resolved_sizes = cls.calculate_cluster_sizes(num_qubits, target_qubits=cluster_sizes)
        else:
            resolved_sizes = list(cluster_sizes)

        if sum(resolved_sizes) != num_qubits:
            return 0.0

        return cls._cutter.estimate_overhead_by_partition_sizes(
            parent_job=job_info,
            partition_sizes=resolved_sizes,
        )

    @staticmethod
    def calculate_cluster_sizes(
        num_qubits: int,
        target_qubits: int,
        mode: str = "balanced",
    ) -> List[int]:
        """Calculate desired cluster sizes for cutting a circuit.

        Args:
            num_qubits: Total number of qubits in the circuit.
            target_qubits: Upper bound or target capacity for each subcircuit.
            mode: 'balanced' (divides into balanced halves/pieces) or 'greedy' (packs target_qubits first).

        Returns:
            List of integers representing the qubit sizes of each subcircuit.
        """
        if num_qubits <= target_qubits:
            # When cutting a circuit that already fits within target_qubits:
            # Default to splitting into two balanced halves
            half = math.ceil(num_qubits / 2)
            return [half, num_qubits - half]

        if mode.lower() == "greedy":
            sizes = []
            remaining = num_qubits
            while remaining > target_qubits:
                sizes.append(target_qubits)
                remaining -= target_qubits
            if remaining > 0:
                sizes.append(remaining)
            return sizes

        # Balanced (default):
        num_parts = math.ceil(num_qubits / target_qubits)
        base = num_qubits // num_parts
        remainder = num_qubits % num_parts
        return [base + (1 if i < remainder else 0) for i in range(num_parts)]

    @classmethod
    def cut_job(
        cls,
        job: SchedulerJobInfo | JobInfo,
        cluster_sizes: List[int] | int | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Cut a single circuit job and automatically update all constraints and metadata.

        Args:
            job: SchedulerJobInfo or JobInfo to be cut.
            cluster_sizes: Either explicit list of partition sizes (e.g. [5, 2] or [4, 3]),
                           or an integer target_qubits (e.g. 5), or None (defaults to splitting in half).

        Returns:
            Dictionary of {child_name: SchedulerJobInfo} with updated constraints and links.
        """
        s_job = job if isinstance(job, SchedulerJobInfo) else SchedulerJobInfo(job_information=job)
        job_info = s_job.job_information
        if not job_info or not job_info.circuit:
            raise ValueError(f"Job {getattr(job_info, 'job_name', 'unknown')} has no valid circuit to cut.")

        num_qubits = job_info.num_qubits or job_info.circuit.num_qubits
        cutter = cls._cutter

        # Resolve cluster sizes
        if cluster_sizes is None:
            half = math.ceil(num_qubits / 2)
            resolved_sizes = [half, num_qubits - half]
        elif isinstance(cluster_sizes, int):
            resolved_sizes = cls.calculate_cluster_sizes(num_qubits, target_qubits=cluster_sizes)
        else:
            resolved_sizes = list(cluster_sizes)

        print(
            f"[Circuit Cutting Tool] Cutting {job_info.job_name} ({num_qubits} qubits) "
            f"into clusters {resolved_sizes}..."
        )

        children_jobs = cutter.cut_by_partition_sizes(
            parent_job=job_info,
            partition_sizes=resolved_sizes,
        )

        sub_sizes = [c.num_qubits for c in children_jobs.values()]
        print(
            f"  -> Generated {len(children_jobs)} subcircuits: "
            f"{sub_sizes} qubits (overhead: {job_info.cutting_overhead:g})"
        )

        wrapped_sub_jobs: Dict[str, SchedulerJobInfo] = {}
        for child_name, child_job in children_jobs.items():
            wrapped_sub_jobs[child_name] = SchedulerJobInfo(
                job_information=child_job,
                assigned_machine=None,
                dispatch_order=None,
                depends_on=list(s_job.depends_on) if s_job.depends_on else None,
            )
        return wrapped_sub_jobs

    @classmethod
    def cut_jobs(
        cls,
        jobs: Dict[str, SchedulerJobInfo],
        target_qubits: int | None = None,
        min_qubits: int = 2,
    ) -> Dict[str, SchedulerJobInfo]:
        """Cut all eligible uncut circuits in the jobs pool and update constraints.

        Args:
            jobs: Dictionary of SchedulerJobInfo.
            target_qubits: Desired target capacity for subcircuits (optional).
            min_qubits: Minimum qubit count to qualify for cutting (default: 2).

        Returns:
            Updated dictionary of SchedulerJobInfo with cut subcircuits replacing original jobs.
        """
        updated_jobs: Dict[str, SchedulerJobInfo] = {}
        for job_name, s_job in jobs.items():
            if cls.can_cut(s_job, min_qubits=min_qubits):
                sub_jobs = cls.cut_job(s_job, cluster_sizes=target_qubits)
                updated_jobs.update(sub_jobs)
            else:
                updated_jobs[job_name] = s_job
        return updated_jobs

