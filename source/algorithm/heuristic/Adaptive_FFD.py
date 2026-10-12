"""Adaptive First Fit Decreasing (Adaptive_FFD / FFD_v3).

Implements on-the-fly, slack-driven circuit cutting:
- Circuits are kept uncut whenever they fit naturally into open bins.
- When a circuit cannot fit into existing open bins, but an open bin has available slack,
  the algorithm dynamically cuts the circuit into [slack, remainder] to pack the bin to 100%.
- Evaluates QPD sampling overhead with `estimate_overhead` before committing to cut.
"""

from source.algorithm.heuristic.FFD import FFD, FFDBin
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper


class Adaptive_FFD(FFD):
    """Adaptive First Fit Decreasing: On-the-fly slack-driven circuit cutting.

    Unlike FFD_v2 which cuts all circuits upfront (pre-sort), Adaptive_FFD schedules
    circuits uncut whenever they fit. Only when a circuit cannot fit into existing open bins
    and there is available slack in an active bin, it adaptively cuts the circuit into
    [slack, remainder] to fill the machine capacity 100% without leaving wasted gaps.
    """

    def __init__(self, max_overhead_threshold: float = 81.0, **kwargs):
        super().__init__(**kwargs)
        self.max_overhead_threshold = max_overhead_threshold

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Execute Adaptive_FFD: on-the-fly slack-driven cutting and bin packing."""
        if not scheduler_job:
            return scheduler_job

        print("\n" + "=" * 65)
        print("  [Adaptive_FFD] On-The-Fly Slack-Driven Cutting & Bin Packing")
        print("=" * 65)

        # 1. Pack with dynamic on-the-fly cutting
        packed_bins, updated_jobs = self.adaptive_pack(scheduler_job, machines)

        # 2. Order bins by execution start time
        bins_in_execution_order = self._order_bins_by_start_time(
            packed_bins, updated_jobs, machines
        )

        # 3. Assign jobs, machines, and dispatch order
        self._assign_jobs(bins_in_execution_order, machines)

        return updated_jobs

    def adaptive_pack(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> tuple[list[FFDBin], dict[str, SchedulerJobInfo]]:
        """Pack jobs into bins, dynamically cutting circuits only when needed to fill idle slack."""
        current_jobs: dict[str, SchedulerJobInfo] = dict(scheduler_job)

        def get_qubits(job_name: str) -> int:
            job_info = current_jobs[job_name].job_information
            if job_info.num_qubits is not None:
                return job_info.num_qubits
            return getattr(job_info.circuit, "num_qubits", 0)

        # Pending jobs to schedule (sorted largest first)
        pending_jobs: list[str] = sorted(
            current_jobs.keys(),
            key=get_qubits,
            reverse=True,
        )

        round_index = 0
        open_bins = self._create_round_bins(machines, round_index)
        full_bins: list[FFDBin] = []

        while pending_jobs:
            job_name = pending_jobs.pop(0)
            s_job = current_jobs[job_name]
            required_qubits = get_qubits(job_name)

            # 1. Try to find an open bin that fits the job directly without cutting
            selected_bin = None
            for candidate_bin in open_bins:
                if required_qubits <= candidate_bin.remaining_qubits:
                    selected_bin = candidate_bin
                    break

            if selected_bin is not None:
                # Job fits as-is: place without cutting
                selected_bin.jobs[job_name] = s_job
                selected_bin.used_qubits += required_qubits
                if selected_bin.remaining_qubits == 0:
                    open_bins.remove(selected_bin)
                    full_bins.append(selected_bin)
                continue

            # 2. Job does not fit directly: check if we can cut to fill available slack
            slack_bin = None
            if SchedulingCutterHelper.can_cut(s_job, min_qubits=2):
                # Search open bins that have positive slack smaller than required_qubits
                candidates = [
                    b for b in open_bins
                    if 0 < b.remaining_qubits < required_qubits
                ]
                if candidates:
                    # Choose the bin with largest slack (first-fit / best-fit tiebreaker)
                    candidates.sort(key=lambda b: b.remaining_qubits, reverse=True)
                    best_cand = candidates[0]
                    slack = best_cand.remaining_qubits
                    remainder = required_qubits - slack

                    # Check overhead before cutting
                    cluster_sizes = [slack, remainder]
                    overhead = SchedulingCutterHelper.estimate_overhead(s_job, cluster_sizes)

                    if overhead <= self.max_overhead_threshold:
                        slack_bin = best_cand

            if slack_bin is not None:
                slack = slack_bin.remaining_qubits
                remainder = required_qubits - slack
                cluster_sizes = [slack, remainder]

                print(
                    f"  [Adaptive_FFD] On-the-fly cutting {job_name} ({required_qubits}q) -> "
                    f"{cluster_sizes} to fill slack in {slack_bin.machine_name}..."
                )
                sub_jobs = SchedulingCutterHelper.cut_job(s_job, cluster_sizes=cluster_sizes)

                # Remove original job and add subcircuits to current_jobs
                del current_jobs[job_name]
                current_jobs.update(sub_jobs)

                sub_names = list(sub_jobs.keys())
                child_for_slack = sub_jobs[sub_names[0]]

                slack_bin.jobs[sub_names[0]] = child_for_slack
                slack_bin.used_qubits += slack
                if slack_bin.remaining_qubits == 0:
                    open_bins.remove(slack_bin)
                    full_bins.append(slack_bin)

                # Insert remainder back into pending_jobs maintaining sorted order
                pending_jobs.append(sub_names[1])
                pending_jobs.sort(key=get_qubits, reverse=True)
                continue

            # 3. Cannot cut or no slack available: open a new round of bins
            round_index += 1
            new_bins = self._create_round_bins(machines, round_index)
            open_bins.extend(new_bins)

            for candidate_bin in new_bins:
                if required_qubits <= candidate_bin.remaining_qubits:
                    selected_bin = candidate_bin
                    break

            if selected_bin is None:
                raise ValueError(f"Job {job_name} ({required_qubits} qubits) cannot fit in any machine.")

            selected_bin.jobs[job_name] = s_job
            selected_bin.used_qubits += required_qubits
            if selected_bin.remaining_qubits == 0:
                open_bins.remove(selected_bin)
                full_bins.append(selected_bin)

        all_bins = full_bins + open_bins
        return all_bins, current_jobs


# Alias for convenience
FFD_v3 = Adaptive_FFD

