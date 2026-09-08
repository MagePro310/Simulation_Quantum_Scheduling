"""Validate batch outcomes and report the realized execution timeline."""

from collections import Counter
from typing import Any

from qiskit.quantum_info.analysis import hellinger_fidelity

from source.component.dataclass.execution_info import (
    BatchCounts,
    ExecutionSummary,
    MachineExecutionResult,
    PreparedBatch,
)
from source.component.dataclass.job_info import ExecutionResult


class PostExecution:
    def split_counts(
        self, prepared: PreparedBatch, counts: BatchCounts, shots: int,
    ) -> dict[str, BatchCounts]:
        """Validate both runs before marginalizing their explicit classical map.

        Mapping entries list merged bit indices in each job's local bit order
        (bit zero first). Count strings use Qiskit's most significant bit first
        convention; spaces separating classical registers are accepted.
        """
        if type(shots) is not int or shots <= 0:
            raise ValueError("Batch shots must be a positive integer")
        width = self._validate_classical_mapping(prepared)
        validated = [
            self._validate_count_distribution(label, distribution, width, shots)
            for label, distribution in (
                ("ideal", counts.distribution_no_noise),
                ("noisy", counts.distribution_with_noise),
            )
        ]

        split = {}
        for job_id in prepared.job_ids:
            bits = prepared.classical_bits[job_id]
            distributions = [
                self._marginalize_counts(distribution, bits, width)
                for distribution in validated
            ]
            split[job_id] = BatchCounts(*distributions)
        return split

    @staticmethod
    def _validate_classical_mapping(prepared: PreparedBatch) -> int:
        """Validate the per-job bit partition and return the merged width."""
        width = prepared.merged_circuit.num_clbits
        if width <= 0 or prepared.transpiled_circuit.num_clbits != width:
            raise ValueError("Merged and transpiled classical widths must agree and be positive")
        if not prepared.job_ids or len(set(prepared.job_ids)) != len(prepared.job_ids):
            raise ValueError("Prepared batch must have unique job IDs")
        if set(prepared.classical_bits) != set(prepared.job_ids):
            raise ValueError("Classical bit mappings must cover exactly the batch jobs")

        all_bits = []
        for job_id in prepared.job_ids:
            bits = prepared.classical_bits[job_id]
            if not bits or any(type(bit) is not int or not 0 <= bit < width for bit in bits):
                raise ValueError(f"Invalid classical bit mapping for job {job_id!r}")
            all_bits.extend(bits)
        if len(all_bits) != width or len(set(all_bits)) != width:
            raise ValueError("Classical bit mappings must partition the merged result bits")
        return width

    @staticmethod
    def _validate_count_distribution(
        label: str, distribution: dict[str, int], width: int, shots: int,
    ) -> Counter[str]:
        """Validate a complete run, merging keys that differ only by spaces."""
        if not isinstance(distribution, dict) or not distribution:
            raise ValueError(f"The {label} batch distribution must be a nonempty count dictionary")
        normalized: Counter[str] = Counter()
        for key, count in distribution.items():
            if not isinstance(key, str):
                raise ValueError(f"The {label} batch outcome must be a binary string")
            bitstring = key.replace(" ", "")
            if len(bitstring) != width or any(bit not in "01" for bit in bitstring):
                raise ValueError(f"The {label} outcome {key!r} does not match the merged classical width")
            if type(count) is not int or count < 0:
                raise ValueError(f"The {label} counts must be nonnegative integers")
            normalized[bitstring] += count
        if sum(normalized.values()) != shots:
            raise ValueError(f"The {label} batch distribution must contain exactly {shots} shots")
        return normalized

    @staticmethod
    def _marginalize_counts(
        distribution: Counter[str], bits: tuple[int, ...], width: int,
    ) -> dict[str, int]:
        """Project a validated run into a job's local classical bit order."""
        marginal: Counter[str] = Counter()
        for bitstring, count in distribution.items():
            local_bits = "".join(bitstring[width - 1 - bit] for bit in reversed(bits))
            marginal[local_bits] += count
        return dict(marginal)

    def finalize(
        self,
        machines: dict[str, Any],
        results: dict[str, ExecutionResult],
        summary: ExecutionSummary,
        *,
        capture_result_schedule: Any = None,
        gantt_output_path: str | None = None,
    ) -> None:
        """Populate metrics from completed jobs and all recorded batch intervals."""
        self._populate_job_metrics(results, summary)
        self._populate_machine_metrics(machines, summary)

        if capture_result_schedule is not None:
            if callable(getattr(capture_result_schedule, "capture_execution", None)):
                capture_result_schedule.capture_execution(summary)
            else:
                capture_result_schedule.execution_summary = summary
        if gantt_output_path is not None:
            self._draw_gantt_chart(machines, results, summary, gantt_output_path)

    @staticmethod
    def _populate_job_metrics(
        results: dict[str, ExecutionResult], summary: ExecutionSummary,
    ) -> None:
        """Reset job metrics, then aggregate timings and fidelity of successes."""
        succeeded = [result for result in results.values() if result.status == "SUCCEEDED"]
        summary.succeeded_jobs = len(succeeded)
        summary.failed_jobs = sum(result.status == "FAILED" for result in results.values())
        summary.blocked_jobs = sum(result.status == "BLOCKED" for result in results.values())
        summary.total_turnaround_time = 0.0
        summary.total_waiting_time = 0.0
        summary.total_response_time = 0.0

        for result in results.values():
            result.fidelity = None
        for result in succeeded:
            if result.start_time is None or result.end_time is None or result.execution_time is None:
                raise ValueError("Successful jobs must have complete execution timings")
            arrival = result.job_info.arrival_time or 0.0
            turnaround = result.end_time - arrival
            summary.total_turnaround_time += turnaround
            summary.total_waiting_time += max(0.0, turnaround - result.execution_time)
            summary.total_response_time += result.start_time - arrival
            if result.distribution_no_noise and result.distribution_with_noise:
                result.fidelity = float(hellinger_fidelity(
                    result.distribution_no_noise, result.distribution_with_noise,
                ))

        count = summary.succeeded_jobs
        summary.average_turnaround_time = summary.total_turnaround_time / count if count else 0.0
        summary.average_waiting_time = summary.total_waiting_time / count if count else 0.0
        summary.average_response_time = summary.total_response_time / count if count else 0.0
        summary.job_completion_rate = count / summary.makespan if summary.makespan else 0.0
        fidelities = [result.fidelity for result in succeeded if result.fidelity is not None]
        summary.average_fidelity = sum(fidelities) / len(fidelities) if fidelities else 0.0

    @staticmethod
    def _populate_machine_metrics(
        machines: dict[str, Any], summary: ExecutionSummary,
    ) -> None:
        """Include every recorded batch, including failed runs, in utilization."""
        summary.machines = {}
        for machine_name, machine in machines.items():
            records = [batch for batch in summary.batches if batch.machine_name == machine_name]
            busy_time = sum(batch.end_time - batch.start_time for batch in records)
            qubit_time = sum(
                (batch.end_time - batch.start_time) * batch.logical_qubits for batch in records
            )
            denominator = machine.capacity * summary.makespan
            summary.machines[machine_name] = MachineExecutionResult(
                machine_name=machine_name,
                busy_time=busy_time,
                qubit_time=qubit_time,
                utilization=qubit_time / denominator if denominator else 0.0,
            )

    @staticmethod
    def _draw_gantt_chart(
        machines: dict[str, Any], results: dict[str, ExecutionResult],
        summary: ExecutionSummary, output_path: str,
    ) -> None:
        """Draw separate job lanes so repeated batches remain visible."""
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        lanes = [
            (machine_name, job_id)
            for machine_name in machines
            for job_id, result in results.items()
            if result.assigned_machine == machine_name
        ]
        lane_indices = {lane: index for index, lane in enumerate(lanes)}
        palette = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]
        colors = {job_id: palette[index % len(palette)] for index, job_id in enumerate(results)}
        figure, axis = plt.subplots(figsize=(12, max(3, 0.65 * len(lanes) + 1.5)))
        try:
            for batch in summary.batches:
                batch_lanes = [lane_indices[(batch.machine_name, job_id)] for job_id in batch.job_ids]
                for job_id, lane in zip(batch.job_ids, batch_lanes):
                    duration = batch.end_time - batch.start_time
                    if duration > 0:
                        axis.barh(
                            lane, duration, left=batch.start_time, height=0.65,
                            color=colors[job_id], edgecolor="black",
                            hatch="//" if batch.status == "FAILED" else None,
                        )
                    else:
                        axis.plot(batch.start_time, lane, marker="x", color="red")
                    axis.annotate(
                        f"B{batch.batch_id}: {batch.shots} shots · {batch.status}",
                        (batch.start_time + duration / 2, lane), ha="center", va="center", fontsize=8,
                    )
                if batch_lanes:
                    axis.vlines(
                        [batch.start_time, batch.end_time], min(batch_lanes) - 0.4,
                        max(batch_lanes) + 0.4, colors="0.35", linestyles="dotted", linewidth=0.8,
                    )

            axis.set_yticks(range(len(lanes)), [
                f"{machine_name} / {job_id} [{results[job_id].status}]"
                for machine_name, job_id in lanes
            ])
            axis.invert_yaxis()
            extent = summary.makespan if summary.makespan > 0 else 1e-6
            margin = max(extent * 0.04, 1e-12)
            axis.set_xlim(-margin, extent + margin)
            axis.set_xlabel("Virtual execution time (seconds)")
            axis.set_ylabel("Machine / job")
            axis.set_title("Quantum execution batches")
            axis.ticklabel_format(axis="x", style="sci", scilimits=(-3, 3), useOffset=False)
            axis.grid(axis="x", alpha=0.25)
            if not lanes:
                axis.text(0.5, 0.5, "No execution jobs", transform=axis.transAxes, ha="center")
            figure.tight_layout()
            figure.savefig(output_path, dpi=160)
        finally:
            plt.close(figure)
