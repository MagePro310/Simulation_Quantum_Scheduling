# Simulation Quantum Scheduling

This is repository for the simulation of quantum scheduling system. This help test different scheduling algorithms and evaluate their performance in a simulated environment.

## How to use

1. Clone the repository.
git clone <repository_url>
2. Install the required dependencies.
pip install -r requirements.txt
3. Run the simulation scripts.
python main.py

## Execution environment

`main.py` runs the input, scheduling, and execution phases, prints completion
totals and the virtual makespan, and saves `execution_gantt_chart.png`.
Execution uses local ideal and noisy Aer simulations; no IBM account is needed.

To select the queue policy or inspect results in your own experiment:

```python
from source.flow.execution.phase_execution import ConcreteExecutionPhase

execution = ConcreteExecutionPhase()
results = execution.execute(
    machines,
    execution_job_relations,  # dict returned by ConcreteSchedulePhase.execute
    capture_result_schedule,
    queue_policy="backfill",  # "strict" is the default
    seed=0,
    gantt_output_path="execution_gantt_chart.png",  # None disables the chart
)

for job_id, result in results.items():
    print(job_id, result.status, result.completed_shots, result.requested_shots)
    print(result.distribution_with_noise, result.fidelity)

summary = execution.execution_summary
print(summary.makespan, summary.average_waiting_time)
print(summary.machines)  # utilization, busy_time, and qubit_time per machine
print(summary.batches)   # members, shots, start/end, and outcome of each batch
```

`ExecutionSummary` owns execution metrics. `ResultOfSchedule` stores input and
scheduling metadata and references the same report as
`capture_result_schedule.execution_summary` after execution; it has no duplicate
flat metric fields. For example, read
`capture_result_schedule.execution_summary.average_fidelity` instead of
`capture_result_schedule.averageFidelity`. Before execution, the reference is `None`.

- **Strict:** admit jobs in `dispatch_order`, stopping at the first job that
  cannot run. Jobs already admitted continue running.
- **Backfill:** skip waiting jobs and admit later eligible jobs that fit.
- Both policies honor arrival times, fixed machine assignments, and every
  dependency. A dependency completes only when the predecessor has accumulated
  **all required shots**. FFD's dependencies between packing groups remain in
  force, so backfill does not remove those barriers.

Eligible jobs on one machine are merged on disjoint logical qubits. Each batch
runs the smallest remaining shot requirement, subject to the backend shot limit.
Finished jobs leave; unfinished jobs retain their counts and can share the next
batch with newly eligible jobs. Jobs arriving during a batch wait until its end.

Schedules use dictionary keys as job and machine identifiers. Dependencies refer
to the original `JobInfo` objects, not job-name strings. Circuits must be measured
and have all parameters bound; explicit qubit metadata must match circuit width.
Missing shots default to 1024 and missing arrival times to zero. Invalid schedules,
including dependency cycles and strict queue-order cycles, fail before simulation.

Compilation or execution errors fail the affected batch and block its dependent
jobs; unrelated work continues. Failed jobs retain results from earlier successful
batches. Ideal and noisy counts are committed together only after their shot totals
validate. Failures are not automatically retried, and low fidelity does not cause
additional shots.

All execution times are **virtual seconds**: a batch lasts the transpiled circuit's
per-shot duration multiplied by its shots. Separate machines overlap in virtual
time regardless of local simulator runtime. Additional preparation, repetition,
compilation, and network overhead are zero in this model. The ideal reference run
adds no virtual QPU time. `ScheduleLatency` separately measures scheduling wall time.

Timing averages and fidelity include successful jobs only. Utilization includes
submitted failed batches and uses logical qubit-time divided by machine capacity
times the full makespan, including idle intervals. A machine's capacity is a logical
admission limit; transpilation can use other physical wires for routing. Real QPU
submission, isolated physical partitions, cutting, migration, and preemption are
outside this implementation.

Run the test suite with `python -m pytest -q` in the environment where the pinned
requirements are installed.

## Contributing

We welcome contributions! Please fork the repository and submit pull requests.
