"""Quantum job execution orchestrator."""

import heapq
import math
from dataclasses import dataclass

from source.component.dataclass.execution_info import BatchCompletion
from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.dataclass.result_schedule import ExecutionSummary

from source.flow.execution.batch_executor import BatchExecutor
from source.flow.execution.interfaces import (
    DefaultLayoutStrategy,
    JobDispatcherProtocol,
    LayoutStrategy,
    TimelineReporterProtocol,
)
from source.flow.execution.job_dispatcher import JobDispatcher
from source.flow.execution.metrics_calculator import MetricsCalculator
from source.flow.execution.reconstruction_handler import ReconstructionHandler
from source.flow.execution.timeline_reporter import ConsoleTimelineReporter


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


class ConcreteExecutionPhase:
    """Quantum job execution orchestrator with Dependency Injection support."""

    def __init__(
        self,
        dispatcher: JobDispatcherProtocol | None = None,
        batch_executor: BatchExecutor | None = None,
        layout_strategy: LayoutStrategy | None = None,
        reconstruction_handler: ReconstructionHandler | None = None,
        reporter: TimelineReporterProtocol | None = None,
    ):
        """Initialize the execution phase with pluggable strategies or standard defaults.

        Args:
            dispatcher: Custom job dispatching strategy (defaults to JobDispatcher).
            batch_executor: Custom batch execution coordinator.
            layout_strategy: Custom physical layout assignment strategy (defaults to Qiskit native).
            reconstruction_handler: Custom circuit reconstruction handler.
            reporter: Presentation logger (defaults to ConsoleTimelineReporter).
        """
        self.reporter = reporter or ConsoleTimelineReporter()
        self.job_dispatcher = dispatcher or JobDispatcher()
        self.layout_strategy = layout_strategy or DefaultLayoutStrategy()
        self.batch_executor = batch_executor or BatchExecutor(
            layout_strategy=self.layout_strategy,
            reporter=self.reporter,
        )
        self.reconstruction_handler = reconstruction_handler or ReconstructionHandler()

        # Expose sub-components for backward compatibility
        self.circuit_composer = self.batch_executor.circuit_composer
        self.quantum_runner = self.batch_executor.quantum_runner
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
        """Execute quantum job schedule using discrete-event simulation."""
        machine_states = self._initialize_machines(machines, scheduler_job)
        results = self._initialize_results(scheduler_job)
        events = []  # Priority queue of (timestamp, batch_id, BatchCompletion)

        now = 0.0
        self.reporter.print_start()

        queue_policy = queue_policy.lower()

        while self._has_unfinished_jobs(results):
            # 1. Process completed batches
            self._complete_finished_batches(now, events, machine_states, results)

            # 2. Block jobs with failed dependencies
            self.job_dispatcher.block_failed_dependents(scheduler_job, results)

            # 3. Print current timeline status
            self.reporter.print_timeline_status(now, results, machine_states)

            # 4. Dispatch and execute new batches on idle machines
            failed = self._dispatch_and_execute(
                now, machines, scheduler_job, results, machine_states, events, queue_policy, seed
            )
            if failed:
                continue

            if self._all_jobs_done(results):
                break

            # 5. Advance clock to next event
            now = self._next_event_time(now, events, scheduler_job, results, queue_policy)

        # Finalize metrics and visualization
        MetricsCalculator.calculate_metrics(self.execution_summary, results, machines, now)
        if capture_result_schedule:
            capture_result_schedule.execution_summary = self.execution_summary
            capture_result_schedule.queue_policy = queue_policy
            capture_result_schedule.seed = seed
        MetricsCalculator.print_summary(self.execution_summary)

        self._generate_gantt_safely(capture_result_schedule, gantt_output_path, results, machines)
        return results

    def _dispatch_and_execute(
        self, now, machines, scheduler_job, results, machine_states, events, queue_policy, seed
    ) -> bool:
        """Dispatch ready jobs and execute batches on available machines."""
        for machine_name, state in machine_states.items():
            if state.busy:
                continue

            state.active = self.job_dispatcher.select_jobs(
                now, scheduler_job, results, state.queue, state.active,
                machines[machine_name].capacity, queue_policy
            )
            if not state.active:
                continue

            state.busy = True
            batch_id = len(self.execution_summary.batches) + 1
            batch_record, job_counts, error, prepared_batch = self.batch_executor.execute_batch(
                now, machines[machine_name], state.active, scheduler_job, results,
                state.prepared, seed, batch_id
            )
            state.prepared = prepared_batch
            self.execution_summary.batches.append(batch_record)

            if error:
                batch_record.status = "FAILED"
                batch_record.error_reason = error
                for job_name in state.active:
                    results[job_name].status = "FAILED"
                    results[job_name].error_reason = error
                state.active = []
                state.prepared = None
                state.busy = False
                return True

            heapq.heappush(events, (batch_record.end_time, batch_id, BatchCompletion(batch_record, job_counts, error)))

        return False

    def _complete_finished_batches(self, now, events, machine_states, results) -> None:
        """Process all batches that completed by current time."""
        while events and events[0][0] <= now:
            _, _, completion = heapq.heappop(events)
            state = machine_states[completion.batch_record.machine_name]

            completion.batch_record.status = "FAILED" if completion.error else "SUCCEEDED"
            completion.batch_record.error_reason = completion.error

            state.active = self.reconstruction_handler.update_job_results(completion, results)
            state.busy = False

            for job_name in completion.batch_record.job_ids:
                if results[job_name].status == "SUCCEEDED":
                    result = results[job_name]
                    info = getattr(result, "job_info", None)
                    if info and getattr(info, "parentJob", None) is not None:
                        continue
                    self.reporter.print_completion(job_name, result.execution_time, result.fidelity)

    # ========== Initialization ==========

    def _initialize_machines(self, machines, scheduler_job) -> dict[str, MachineState]:
        """Create machine states with job queues sorted by dispatch order."""
        queues = {name: [] for name in machines}
        for job_name, job in scheduler_job.items():
            if job.assigned_machine in queues:
                queues[job.assigned_machine].append(job_name)

        for queue in queues.values():
            queue.sort(key=lambda name: scheduler_job[name].dispatch_order or 0)

        return {name: MachineState(queue) for name, queue in queues.items()}

    def _initialize_results(self, scheduler_job) -> dict[str, ExecutionResult]:
        """Create initial execution results for all scheduled jobs."""
        return {
            name: ExecutionResult(
                job_info=job.job_information,
                assigned_machine=job.assigned_machine,
                distribution_no_noise={},
                distribution_with_noise={},
                execution_time=0.0,
                requested_shots=job.job_information.shots or 1024,
            )
            for name, job in scheduler_job.items()
        }

    # ========== Timeline & Progress ==========

    def _next_event_time(self, now, events, scheduler_job, results, queue_policy) -> float:
        """Calculate next event time from completed batches or pending job arrivals."""
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

    def _has_unfinished_jobs(self, results) -> bool:
        """Check if any jobs are pending or running."""
        return any(r.status in {"PENDING", "RUNNING"} for r in results.values())

    def _all_jobs_done(self, results) -> bool:
        """Check if all jobs are in a terminal state."""
        return all(r.status in {"SUCCEEDED", "FAILED", "BLOCKED"} for r in results.values())

    def _generate_gantt_safely(self, capture_result_schedule, gantt_output_path, results, machines) -> None:
        """Generate Gantt chart visualization safely without interrupting execution flow."""
        algo_name = getattr(capture_result_schedule, "nameSchedule", "Schedule") if capture_result_schedule else "Schedule"
        if not gantt_output_path:
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[3]
            gantt_output_path = project_root / "results" / "charts" / f"{algo_name}_gantt.png"

        try:
            from source.component.help_function.gantt_chart import GanttChart
            gantt = GanttChart(title=f"{algo_name} Schedule Gantt Chart")
            gantt.display(results, machines, output_path=gantt_output_path, execution_summary=self.execution_summary)
        except Exception as err:
            print(f"Failed to generate Gantt chart: {err}")

    # ========== Backward Compatibility Delegations ==========

    def _select_jobs(self, *args, **kwargs):
        """Delegate job selection to JobDispatcher for backward compatibility."""
        return self.job_dispatcher.select_jobs(*args, **kwargs)

    def _block_failed_dependents(self, *args, **kwargs):
        """Delegate dependency blocking to JobDispatcher for backward compatibility."""
        return self.job_dispatcher.block_failed_dependents(*args, **kwargs)

    def _reconstruct_parent_job(self, *args, **kwargs):
        """Delegate reconstruction to ReconstructionHandler for backward compatibility."""
        return self.reconstruction_handler.reconstruct_parent_job(*args, **kwargs)

    def _print_status(self, now, results, machine_states) -> None:
        """Delegate timeline printing to reporter for backward compatibility."""
        self.reporter.print_timeline_status(now, results, machine_states)
