"""Serialization and terminal formatting utilities for simulation results."""

from __future__ import annotations

from typing import Any

from source.models.schedule_result import ResultOfSchedule
from source.utils.provenance import dependency_versions


def serialize_result(capture_result_schedule: ResultOfSchedule) -> dict[str, Any]:
    """Convert ResultOfSchedule to a JSON-serializable dictionary."""
    result_dict: dict[str, Any] = {
        "num_circuits": capture_result_schedule.num_circuits,
        "name_circuits": capture_result_schedule.name_circuits,
        "average_qubits": capture_result_schedule.average_qubits,
        "name_machines": capture_result_schedule.name_machines,
        "name_schedule": capture_result_schedule.name_schedule,
        "schedule_latency": capture_result_schedule.schedule_latency,
        "exceed_cutting_policy": capture_result_schedule.exceed_cutting_policy,
        "optional_cutting": capture_result_schedule.optional_cutting,
        "optional_cutting_policy": capture_result_schedule.optional_cutting_policy,
        "shot_distribution": capture_result_schedule.shot_distribution,
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
                "qubit_time": getattr(batch, "occupied_qubit_time", None),
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

    result_dict["seed"] = capture_result_schedule.seed
    result_dict["queue_policy"] = capture_result_schedule.queue_policy
    result_dict["workload_fingerprint"] = capture_result_schedule.workload_fingerprint
    result_dict["machine_config"] = str(capture_result_schedule.name_machines)
    result_dict["git_commit"] = capture_result_schedule.git_commit
    result_dict["config"] = capture_result_schedule.config
    result_dict["dependency_versions"] = dependency_versions()

    return result_dict


def print_schedule_result(
    capture_result_schedule: ResultOfSchedule,
    schedule_result: dict | None = None,
) -> None:
    """Print comprehensive scheduling and execution results to terminal."""
    algo = capture_result_schedule.name_schedule or "Unknown"
    exceed_policy = capture_result_schedule.exceed_cutting_policy
    opt_cutting = capture_result_schedule.optional_cutting
    opt_policy = capture_result_schedule.optional_cutting_policy or "half"
    queue_policy = capture_result_schedule.queue_policy
    latency = capture_result_schedule.schedule_latency
    num_circuits = capture_result_schedule.num_circuits
    circ_type = capture_result_schedule.name_circuits or "N/A"
    avg_qubits = capture_result_schedule.average_qubits
    machines = capture_result_schedule.name_machines

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
