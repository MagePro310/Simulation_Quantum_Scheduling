"""Simple quantum job execution orchestrator."""

import heapq
import math
from collections import Counter
from dataclasses import dataclass

from source.component.dataclass.execution_info import (
    BatchCounts,
    BatchExecutionRecord,
)
from source.component.dataclass.result_schedule import ExecutionSummary
from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic

from source.flow.execution.circuit_composer import CircuitPreparation
from source.flow.execution.metrics_calculator import MetricsCalculator
from source.flow.execution.quantum_simulator import QuantumExecutor


@dataclass
class MachineState:
    """Track machine execution state."""
    queue: list[str]                    # Jobs waiting to run
    active: list[str] = None           # Jobs currently running
    busy: bool = False                  # Is machine executing?
    prepared = None                     # Cached prepared batch

    def __post_init__(self):
        if self.active is None:
            self.active = []


@dataclass
class BatchCompletion:
    """Batch completion event."""
    batch_record: BatchExecutionRecord
    job_counts: dict[str, BatchCounts] | None
    error: str | None


class ConcreteExecutionPhase:
    """Quantum job execution orchestrator."""

    def __init__(self):
        self.circuit_composer = CircuitPreparation()
        self.quantum_runner = QuantumExecutor()
        self.execution_summary = ExecutionSummary()

    def execute(
        self,
        machines: dict[str, MachineCharacteristic],
        scheduler_job: dict[str, SchedulerJobInfo],
        *,
        queue_policy: str = "strict",
        seed: int = 0,
        gantt_output_path: str | None = None,
        capture_result_schedule=None,
    ) -> dict[str, ExecutionResult]:
        """Execute quantum job schedule."""

        # Initialize state
        machine_states = self._initialize_machines(machines, scheduler_job)
        results = self._initialize_results(scheduler_job)
        events = []  # Heap of (time, batch_id, completion)

        # Event loop
        now = 0.0
        print("\n=== Quantum Execution Started ===")

        while self._has_unfinished_jobs(results):
            # Process completed batches
            self._complete_finished_batches(now, events, machine_states, results)

            # Block jobs with failed dependencies
            self._block_failed_dependents(scheduler_job, results)

            # Print status
            self._print_status(now, results, machine_states)

            # Dispatch and execute new batches
            failed = self._dispatch_and_execute(
                now, machines, scheduler_job, results,
                machine_states, events, queue_policy, seed
            )

            if failed:
                continue

            if self._all_jobs_done(results):
                break

            # Advance to next event
            now = self._next_event_time(now, events, scheduler_job, results, queue_policy)

        # Calculate final metrics
        MetricsCalculator.calculate_metrics(self.execution_summary, results, machines, now)
        if capture_result_schedule:
            capture_result_schedule.execution_summary = self.execution_summary
        MetricsCalculator.print_summary(self.execution_summary)

        return results

    # ========== Initialization ==========

    def _initialize_machines(self, machines, scheduler_job):
        """Create machine states with job queues."""
        # Build queues per machine
        queues = {name: [] for name in machines}
        for job_name, job in scheduler_job.items():
            if job.assigned_machine in queues:
                queues[job.assigned_machine].append(job_name)

        # Sort by dispatch order
        for queue in queues.values():
            queue.sort(key=lambda name: scheduler_job[name].dispatch_order or 0)

        return {name: MachineState(queue) for name, queue in queues.items()}

    def _initialize_results(self, scheduler_job):
        """Create initial execution results."""
        results = {}
        for name, job in scheduler_job.items():
            results[name] = ExecutionResult(
                job_info=job.job_information,
                assigned_machine=job.assigned_machine,
                distribution_no_noise={},
                distribution_with_noise={},
                execution_time=0.0,
                requested_shots=job.job_information.shots or 1024,
            )
        return results

    # ========== Main Loop Logic ==========

    def _complete_finished_batches(self, now, events, machine_states, results):
        """Process all batches that completed by current time."""
        while events and events[0][0] <= now:
            _, _, completion = heapq.heappop(events)
            state = machine_states[completion.batch_record.machine_name]

            # Update batch status
            completion.batch_record.status = "FAILED" if completion.error else "SUCCEEDED"
            completion.batch_record.error_reason = completion.error

            # Update job results and print completions
            state.active = self._update_job_results(completion, results)
            state.busy = False

            # Print completions
            for job_name in completion.batch_record.job_ids:
                if results[job_name].status == "SUCCEEDED":
                    result = results[job_name]
                    print(f"│ Complete : {job_name:<15} (duration: {result.execution_time:.3f}s, fidelity: {result.fidelity:.4f})")

    def _update_job_results(self, completion, results):
        """Update results for completed batch, return remaining active jobs."""
        remaining = []
        record = completion.batch_record

        for job_name in record.job_ids:
            result = results[job_name]
            result.end_time = record.end_time
            result.execution_time += record.end_time - record.start_time

            if completion.error:
                result.status = "FAILED"
                result.error_reason = completion.error
                continue

            # Add measurement counts
            counts = completion.job_counts[job_name]
            result.distribution_no_noise = dict(
                Counter(result.distribution_no_noise) + Counter(counts.distribution_no_noise)
            )
            result.distribution_with_noise = dict(
                Counter(result.distribution_with_noise) + Counter(counts.distribution_with_noise)
            )
            result.completed_shots += record.shots

            # Check if job is done
            if result.completed_shots >= result.requested_shots:
                result.status = "SUCCEEDED"
                # Calculate fidelity
                overlap = sum(
                    min(result.distribution_no_noise.get(k, 0),
                        result.distribution_with_noise.get(k, 0))
                    for k in set(result.distribution_no_noise) | set(result.distribution_with_noise)
                )
                result.fidelity = overlap / result.completed_shots if result.completed_shots > 0 else 1.0
            else:
                result.status = "RUNNING"
                remaining.append(job_name)

        return remaining

    def _block_failed_dependents(self, scheduler_job, results):
        """Mark jobs as BLOCKED if their dependencies failed."""
        while True:
            changed = False
            for job_name, job in scheduler_job.items():
                if results[job_name].status != "PENDING":
                    continue

                failed_deps = [
                    dep_name
                    for dep_info in job.depends_on
                    for dep_name, dep_job in scheduler_job.items()
                    if dep_job.job_information is dep_info and results[dep_name].status in {"FAILED", "BLOCKED"}
                ]

                if failed_deps:
                    results[job_name].status = "BLOCKED"
                    results[job_name].error_reason = f"Dependencies failed: {failed_deps}"
                    changed = True

            if not changed:
                break

    def _dispatch_and_execute(self, now, machines, scheduler_job, results,
                             machine_states, events, queue_policy, seed):
        """Dispatch ready jobs and execute batches on available machines."""
        for machine_name, state in machine_states.items():
            if state.busy:
                continue

            # Select jobs to run
            state.active = self._select_jobs(
                now, scheduler_job, results, state.queue, state.active,
                machines[machine_name].capacity, queue_policy
            )

            if not state.active:
                continue

            # Execute batch
            try:
                state.busy = True
                state.prepared = self._execute_batch(
                    now, machines[machine_name], state.active, scheduler_job, results,
                    state.prepared, events, seed
                )
            except Exception as error:
                # Handle failure
                self.execution_summary.batches[-1].status = "FAILED"
                self.execution_summary.batches[-1].error_reason = str(error)

                for job_name in state.active:
                    results[job_name].status = "FAILED"
                    results[job_name].error_reason = f"Batch preparation failed: {error}"

                state.active = []
                state.prepared = None
                state.busy = False
                return True

        return False

    def _select_jobs(self, now, scheduler_job, results, queue, active, capacity, policy):
        """Select jobs from queue that can run now."""
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
                for dep_info in scheduler_job[job_name].depends_on
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

            # Add job
            active_jobs.append(job_name)
            used_qubits += info.circuit.num_qubits
            to_remove.append(job_name)

        for name in to_remove:
            queue.remove(name)

        return active_jobs

    def _execute_batch(self, now, machine, active_jobs, scheduler_job,
                      results, prepared_batch, events, seed):
        """Prepare and execute a batch on the machine."""
        batch_id = len(self.execution_summary.batches) + 1
        batch_record = BatchExecutionRecord(
            batch_id=batch_id,
            machine_name=machine.name,
            job_ids=tuple(active_jobs),
            shots=min(results[name].requested_shots - results[name].completed_shots for name in active_jobs),
            start_time=now,
            end_time=now,
            logical_qubits=sum(scheduler_job[name].job_information.circuit.num_qubits for name in active_jobs),
        )
        self.execution_summary.batches.append(batch_record)

        # Apply shot limit
        if max_shots := self.quantum_runner.max_shots(machine):
            batch_record.shots = min(batch_record.shots, max_shots)

        # Prepare circuits (reuse if same jobs)
        if prepared_batch is None or prepared_batch.job_ids != batch_record.job_ids:
            prepared_batch = self.circuit_composer.prepare_batch(
                machine,
                {name: scheduler_job[name].job_information for name in active_jobs},
                seed=seed,
            )

        # Calculate duration and mark jobs as running
        batch_record.end_time = now + float(prepared_batch.duration_per_shot) * batch_record.shots

        for name in active_jobs:
            if results[name].start_time is None:
                results[name].start_time = now
            results[name].status = "RUNNING"

        print(f"│ Dispatch : {machine.name:<15} → {', '.join(active_jobs)} ({batch_record.shots} shots)")

        # Execute quantum simulation
        try:
            job_counts = self._split_counts(
                prepared_batch,
                self.quantum_runner.execute_batch(machine, prepared_batch, batch_record.shots, seed=(seed + batch_id - 1) % 2**32)
            )
            error = None
        except Exception as e:
            job_counts = None
            error = f"Batch {batch_id} execution failed: {e}"

        heapq.heappush(events, (batch_record.end_time, batch_id, BatchCompletion(batch_record, job_counts, error)))

        return prepared_batch

    def _split_counts(self, prepared_batch, merged_counts):
        """Split merged batch results into individual job counts."""
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

    # ========== Status & Time ==========

    def _print_status(self, now, results, machine_states):
        """Print current execution status."""
        if not any(r.status in {"PENDING", "RUNNING"} for r in results.values()):
            return

        print(f"\n┌─ Time: {now:.3f}s ─────────────────────────────────────")

        if pending := [name for name, r in results.items() if r.status == "PENDING"]:
            print(f"│ Queue    : {', '.join(pending)}")

        for machine_name, state in machine_states.items():
            if state.busy and state.active:
                print(f"│ Running  : {machine_name:<15} → {', '.join(state.active)}")

        print("└" + "─" * 50)

    def _next_event_time(self, now, events, scheduler_job, results, queue_policy):
        """Calculate next event time."""
        next_times = [timestamp for timestamp, _, _ in events]
        next_times.extend(
            job.job_information.arrival_time
            for name, job in scheduler_job.items()
            if results[name].status == "PENDING"
            and job.job_information.arrival_time
            and job.job_information.arrival_time > now
        )

        if not next_times:
            raise RuntimeError(
                f"Cannot make progress with queue_policy={queue_policy!r}: "
                f"{[name for name, r in results.items() if r.status in {'PENDING', 'RUNNING'}]}"
            )

        earliest = min(next_times)
        return max(t for t in next_times if t - earliest <= 4 * max(math.ulp(earliest), math.ulp(t)))

    # ========== Helper Checks ==========

    def _has_unfinished_jobs(self, results):
        """Check if any jobs are pending or running."""
        return any(r.status in {"PENDING", "RUNNING"} for r in results.values())

    def _all_jobs_done(self, results):
        """Check if all jobs are in terminal state."""
        return all(r.status in {"SUCCEEDED", "FAILED", "BLOCKED"} for r in results.values())
