"""Coordinate a fixed schedule on a virtual QPU clock."""

from collections import Counter
from dataclasses import dataclass, field
import heapq
import math
from typing import Any

from source.component.dataclass.execution_info import (
    BatchCounts,
    BatchExecutionRecord,
    ExecutionSummary,
    PreparedBatch,
)
from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.execution.execution_validation import ValidatedJob, validate_schedule
from source.flow.execution.main_execution_quantum import MainExecutionQuantum
from source.flow.execution.post_execution_analysis import PostExecution
from source.flow.execution.pre_execution_transpile import PreExecution


_UNFINISHED_STATUSES = {"PENDING", "RUNNING"}
_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "BLOCKED"}


@dataclass
class _MachineState:
    pending: list[str]
    active: list[str] = field(default_factory=list)
    busy: bool = False
    prepared: PreparedBatch | None = None


@dataclass
class _Completion:
    record: BatchExecutionRecord
    counts: dict[str, BatchCounts] | None
    error: str | None


@dataclass
class _ExecutionRun:
    """Mutable state belonging to one execute call, separate from input jobs."""

    machines: dict[str, MachineCharacteristic]
    jobs: dict[str, ValidatedJob]
    results: dict[str, ExecutionResult]
    machine_states: dict[str, _MachineState]
    summary: ExecutionSummary
    queue_policy: str
    seed: int
    now: float = 0.0
    events: list[tuple[float, int, _Completion]] = field(default_factory=list)


