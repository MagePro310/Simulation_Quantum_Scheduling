#!/usr/bin/env python3
"""Sequential batch runner for quantum scheduling algorithms with process isolation.

Uses SimulationConfig as the Single Source of Truth (SSOT), loading
all parameters from YAML/JSON and ensuring identical environments across all algorithms.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, TimeoutError
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.models.simulation_config import SimulationConfig


def get_batch_timestamp() -> str:
    """Return current UTC timestamp with microseconds."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _worker_task(algo_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Execute algorithm pipeline in a separate, isolated OS process with config."""
    from source.flow.runner import run_pipeline

    return run_pipeline(algorithm=algo_name, config=config)


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
        "git_commit",
        "config_json",
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
    """Append one result row to the CSV file using direct fallbacks."""
    data = result_data or {}
    exec_summary = data.get("execution_summary") or {}

    row = {
        "run_index": run_index,
        "algorithm": algorithm,
        "start_timestamp": start_time,
        "end_timestamp": end_time,
        "process_status": status,
        "error_message": error_message or "",
        "num_circuits": data.get("num_circuits", ""),
        "name_circuits": data.get("name_circuits", ""),
        "average_qubits": data.get("average_qubits", ""),
        "name_machines": json.dumps(data["name_machines"]) if "name_machines" in data else "",
        "name_schedule": data.get("name_schedule", ""),
        "schedule_latency": data.get("schedule_latency", ""),
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
        "dependency_versions": json.dumps(data.get("dependency_versions", {}))
        if "dependency_versions" in data
        else "",
        "git_commit": data.get("git_commit", ""),
        "config_json": json.dumps(data["config"]) if "config" in data else "",
    }

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)


def main() -> int:
    """Run batch simulation driven by centralized configuration."""
    parser = argparse.ArgumentParser(
        description="Sequential batch runner for quantum scheduling algorithms"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to YAML/JSON simulation config file (default: configs/default_batch.yaml if present)",
    )
    args = parser.parse_args()

    # Load and resolve centralized configuration (Single Source of Truth)
    config = SimulationConfig.resolve(args.config)
    config_dict = config.to_dict()

    results_dir = PROJECT_ROOT / config.batch.output_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    algorithms_to_run = config.batch.algorithms
    cutting_policy = config.scheduling.cutting_policy
    queue_policy = config.execution.queue_policy
    seed = config.execution.seed
    timeout = config.execution.timeout

    print("====================================================================")
    print("             QUANTUM SCHEDULING BATCH SIMULATION RUNNER             ")
    print("====================================================================")
    print(f"Config Source   : {args.config if args.config else 'configs/default_batch.yaml (auto-detected)'}")
    print(f"Algorithms ({len(algorithms_to_run)}): {', '.join(algorithms_to_run)}")
    print(f"Target Workload : {config.workload.benchmark} ({len(config.workload.jobs)} jobs)")
    print(f"Target Machines : {', '.join(config.machines)}")
    print(f"Cutting Policy  : {cutting_policy}")
    print(f"Queue Policy    : {queue_policy}")
    print(f"Random Seed     : {seed}")
    print(f"Timeout / Algo  : {timeout}s")
    print("====================================================================")

    # Create timestamped CSV
    csv_path = results_dir / f"{get_batch_timestamp()}.csv"
    print(f"\nCreating batch results file: {csv_path}")
    create_csv_with_header(csv_path)

    failed_algorithms: list[str] = []

    # Process Isolation: execute each algorithm in a dedicated worker process
    with ProcessPoolExecutor(max_workers=1) as executor:
        for run_index, algo_name in enumerate(algorithms_to_run, start=1):
            print(f"\n[{run_index}/{len(algorithms_to_run)}] Running {algo_name}...")

            start_time = datetime.now(timezone.utc).isoformat()
            future = executor.submit(_worker_task, algo_name, config_dict)

            try:
                result_data = future.result(timeout=timeout)
                status, error = "SUCCESS", None
            except TimeoutError:
                result_data = None
                status, error = "FAILED", f"Process timeout ({timeout}s)"
            except Exception as e:
                result_data = None
                status, error = "FAILED", f"Exception: {str(e)[:500]}"

            end_time = datetime.now(timezone.utc).isoformat()
            print(f"  Status: {status}")
            if error:
                failed_algorithms.append(algo_name)
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

    # Auto-generate comparison report and charts if requested
    if config.batch.auto_compare and csv_path.exists():
        print("\n" + "=" * 68)
        print("  Auto-generating comparison report and charts...")
        print("=" * 68)
        try:
            from source.analysis.report_generator import run_comparison

            analysis_dir = run_comparison(csv_path)
            print(f"\nReport generated at: {analysis_dir / 'comparison_report.md'}")
        except Exception as e:
            print(f"Warning: Could not auto-generate comparison report: {e}", file=sys.stderr)

    if failed_algorithms:
        print(f"\nFailed algorithms: {', '.join(failed_algorithms)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
