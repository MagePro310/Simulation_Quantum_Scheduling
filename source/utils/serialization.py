"""Serialization and terminal formatting utilities for simulation results."""

from __future__ import annotations

from typing import Any
import matplotlib
import numpy
import qiskit

from source.models.schedule_result import ResultOfSchedule


def serialize_result(capture_result_schedule: ResultOfSchedule) -> dict[str, Any]:
    """Convert ResultOfSchedule to a JSON-serializable dictionary."""
    num_circuits = getattr(capture_result_schedule, "num_circuits", None)
    if num_circuits is None:
        num_circuits = getattr(capture_result_schedule, "numCircuits", 0)

    name_circuits = getattr(capture_result_schedule, "name_circuits", None)
    if name_circuits is None:
        name_circuits = getattr(capture_result_schedule, "nameCircuits", "")

    avg_qubits = getattr(capture_result_schedule, "average_qubits", None)
    if avg_qubits is None:
        avg_qubits = getattr(capture_result_schedule, "averageQubits", 0.0)

    name_machines = getattr(capture_result_schedule, "name_machines", None)
    if name_machines is None:
        name_machines = getattr(capture_result_schedule, "nameMachines", [])

    name_schedule = getattr(capture_result_schedule, "name_schedule", None)
    if name_schedule is None:
        name_schedule = getattr(capture_result_schedule, "nameSchedule", "")

    latency = getattr(capture_result_schedule, "schedule_latency", None)
    if latency is None:
        latency = getattr(capture_result_schedule, "ScheduleLatency", 0.0)

    result_dict: dict[str, Any] = {
        "num_circuits": num_circuits,
        "name_circuits": name_circuits,
        "average_qubits": avg_qubits,
        "name_machines": name_machines,
        "name_schedule": name_schedule,
        "schedule_latency": latency,
        # Legacy key aliases for backward compatibility with external consumer tools
        "numCircuits": num_circuits,
        "nameCircuits": name_circuits,
        "averageQubits": avg_qubits,
        "nameMachines": name_machines,
        "nameSchedule": name_schedule,
        "ScheduleLatency": latency,
        "exceed_cutting_policy": getattr(capture_result_schedule, "exceed_cutting_policy", "greedy"),
        "optional_cutting": getattr(capture_result_schedule, "optional_cutting", False),
        "optional_cutting_policy": getattr(capture_result_schedule, "optional_cutting_policy", None),
    }

    if capture_result_schedule.execution_summary:
        exec_sum = capture_result_schedule.execution_summary

        batches_serialized = []
        for batch in exec_sum.batches:
            batch_dict = {
                "batch_id": getattr(batch, "batch_id", 0),
                "machine_name": getattr(batch, "machine_name", ""),
                "job_ids": list(getattr(batch, "job_ids", ())),
                "shots": getattr(batch, "shots", 0),
                "start_time": getattr(batch, "start_time", 0.0),
                "end_time": getattr(batch, "end_time", 0.0),
                "logical_qubits": getattr(batch, "logical_qubits", 0),
                "status": getattr(batch, "status", "UNKNOWN"),
                "error_reason": getattr(batch, "error_reason", None),
            }
            batches_serialized.append(batch_dict)

        result_dict["execution_summary"] = {
            "makespan": exec_sum.makespan,
            "average_turnaround_time": exec_sum.average_turnaround_time,
            "average_waiting_time": exec_sum.average_waiting_time,
            "average_fidelity": exec_sum.average_fidelity,
            "cluster_qubit_utilization": exec_sum.cluster_qubit_utilization,
            "total_cutting_overhead": exec_sum.total_cutting_overhead,
            "succeeded_jobs": exec_sum.succeeded_jobs,
            "failed_jobs": exec_sum.failed_jobs,
            "blocked_jobs": exec_sum.blocked_jobs,
            "machines": {
                name: {
                    "machine_name": m.machine_name,
                    "utilization": m.utilization,
                    "busy_time": m.busy_time,
                    "qubit_time": m.qubit_time,
                }
                for name, m in exec_sum.machines.items()
            },
            "batches": batches_serialized,
        }
    else:
        result_dict["execution_summary"] = None

    result_dict["seed"] = getattr(capture_result_schedule, "seed", 0)
    result_dict["queue_policy"] = getattr(capture_result_schedule, "queue_policy", "strict")
    result_dict["workload_fingerprint"] = f"{num_circuits}_{name_circuits}"
    result_dict["machine_config"] = str(name_machines)
    result_dict["dependency_versions"] = {
        "qiskit": qiskit.__version__,
        "numpy": numpy.__version__,
        "matplotlib": matplotlib.__version__,
    }

    return result_dict