class ConcreteExecutionPhase:
    """Validate, execute, analyze, and report a schedule without modifying it.

    Helpers can be supplied for deterministic tests or alternative local runners.
    execution_summary is reset on every call and remains the sole metric owner.
    """

    def __init__(self, pre_execution=None, main_execution=None, post_execution=None):
        self.pre_execution = pre_execution if pre_execution is not None else PreExecution()
        self.main_execution = main_execution if main_execution is not None else MainExecutionQuantum()
        self.post_execution = post_execution if post_execution is not None else PostExecution()
        self.execution_summary = ExecutionSummary()

    def execute(
        self,
        machines: dict[str, MachineCharacteristic],
        scheduler_job: dict[str, SchedulerJobInfo],
        capture_result_schedule: Any = None,
        *,
        queue_policy: str = "strict",
        seed: int = 0,
        gantt_output_path: str | None = "execution_gantt_chart.png",
    ) -> dict[str, ExecutionResult]:
        self.execution_summary = ExecutionSummary()
        jobs, queues = validate_schedule(machines, scheduler_job, queue_policy, seed)
        run = _ExecutionRun(
            machines=machines,
            jobs=jobs,
            results=self._create_results(jobs),
            machine_states={name: _MachineState(queue) for name, queue in queues.items()},
            summary=self.execution_summary,
            queue_policy=queue_policy,
            seed=seed,
        )

        self._run_until_finished(run)
        self.post_execution.finalize(
            machines, run.results, self.execution_summary,
            capture_result_schedule=capture_result_schedule,
            gantt_output_path=gantt_output_path,
        )
        self._print_summary()
        return run.results

    @staticmethod
    def _create_results(jobs: dict[str, ValidatedJob]) -> dict[str, ExecutionResult]:
        return {
            name: ExecutionResult(
                job_info=job.information,
                assigned_machine=job.machine,
                distribution_no_noise={},
                distribution_with_noise={},
                execution_time=0.0,
                requested_shots=job.shots,
            )
            for name, job in jobs.items()
        }

    def _run_until_finished(self, run: _ExecutionRun) -> None:
        while any(result.status in _UNFINISHED_STATUSES for result in run.results.values()):
            self._finish_due_batches(run)
            self._block_dependents(run)
            preparation_failed = self._dispatch_ready_machines(run)
            run.summary.makespan = run.now

            if preparation_failed:
                # A failed head may expose independent work at this same instant.
                continue
            if all(result.status in _TERMINAL_STATUSES for result in run.results.values()):
                break
            run.now = self._next_event_time(run)

        run.summary.makespan = run.now

    def _finish_due_batches(self, run: _ExecutionRun) -> None:
        # Process all simultaneous completions before any successor is admitted.
        while run.events and run.events[0][0] <= run.now:
            _, _, completion = heapq.heappop(run.events)
            state = run.machine_states[completion.record.machine_name]
            self._complete_batch(completion, state, run.results)

    @staticmethod
    def _block_dependents(run: _ExecutionRun) -> None:
        changed = True
        while changed:
            changed = False
            for name, job in run.jobs.items():
                if run.results[name].status != "PENDING":
                    continue
                failed = [
                    dependency for dependency in job.dependencies
                    if run.results[dependency].status in {"FAILED", "BLOCKED"}
                ]
                if failed:
                    run.results[name].status = "BLOCKED"
                    run.results[name].error_reason = f"Dependencies failed or blocked: {failed}"
                    changed = True

    def _dispatch_ready_machines(self, run: _ExecutionRun) -> bool:
        """Submit idle machines; report preparation failures needing another pass."""
        preparation_failed = False
        for machine_name, state in run.machine_states.items():
            if state.busy:
                continue
            machine = run.machines[machine_name]
            self._admit_jobs(run, state, machine.capacity)
            if not state.active:
                continue

            record = self._new_batch_record(run, machine_name, state)
            try:
                self._prepare_batch(run, machine, state, record)
            except Exception as error:
                self._fail_preparation(run, state, record, error)
                preparation_failed = True
                continue
            self._submit_batch(run, machine, state, record)
        return preparation_failed

    @staticmethod
    def _admit_jobs(run: _ExecutionRun, state: _MachineState, capacity: int) -> None:
        state.pending = [name for name in state.pending if run.results[name].status == "PENDING"]
        available = capacity - sum(run.jobs[name].width for name in state.active)
        admitted: set[str] = set()
        for name in state.pending:
            job = run.jobs[name]
            dependencies_complete = all(
                run.results[dependency].status == "SUCCEEDED" for dependency in job.dependencies
            )
            eligible = job.arrival <= run.now and job.width <= available and dependencies_complete
            if eligible:
                state.active.append(name)
                admitted.add(name)
                available -= job.width
            elif run.queue_policy == "strict":
                break
        state.pending = [name for name in state.pending if name not in admitted]
        state.active.sort(key=lambda name: run.jobs[name].order)

    @staticmethod
    def _new_batch_record(
        run: _ExecutionRun, machine_name: str, state: _MachineState,
    ) -> BatchExecutionRecord:
        job_ids = tuple(state.active)
        shots = min(
            run.results[name].requested_shots - run.results[name].completed_shots
            for name in job_ids
        )
        record = BatchExecutionRecord(
            batch_id=len(run.summary.batches) + 1,
            machine_name=machine_name,
            job_ids=job_ids,
            shots=shots,
            start_time=run.now,
            end_time=run.now,
            logical_qubits=sum(run.jobs[name].width for name in job_ids),
        )
        run.summary.batches.append(record)
        return record

    def _prepare_batch(
        self, run: _ExecutionRun, machine: MachineCharacteristic,
        state: _MachineState, record: BatchExecutionRecord,
    ) -> None:
        """Apply shot limits and reuse compilation while membership is unchanged."""
        limit = self.main_execution.max_shots(machine)
        if limit is not None:
            if type(limit) is not int or limit <= 0:
                raise ValueError("Backend shot limit must be a positive integer")
            record.shots = min(record.shots, limit)
        if state.prepared is None or state.prepared.job_ids != record.job_ids:
            state.prepared = self.pre_execution.prepare_batch(
                machine,
                {name: run.jobs[name].information for name in record.job_ids},
                seed=run.seed,
            )
        duration = float(state.prepared.duration_per_shot) * record.shots
        end_time = run.now + duration
        if (
            not math.isfinite(duration) or duration <= 0
            or not math.isfinite(end_time) or end_time <= run.now
        ):
            raise ValueError("Batch duration must be finite, positive, and advance virtual time")
        record.end_time = end_time

    def _fail_preparation(
        self, run: _ExecutionRun, state: _MachineState,
        record: BatchExecutionRecord, error: Exception,
    ) -> None:
        """Preparation failures release jobs immediately and consume no QPU time."""
        reason = f"Batch {record.batch_id} on {record.machine_name!r} preparation failed: {error}"
        record.status = "FAILED"
        record.error_reason = reason
        for name in record.job_ids:
            run.results[name].status = "FAILED"
            run.results[name].error_reason = reason
        state.active = []
        state.prepared = None
        self._block_dependents(run)

    def _submit_batch(
        self, run: _ExecutionRun, machine: MachineCharacteristic,
        state: _MachineState, record: BatchExecutionRecord,
    ) -> None:
        """Compute counts now, but commit success or failure at the virtual end."""
        for name in record.job_ids:
            if run.results[name].start_time is None:
                run.results[name].start_time = run.now
            run.results[name].status = "RUNNING"
        state.busy = True
        counts = None
        reason = None
        try:
            merged_counts = self.main_execution.execute_batch(
                machine, state.prepared, record.shots,
                seed=(run.seed + record.batch_id - 1) % 2**32,
            )
            counts = self.post_execution.split_counts(state.prepared, merged_counts, record.shots)
        except Exception as error:
            reason = f"Batch {record.batch_id} on {record.machine_name!r} execution failed: {error}"
        completion = _Completion(record, counts, reason)
        heapq.heappush(run.events, (record.end_time, record.batch_id, completion))

    @staticmethod
    def _complete_batch(
        completion: _Completion, state: _MachineState,
        results: dict[str, ExecutionResult],
    ) -> None:
        record = completion.record
        record.status = "FAILED" if completion.error is not None else "SUCCEEDED"
        record.error_reason = completion.error
        for name in record.job_ids:
            result = results[name]
            result.end_time = record.end_time
            result.execution_time += record.end_time - record.start_time
            if completion.error is not None:
                result.status = "FAILED"
                result.error_reason = completion.error
                continue

            counts = completion.counts[name]
            result.distribution_no_noise = dict(
                Counter(result.distribution_no_noise) + Counter(counts.distribution_no_noise)
            )
            result.distribution_with_noise = dict(
                Counter(result.distribution_with_noise) + Counter(counts.distribution_with_noise)
            )
            result.completed_shots += record.shots
            if result.completed_shots == result.requested_shots:
                result.status = "SUCCEEDED"
            else:
                result.status = "RUNNING"
        state.active = [name for name in state.active if results[name].status == "RUNNING"]
        state.busy = False

    def _next_event_time(self, run: _ExecutionRun) -> float:
        next_times = [timestamp for timestamp, _, _ in run.events]
        next_times.extend(
            job.arrival for name, job in run.jobs.items()
            if run.results[name].status == "PENDING" and job.arrival > run.now
        )
        if not next_times:
            waiting = [
                name for name, result in run.results.items()
                if result.status in _UNFINISHED_STATUSES
            ]
            raise RuntimeError(
                f"Execution cannot make progress with queue_policy={run.queue_policy!r}: {waiting}"
            )
        return self._next_timestamp(next_times)

    @staticmethod
    def _next_timestamp(times: list[float]) -> float:
        """Group rounding-equivalent times without merging distinct QPU events.

        Arithmetic such as 0.2 + 0.1 can differ from 0.3 by one float step.
        Use a few representable steps instead of an absolute tolerance. Choose
        the latest grouped timestamp so successors never precede their own
        arrival or a prerequisite's recorded end.
        """
        earliest = min(times)
        return max(
            timestamp for timestamp in times
            if timestamp - earliest <= 4 * max(math.ulp(earliest), math.ulp(timestamp))
        )

    def _print_summary(self) -> None:
        summary = self.execution_summary
        print(
            f"Execution completed: {summary.succeeded_jobs} succeeded, "
            f"{summary.failed_jobs} failed, "
            f"{summary.blocked_jobs} blocked; "
            f"virtual makespan {summary.makespan:.6g} seconds"
        )
