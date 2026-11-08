# Execution Engine Guide

The [`source/flow/execution/`](.) module manages the discrete-event execution engine, multi-programming co-location, and circuit cutting reconstruction.

---

## 1. Module Overview

| File | Primary Responsibility |
| :--- | :--- |
| [`orchestrator.py`](orchestrator.py) | **ExecutionPhase**: Core engine managing virtual timeline (`now`), min-heap event queue, and machine state transitions. |
| [`interfaces.py`](interfaces.py) | **Protocols**: `JobDispatcherProtocol`, `LayoutStrategy`, `TimelineReporterProtocol` (PEP 544). |
| [`job_dispatcher.py`](job_dispatcher.py) | **Dispatcher**: Evaluates arrival times, DAG dependencies, strict/backfill policies, and cascade error handling. |
| [`batch_executor.py`](batch_executor.py) | **Batch Executor**: Coordinates multi-programming batch preparation and execution against Qiskit Aer. |
| [`circuit_composer.py`](circuit_composer.py) | **Composer**: Packs independent circuits or QPD subexperiments onto a shared QPU register. |
| [`quantum_simulator.py`](quantum_simulator.py) | **Simulator**: Executes noisy or ideal simulations on IBM fake backends via Qiskit Aer. |
| [`reconstruction_handler.py`](reconstruction_handler.py) | **Reconstruction Handler**: Accumulates subcircuit shot outcomes and triggers parent reconstruction. |
| [`circuit_reconstructor.py`](circuit_reconstructor.py) | **Reconstructor**: Reconstructs output bitstring distributions from Z-basis expectation values with a direct inverse Walsh-Hadamard sum (O(4ⁿ) in the parent's qubit count). |
| [`timeline_reporter.py`](timeline_reporter.py) | **Reporter**: Timeline logging (`ConsoleTimelineReporter`, `SilentTimelineReporter`). |
| [`metrics_calculator.py`](metrics_calculator.py) | **Metrics**: Computes makespan, turnaround/waiting times, qubit-time utilization, and fidelity. |

---

## 2. Dependency Injection & Extensibility

All core components support dependency injection in `ExecutionPhase`:

```python
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.execution.timeline_reporter import SilentTimelineReporter

# Run simulation in silent mode (no terminal logs during batch benchmarks)
silent_phase = ExecutionPhase(reporter=SilentTimelineReporter())
results = silent_phase.execute(machines, scheduled_jobs)
```
