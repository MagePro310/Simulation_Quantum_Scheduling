"""Batch executor: prepare and execute batches on quantum hardware."""

import heapq
import math

from source.component.dataclass.execution_info import (
    BatchCounts,
    BatchExecutionRecord,
    ExecutionSummary,
)
from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class BatchExecutor:
    """Execute batches on quantum machines."""

    def __init__(self, circuit_composer, quantum_runner):
        self.circuit_composer = circuit_composer
        self.quantum_runner = quantum_runner

    def execute_batch(
        self,
        now: float,
        machine: MachineCharacteristic,
        active_jobs: list[str],
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        prepared_batch,
        summary: ExecutionSummary,
        events: list,
        seed: int,
    ) -> tuple:
        """Prepare and execute a batch on machine.

        Returns:
            (prepared_batch, completion_event) or raises exception
        """
        # Calculate shots
        shots = min(self._remaining_shots(results[name]) for name in active_jobs)

        # Create batch record
        batch_id = len(summary.batches) + 1
        batch_record = BatchExecutionRecord(
            batch_id=batch_id,
            machine_name=machine.name,
            job_ids=tuple(active_jobs),
            shots=shots,
            start_time=now,
            end_time=now,
            logical_qubits=sum(
                scheduler_job[name].job_information.circuit.num_qubits
                for name in active_jobs
            ),
        )
        summary.batches.append(batch_record)

        # Apply shot limits
        if limit := self.quantum_runner.max_shots(machine):
            batch_record.shots = min(batch_record.shots, limit)

        # Prepare circuits (reuse if possible)
        if prepared_batch is None or prepared_batch.job_ids != batch_record.job_ids:
            prepared_batch = self.circuit_composer.prepare_batch(
                machine,
                {name: scheduler_job[name].job_information for name in batch_record.job_ids},
                seed=seed,
            )

        # Calculate duration
        duration = float(prepared_batch.duration_per_shot) * batch_record.shots
        batch_record.end_time = now + duration

        # Mark jobs as running
        for name in batch_record.job_ids:
            if results[name].start_time is None:
                results[name].start_time = now
            results[name].status = "RUNNING"

        # Print notification
        job_list = ', '.join(batch_record.job_ids)
        print(f"│ Dispatch : {batch_record.machine_name:<15} → {job_list} ({batch_record.shots} shots)")

        # Execute simulation
        try:
            merged_counts = self.quantum_runner.execute_batch(
                machine, prepared_batch, batch_record.shots,
                seed=(seed + batch_record.batch_id - 1) % 2**32,
            )
            counts = self._split_counts(prepared_batch, merged_counts)
            error_reason = None
        except Exception as error:
            counts = None
            error_reason = f"Batch {batch_record.batch_id} on {batch_record.machine_name!r} execution failed: {error}"

        # Schedule completion
        from dataclasses import dataclass

        @dataclass
        class Completion:
            record: BatchExecutionRecord
            counts: dict[str, BatchCounts] | None
            error: str | None

        completion = Completion(batch_record, counts, error_reason)
        heapq.heappush(events, (batch_record.end_time, batch_record.batch_id, completion))

        return prepared_batch

    @staticmethod
    def _remaining_shots(result: ExecutionResult) -> int:
        """Calculate remaining shots for a job."""
        return result.requested_shots - result.completed_shots

    @staticmethod
    def _split_counts(prepared_batch, merged_counts: BatchCounts) -> dict[str, BatchCounts]:
        """Split merged batch counts back into individual job counts."""
        job_counts = {}

        for job_id in prepared_batch.job_ids:
            bit_indices = prepared_batch.classical_bits[job_id]
            no_noise = {}
            with_noise = {}

            for bitstring, count in merged_counts.distribution_no_noise.items():
                job_bits = ''.join(bitstring[-(i + 1)] for i in bit_indices)
                no_noise[job_bits] = no_noise.get(job_bits, 0) + count

            for bitstring, count in merged_counts.distribution_with_noise.items():
                job_bits = ''.join(bitstring[-(i + 1)] for i in bit_indices)
                with_noise[job_bits] = with_noise.get(job_bits, 0) + count

            job_counts[job_id] = BatchCounts(
                distribution_no_noise=no_noise,
                distribution_with_noise=with_noise,
            )

        return job_counts
