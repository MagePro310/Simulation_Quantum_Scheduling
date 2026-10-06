#!/usr/bin/env python3
"""Sequential batch runner for quantum scheduling algorithms with process isolation."""

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"

# Module import map for in-memory execution with process isolation
ALGORITHMS = [
    {"name": "FFD", "module": "implement.FFD"},
    {"name": "FFD_v2", "module": "implement.FFD_v2"},
    {"name": "LPT", "module": "implement.LPT"},
    {"name": "QGroup", "module": "implement.QGroup"},
]

TIMEOUT = 600  # seconds per algorithm


def get_batch_timestamp() -> str:
    """Return current UTC timestamp with microseconds."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")


def _worker_task(module_name: str, **kwargs) -> dict[str, Any]:
    """Execute algorithm pipeline in a separate, isolated OS process."""
    import importlib
    mod = importlib.import_module(module_name)
    return mod.run_algorithm(**kwargs)


def create_csv_with_header(csv_path: Path) -> None:
    """Create CSV file with header row for batch results."""
    headers = [
        "run_index",
        "algorithm",
        "start_timestamp",
        "end_timestamp",
        "process_status",
        "error_message",
        "num_circuits",
        "name_circuits",
        "average_qubits",
        "name_machines",
        "name_schedule",
        "schedule_latency",
        "makespan",
        "average_turnaround_time",
        "average_waiting_time",
        "average_fidelity",
        "cluster_qubit_utilization",
        "total_cutting_overhead",
        "succeeded_jobs",
        "failed_jobs",
        "blocked_jobs",
        "cutting_policy",
        "optional_cutting",
        "optional_cutting_policy",
        "machines_json",
        "batches_json",
        "workload_fingerprint",
        "machine_config",
        "seed",
        "queue_policy",
        "dependency_versions",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()


def append_result_row(
    csv_path: Path,
    run_index: int,
    algorithm: str,
    start_time: str,
    end_time: str,
    status: str,
    error_message: str | None,
    result_data: dict[str, Any] | None,
) -> None:
    """Append one result row to the CSV file using direct fallbacks (no nested if-else)."""
    data = result_data or {}
    exec_summary = data.get("execution_summary") or {}

    row = {
        "run_index": run_index,
        "algorithm": algorithm,
        "start_timestamp": start_time,
        "end_timestamp": end_time,
        "process_status": status,
        "error_message": error_message or "",
        "num_circuits": data.get("numCircuits", ""),
        "name_circuits": data.get("nameCircuits", ""),
        "average_qubits": data.get("averageQubits", ""),
        "name_machines": json.dumps(data.get("nameMachines", "")) if "nameMachines" in data else "",
        "name_schedule": data.get("nameSchedule", ""),
        "schedule_latency": data.get("ScheduleLatency") or data.get("schedule_latency", ""),
        "makespan": exec_summary.get("makespan", ""),
        "average_turnaround_time": exec_summary.get("average_turnaround_time", ""),
        "average_waiting_time": exec_summary.get("average_waiting_time", ""),
        "average_fidelity": exec_summary.get("average_fidelity", ""),
        "cluster_qubit_utilization": exec_summary.get("cluster_qubit_utilization", ""),
        "total_cutting_overhead": exec_summary.get("total_cutting_overhead", ""),
        "succeeded_jobs": exec_summary.get("succeeded_jobs", ""),
        "failed_jobs": exec_summary.get("failed_jobs", ""),
        "blocked_jobs": exec_summary.get("blocked_jobs", ""),
        "cutting_policy": data.get("exceed_cutting_policy", ""),
        "optional_cutting": data.get("optional_cutting", False),
        "optional_cutting_policy": data.get("optional_cutting_policy", ""),
        "machines_json": json.dumps(exec_summary.get("machines", "")) if exec_summary.get("machines") else "",
        "batches_json": json.dumps(exec_summary.get("batches", "")) if exec_summary.get("batches") else "",
        "workload_fingerprint": data.get("workload_fingerprint", ""),
        "machine_config": data.get("machine_config", ""),
        "seed": data.get("seed", "0"),
        "queue_policy": data.get("queue_policy", "strict"),
        "dependency_versions": json.dumps(data.get("dependency_versions", {})) if "dependency_versions" in data else "",
    }

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)


def main() -> int:
    """Run batch simulation and collect results."""
    parser = argparse.ArgumentParser(description="Sequential batch runner for quantum scheduling algorithms")
    parser.add_argument(
        "--cutting-policy",
        choices=["greedy", "half"],
        default="greedy",
        help="Mandatory cut policy for circuits exceeding machine capacity: 'greedy' or 'half' (default: 'greedy')",
    )
    parser.add_argument(
        "--optional-cutting",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override optional cutting for all algorithms (default: use each algorithm's native setup)",
    )
    parser.add_argument(
        "--optional-cutting-policy",
        choices=["half"],
        default="half",
        help="Policy for optional cutting stage: 'half' (default: 'half', extensible)",
    )
    parser.add_argument(
        "--queue-policy",
        choices=["strict", "relaxed", "backfill"],
        default="strict",
        help="Queue dispatch / backfilling policy: 'strict', 'relaxed', or 'backfill' (default: 'strict')",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for transpilation and simulation reproducibility (default: 0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT,
        help=f"Timeout in seconds per algorithm (default: {TIMEOUT})",
    )
    args = parser.parse_args()

    enable_optional = args.optional_cutting
    if enable_optional is None:
        opt_summary = "native (per-algorithm setup)"
    else:
        opt_summary = f"override: enabled ({args.optional_cutting_policy})" if enable_optional else "override: disabled"

    print(f"Configured algorithms: {', '.join(a['name'] for a in ALGORITHMS)}")
    print(f"Circuit cutting: Mandatory exceed={args.cutting_policy}, Optional={opt_summary}")

    # Create timestamped CSV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / f"{get_batch_timestamp()}.csv"
    print(f"Creating batch results file: {csv_path}")
    create_csv_with_header(csv_path)

    # Process Isolation: execute each algorithm in a dedicated worker process
    with ProcessPoolExecutor(max_workers=1) as executor:
        for run_index, algo in enumerate(ALGORITHMS, start=1):
            algo_name = algo["name"]
            opt_log = "native setup" if enable_optional is None else str(enable_optional)
            print(f"\n[{run_index}/{len(ALGORITHMS)}] Running {algo_name} (policy={args.cutting_policy}, optional_cutting={opt_log}, queue={args.queue_policy}, seed={args.seed})...")

            kwargs = {
                "cutting_policy": args.cutting_policy,
                "optional_cutting_policy": args.optional_cutting_policy,
                "queue_policy": args.queue_policy,
                "seed": args.seed,
            }
            if enable_optional is not None:
                kwargs["optional_cutting"] = enable_optional

            start_time = datetime.utcnow().isoformat()
            future = executor.submit(_worker_task, algo["module"], **kwargs)

            # DUY NHẤT 1 TẦNG BẢO VỆ NGOÀI CÙNG
            try:
                result_data = future.result(timeout=args.timeout)
                status, error = "SUCCESS", None
            except TimeoutError:
                result_data = None
                status, error = "FAILED", f"Process timeout ({args.timeout}s)"
            except Exception as e:
                result_data = None
                status, error = "FAILED", f"Exception: {str(e)[:500]}"

            end_time = datetime.utcnow().isoformat()
            print(f"  Status: {status}")
            if error:
                print(f"  Error: {error}")

            append_result_row(
                csv_path,
                run_index,
                algo_name,
                start_time,
                end_time,
                status,
                error,
                result_data if status == "SUCCESS" else None,
            )
            print("  Result appended to CSV")

    print(f"\nBatch complete. Results saved to: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
