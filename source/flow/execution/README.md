# Execution Engine Guide

The [`source/flow/execution/`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/) module manages the discrete-event execution engine, multi-programming co-location, and circuit cutting reconstruction.

---

## 1. Module Overview

| File | Primary Responsibility |
| :--- | :--- |
| [`orchestrator.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/orchestrator.py) | **ExecutionPhase**: Core engine managing virtual timeline (`now`), min-heap event queue, and machine state transitions. |
| [`interfaces.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/interfaces.py) | **Protocols**: `JobDispatcherProtocol`, `LayoutStrategy`, `TimelineReporterProtocol` (PEP 544). |
| [`job_dispatcher.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/job_dispatcher.py) | **Dispatcher**: Evaluates arrival times, DAG dependencies, strict/backfill policies, and cascade error handling. |
| [`batch_executor.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/batch_executor.py) | **Batch Executor**: Coordinates multi-programming batch preparation and execution against Qiskit Aer. |
| [`circuit_composer.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/circuit_composer.py) | **Composer**: Packs independent circuits or QPD subexperiments onto a shared QPU register. |
| [`quantum_simulator.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/quantum_simulator.py) | **Simulator**: Executes noisy or ideal simulations on IBM fake backends via Qiskit Aer. |
| [`reconstruction_handler.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/reconstruction_handler.py) | **Reconstruction Handler**: Accumulates subcircuit shot outcomes and triggers parent reconstruction. |
| [`circuit_reconstructor.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/circuit_reconstructor.py) | **Reconstructor**: Reconstructs output bitstring distributions using Fast Walsh-Hadamard Transform (FWHT). |
| [`timeline_reporter.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/timeline_reporter.py) | **Reporter**: Timeline logging (`ConsoleTimelineReporter`, `SilentTimelineReporter`). |
| [`metrics_calculator.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/metrics_calculator.py) | **Metrics**: Computes makespan, turnaround/waiting times, qubit-time utilization, and fidelity. |

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
