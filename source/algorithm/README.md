# Algorithm Developer Guide

The [`source/algorithm/`](.) directory hosts scheduling algorithms for the quantum simulation platform.

---

## 1. Directory Overview

- [`interfaces.py`](interfaces.py): `ScheduleAlgorithmProtocol` defining the `execute(scheduler_job, machines)` interface (PEP 544).
- [`registry.py`](registry.py): Central registry with `@register_algorithm` (one exact, case-sensitive name per algorithm), `get_algorithm(name)`, and `list_algorithms()`.
- [`common.py`](common.py): Helper functions for sorting and cluster capacity analysis.
- `heuristic/`: Built-in implementations:
  - [`ffd.py`](heuristic/ffd.py): First Fit Decreasing.
  - [`ffd_v2.py`](heuristic/ffd_v2.py): FFD with pre-sort circuit cutting.
  - [`adaptive_ffd.py`](heuristic/adaptive_ffd.py): Adaptive FFD (on-the-fly slack cutting).
  - [`lpt.py`](heuristic/lpt.py): Longest Processing Time first.
  - [`qgroup.py`](heuristic/qgroup.py): QGroup (Clustering + MILP, IEEE QCE 2024).

---

## 2. Adding a New Algorithm in 3 Steps

### Step 1: Implement the Class with `@register_algorithm`

Create `source/algorithm/heuristic/my_algo.py`:

```python
from source.algorithm.registry import register_algorithm
from source.models.job import SchedulerJobInfo
from source.models.machine import MachineCharacteristic

@register_algorithm("MyAlgo")
class MyAlgo:
    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        machine_names = list(machines.keys())
        for idx, job in enumerate(scheduler_job.values()):
            job.assigned_machine = machine_names[idx % len(machine_names)]
            job.dispatch_order = idx
        return scheduler_job
```

### Step 2: Export in `source/algorithm/heuristic/__init__.py`

```python
from source.algorithm.heuristic.my_algo import MyAlgo

__all__ = [..., "MyAlgo"]
```

### Step 3: Run Immediately

- **Single CLI Run**:
  ```bash
  python run_simulation.py -a MyAlgo
  ```
- **Batch Benchmark**:
  Add `"MyAlgo"` to `batch.algorithms` in your YAML config (for example [`configs/default_batch.yaml`](../../configs/default_batch.yaml)).

---

## 3. Circuit Cutting Helper

Use [`SchedulingCutterHelper`](../flow/schedule/cutting/schedule_cutter_helper.py) within your algorithm for on-demand circuit partitioning:

```python
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper

# Batch cut oversized jobs
cut_jobs = SchedulingCutterHelper.cut_jobs(scheduler_job, target_qubits=max_capacity)

# Cut single job to fit bin slack
if SchedulingCutterHelper.can_cut(job):
    sub_jobs = SchedulingCutterHelper.cut_job(job, cluster_sizes=[slack, remainder])
```