def print_schedule_result(
    capture_result_schedule: ResultOfSchedule,
    schedule_result: dict | None = None,
) -> None:
    """Print comprehensive scheduling and execution results to terminal."""
    algo = getattr(capture_result_schedule, "name_schedule", "") or getattr(
        capture_result_schedule, "nameSchedule", "Unknown"
    )
    exceed_policy = getattr(capture_result_schedule, "exceed_cutting_policy", "greedy")
    opt_cutting = getattr(capture_result_schedule, "optional_cutting", False)
    opt_policy = getattr(capture_result_schedule, "optional_cutting_policy", "half") or "half"
    queue_policy = getattr(capture_result_schedule, "queue_policy", "strict")

    latency = getattr(capture_result_schedule, "schedule_latency", None)
    if latency is None:
        latency = getattr(capture_result_schedule, "ScheduleLatency", 0.0)

    num_circuits = getattr(capture_result_schedule, "num_circuits", None)
    if num_circuits is None:
        num_circuits = getattr(capture_result_schedule, "numCircuits", 0)

    circ_type = getattr(capture_result_schedule, "name_circuits", "") or getattr(
        capture_result_schedule, "nameCircuits", "N/A"
    )

    avg_qubits = getattr(capture_result_schedule, "average_qubits", None)
    if avg_qubits is None:
        avg_qubits = getattr(capture_result_schedule, "averageQubits", 0.0)

    machines = getattr(capture_result_schedule, "name_machines", None)
    if machines is None:
        machines = getattr(capture_result_schedule, "nameMachines", [])

    if isinstance(machines, list):
        machines_str = ", ".join(machines)
    else:
        machines_str = str(machines)

    opt_str = f"Enabled ({opt_policy})" if opt_cutting else "Disabled (exceed only)"

    width = 68
    print()
    print("=" * width)
    print(f"SCHEDULING & EXECUTION RESULTS: {algo}".center(width))
    print("=" * width)
    print(f"  • Algorithm               : {algo}")
    print(f"  • Mandatory Cut (Exceed)  : {exceed_policy} (always active for > max_capacity)")
    print(f"  • Optional Cut (Remaining): {opt_str}")
    print(f"  • Queue / Backfill Policy : {queue_policy}")
    print(f"  • Schedule Latency        : {latency:.6f} s")
    print(f"  • Target Workload         : {num_circuits} circuits ({circ_type}), avg {avg_qubits:.1f} qubits")
    print(f"  • Target Machines         : {machines_str}")

    summary = capture_result_schedule.execution_summary
    if summary:
        print("-" * width)
        print("CORE EXECUTION PERFORMANCE METRICS".center(width))
        print("-" * width)
        print(f"  • Virtual Makespan        : {summary.makespan:.6f} s")
        print(
            f"  • Completed Jobs          : {summary.succeeded_jobs} succeeded, {summary.failed_jobs} failed, {summary.blocked_jobs} blocked"
        )
        print(f"  • Avg Turnaround Time     : {summary.average_turnaround_time:.6f} s")
        print(f"  • Avg Waiting Time        : {summary.average_waiting_time:.6f} s")
        print(f"  • Avg Fidelity (Qubit-wt) : {summary.average_fidelity:.4f}")
        print(f"  • Cluster Qubit Util      : {summary.cluster_qubit_utilization * 100:.2f}%")
        print(f"  • Total Cutting Overhead  : {summary.total_cutting_overhead:g}")

        if summary.machines:
            print("-" * width)
            print("MACHINE UTILIZATION".center(width))
            print("-" * width)
            for m_name, m_stat in summary.machines.items():
                print(
                    f"  • {m_name:<16} : qubit space-time util {m_stat.utilization * 100:>6.2f}%, busy time {m_stat.busy_time:.6f} s, qubit-time {m_stat.qubit_time:.4f}"
                )

    print("=" * width)
    print()
