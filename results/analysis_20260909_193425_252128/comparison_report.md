# Quantum Scheduling Batch Results Comparison

## Execution Status

| Algorithm | Status | Error |
|-----------|--------|-------|
| FFD | ✅ SUCCESS |  |
| LPT | ✅ SUCCESS |  |

## Workload and Configuration

- **Circuits**: 10 (ghz)
- **Average Qubits**: 3.0
- **Machines**: ["fake_belem", "fake_bogota"]
- **Seed**: 0
- **Queue Policy**: strict
- **Baseline Algorithm**: FFD

## Scheduling Latency (wall-clock)

| Algorithm | Latency (s) | Difference from baseline |
|-----------|-------------|-------------------------|
| FFD | 0.0002911090850830078 | baseline |
| LPT | 0.0002601146697998047 | -0.0000 |

## Execution Summary Metrics

All times in seconds (virtual execution time).

| Metric | FFD | LPT |
|--------|--------|--------|
| Makespan | 0.0299 | 0.0359 (+0.0061, +20.40%) |
| Avg Turnaround Time | 0.0177 | 0.0216 (+0.0038, +21.55%) |
| Avg Waiting Time | 0.0108 | 0.0147 (+0.0039, +36.43%) |
| Avg Response Time | 0.0108 | 0.0147 (+0.0039, +36.43%) |
| Job Completion Rate | 334.9490 | 278.1912 (-56.7578, -16.95%) |
| Avg Fidelity | 0.8734 | 0.8644 (-0.0091, -1.04%) |

**Metric Definitions:**

- **Makespan**: Total virtual execution time
- **Avg Turnaround Time**: Job submission to completion (successful jobs only)
- **Avg Waiting Time**: Time between job batches (successful jobs only)
- **Avg Response Time**: Initial waiting time (successful jobs only)
- **Job Completion Rate**: Throughput: successes / makespan
- **Avg Fidelity**: Mean fidelity (successful jobs only)

**Note**: Values in parentheses show (difference from baseline, % change)

## Job Outcomes

| Algorithm | Succeeded | Failed | Blocked | Total |
|-----------|-----------|--------|---------|-------|
| FFD | 10 | 0 | 0 | 10 |
| LPT | 10 | 0 | 0 | 10 |

## Machine Utilization

| Machine | FFD Util | LPT Util | FFD Busy Time | LPT Busy Time |
|---|---|---|---|---|
| fake_belem | 1.0000 | 1.0000 | 0.03s | 0.04s |
| fake_bogota | 0.6656 | 0.8966 | 0.02s | 0.03s |

**Note**: Utilization measures logical qubit allocation over capacity × makespan.

## Batch Execution Records

### FFD Batches

Total batches: 7

| Batch | Machine | Jobs | Shots | Start | End | Duration | Status |
|-------|---------|------|-------|-------|-----|----------|--------|
| 1 | fake_belem | 1 | 1024 | 0.00s | 0.01s | 0.01s | SUCCEEDED |
| 2 | fake_bogota | 1 | 1024 | 0.00s | 0.01s | 0.01s | SUCCEEDED |
| 3 | fake_bogota | 2 | 1024 | 0.01s | 0.01s | 0.01s | SUCCEEDED |
| 4 | fake_belem | 1 | 1024 | 0.01s | 0.02s | 0.01s | SUCCEEDED |
| 5 | fake_bogota | 2 | 1024 | 0.01s | 0.02s | 0.01s | SUCCEEDED |
| 6 | fake_belem | 2 | 1024 | 0.02s | 0.02s | 0.01s | SUCCEEDED |
| 7 | fake_belem | 1 | 1024 | 0.02s | 0.03s | 0.01s | SUCCEEDED |

### LPT Batches

Total batches: 10

| Batch | Machine | Jobs | Shots | Start | End | Duration | Status |
|-------|---------|------|-------|-------|-----|----------|--------|
| 1 | fake_belem | 1 | 1024 | 0.00s | 0.01s | 0.01s | SUCCEEDED |
| 2 | fake_bogota | 1 | 1024 | 0.00s | 0.01s | 0.01s | SUCCEEDED |
| 3 | fake_bogota | 1 | 1024 | 0.01s | 0.01s | 0.01s | SUCCEEDED |
| 4 | fake_belem | 1 | 1024 | 0.01s | 0.02s | 0.01s | SUCCEEDED |
| 5 | fake_bogota | 1 | 1024 | 0.01s | 0.02s | 0.01s | SUCCEEDED |
| 6 | fake_belem | 1 | 1024 | 0.02s | 0.02s | 0.01s | SUCCEEDED |
| 7 | fake_bogota | 1 | 1024 | 0.02s | 0.03s | 0.01s | SUCCEEDED |
| 8 | fake_belem | 1 | 1024 | 0.02s | 0.03s | 0.01s | SUCCEEDED |
| 9 | fake_bogota | 1 | 1024 | 0.03s | 0.03s | 0.01s | SUCCEEDED |
| 10 | fake_belem | 1 | 1024 | 0.03s | 0.04s | 0.01s | SUCCEEDED |

