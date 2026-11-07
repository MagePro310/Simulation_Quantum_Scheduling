# Quantum Circuit Scheduling Simulator

A discrete-event simulation platform for quantum circuit scheduling on heterogeneous QPU clusters. Supports **multi-programming** (spatial co-location), **circuit cutting** (QPD via `qiskit-addon-cutting`), and noise-aware execution via Qiskit Aer fake backends.

---

## Features

- **Discrete-Event Simulation**: Min-heap event timeline modeling job arrivals, compilation, switching overhead, and QPU execution.
- **Quantum Multi-Programming**: Spatial co-location of independent circuits onto larger QPUs to maximize space-time qubit utilization.
- **Circuit Cutting (QPD)**: Automatic partitioning of oversized circuits, joint co-execution, and FWHT-based probability reconstruction.
- **Hardware Noise Modeling**: Realistic noise simulation using IBM fake backends (`FakeManila`, `FakeSherbrooke`, etc.) via Qiskit Aer.
- **Extensible Architecture**: Central registry (`@register_algorithm`) for plugging in custom scheduling algorithms without modifying core engine code.

---

## Quick Start

### 1. Installation

```bash
conda create -n scquan python=3.12 -y
conda activate scquan
pip install -r requirements.txt
pip install -e .
```

### 2. Run Simulation

- **Single Algorithm**:
  ```bash
  python run_simulation.py -a FFD
  # List all available algorithms:
  python run_simulation.py --list
  ```

- **Batch Benchmark (runs all algorithms in isolated processes)**:
  ```bash
  python run_batch.py
  ```
  Exports metrics CSV to `results/`, comparative charts to `results/analysis_<timestamp>/`, and Gantt charts to `results/charts/`.

- **Analyze Existing CSV Results**:
  ```bash
  python compare_results.py results/<filename>.csv
  ```

---

## Project Structure

```text
.
├── configs/                 # YAML configuration (workload, cluster, batch parameters)
├── source/
│   ├── models/              # Dataclasses (JobInfo, MachineCharacteristic, SimulationConfig)
│   ├── flow/                # 3-phase simulation pipeline
│   │   ├── input/           # Phase 1: Workload & cluster loader
│   │   ├── schedule/        # Phase 2: Pre-cutting & scheduling algorithms
│   │   └── execution/       # Phase 3: Discrete-event engine, multi-programming & reconstruction
│   ├── algorithm/           # Central registry & heuristic algorithms (FFD, LPT, QGroup...)
│   ├── simulator/           # Dynamic IBM fake backend loader
│   ├── utils/               # Timing estimation, fidelity (Hellinger, TVD), Gantt chart generator
│   └── analysis/            # Benchmark metrics, comparison report & chart generators
├── tests/                   # Pytest test suite (46 tests)
├── run_simulation.py        # CLI for single-algorithm execution
├── run_batch.py             # Batch benchmark runner
└── compare_results.py       # Standalone report & chart generation CLI
```

---

## Adding a Custom Algorithm

Define your algorithm in `source/algorithm/heuristic/` with `@register_algorithm`:

```python
from source.algorithm.registry import register_algorithm
from source.models.job import SchedulerJobInfo
from source.models.machine import MachineCharacteristic

@register_algorithm("MyAlgorithm")
class MyAlgorithm:
    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        machine_names = list(machines.keys())
        for idx, job in enumerate(scheduler_job.values()):
            assigned = machine_names[idx % len(machine_names)]
            job.assigned_machine = assigned
            job.dispatch_order = idx
        return scheduler_job
```

Export your class in `source/algorithm/heuristic/__init__.py`, then run:
```bash
python run_simulation.py -a MyAlgorithm
```

---

## Testing

```bash
pytest tests
```
