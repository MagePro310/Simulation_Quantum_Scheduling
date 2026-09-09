#!/usr/bin/env python3
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"

# Add new algorithms to this list; script paths are relative to PROJECT_ROOT.
ALGORITHMS = [
    {"name": "FFD", "script": "implement/FFD.py"},
    {"name": "LPT", "script": "implement/LPT.py"},
]

# Batch settings
SEED = 0
QUEUE_POLICY = "strict"
TIMEOUT = 600  # seconds per algorithm

"""Sequential batch runner for quantum scheduling algorithms.

Reads algorithm configurations from batch_config.py and runs each algorithm
in a separate process, collecting results into a single timestamped CSV file.

To add a new algorithm: edit batch_config.py and add it to the ALGORITHMS list.
"""

import csv
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def get_batch_timestamp() -> str:
    """Return current time in Asia/Ho_Chi_Minh timezone with microseconds."""
    # Using UTC and noting timezone in filename since pytz not in requirements
    now = datetime.utcnow()
    # Format: YYYYMMDD_HHMMSS_microseconds
    return now.strftime("%Y%m%d_%H%M%S_%f")


def create_csv_with_header(csv_path: Path) -> None:
    """Create CSV file with header row for batch results."""
    headers = [
        "run_index",
        "algorithm",
        "start_timestamp",
        "end_timestamp",
        "process_status",
        "error_message",
        # ResultOfSchedule fields
        "num_circuits",
        "name_circuits",
        "average_qubits",
        "name_machines",
        "name_schedule",
        "schedule_latency",
        # ExecutionSummary scalar fields
        "makespan",
        "total_turnaround_time",
        "total_waiting_time",
        "total_response_time",
        "average_turnaround_time",
        "average_waiting_time",
        "average_response_time",
        "job_completion_rate",
        "average_fidelity",
        "succeeded_jobs",
        "failed_jobs",
        "blocked_jobs",
        # Nested/list fields as JSON
        "machines_json",
        "batches_json",
        # Fingerprints and metadata
        "workload_fingerprint",
        "machine_config",
        "seed",
        "queue_policy",
        "dependency_versions",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()


def run_algorithm(algorithm_name: str, script_path: Path, output_json: Path) -> tuple[str, str | None]:
    """Run algorithm script in a separate process.

    Returns:
        (status, error_message) tuple where status is 'SUCCESS' or 'FAILED'
    """

    try:
        result = subprocess.run(
            [sys.executable, str(script_path), "--json-output", str(output_json)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd=PROJECT_ROOT,
        )

        if result.returncode == 0:
            return ("SUCCESS", None)
        else:
            error_msg = f"Exit code {result.returncode}: {result.stderr[:500]}"
            return ("FAILED", error_msg)

    except subprocess.TimeoutExpired:
        return ("FAILED", f"Process timeout ({TIMEOUT}s)")
    except Exception as e:
        return ("FAILED", f"Exception: {str(e)[:500]}")


def load_result_json(json_path: Path) -> dict[str, Any] | None:
    """Load result from JSON file, return None if file doesn't exist or is invalid."""
    try:
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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
    """Append one result row to the CSV file."""

    row = {
        "run_index": run_index,
        "algorithm": algorithm,
        "start_timestamp": start_time,
        "end_timestamp": end_time,
        "process_status": status,
        "error_message": error_message or "",
    }

    # If we have result data, extract fields
    if result_data:
        row["num_circuits"] = result_data.get("numCircuits", "")
        row["name_circuits"] = result_data.get("nameCircuits", "")
        row["average_qubits"] = result_data.get("averageQubits", "")
        row["name_machines"] = json.dumps(result_data.get("nameMachines", ""))
        row["name_schedule"] = result_data.get("nameSchedule", "")
        row["schedule_latency"] = result_data.get("ScheduleLatency", "")

        # ExecutionSummary fields
        exec_summary = result_data.get("execution_summary", {}) or {}
        row["makespan"] = exec_summary.get("makespan", "")
        row["total_turnaround_time"] = exec_summary.get("total_turnaround_time", "")
        row["total_waiting_time"] = exec_summary.get("total_waiting_time", "")
        row["total_response_time"] = exec_summary.get("total_response_time", "")
        row["average_turnaround_time"] = exec_summary.get("average_turnaround_time", "")
        row["average_waiting_time"] = exec_summary.get("average_waiting_time", "")
        row["average_response_time"] = exec_summary.get("average_response_time", "")
        row["job_completion_rate"] = exec_summary.get("job_completion_rate", "")
        row["average_fidelity"] = exec_summary.get("average_fidelity", "")
        row["succeeded_jobs"] = exec_summary.get("succeeded_jobs", "")
        row["failed_jobs"] = exec_summary.get("failed_jobs", "")
        row["blocked_jobs"] = exec_summary.get("blocked_jobs", "")

        # Nested fields as JSON strings
        machines = exec_summary.get("machines", {})
        row["machines_json"] = json.dumps(machines) if machines else ""

        batches = exec_summary.get("batches", [])
        row["batches_json"] = json.dumps(batches) if batches else ""

        # Metadata
        row["workload_fingerprint"] = result_data.get("workload_fingerprint", "")
        row["machine_config"] = result_data.get("machine_config", "")
        row["seed"] = result_data.get("seed", "0")
        row["queue_policy"] = result_data.get("queue_policy", "strict")
        row["dependency_versions"] = json.dumps(result_data.get("dependency_versions", {}))
    else:
        # Fill with empty values for failed runs
        for key in [
            "num_circuits", "name_circuits", "average_qubits", "name_machines",
            "name_schedule", "schedule_latency", "makespan", "total_turnaround_time",
            "total_waiting_time", "total_response_time", "average_turnaround_time",
            "average_waiting_time", "average_response_time", "job_completion_rate",
            "average_fidelity", "succeeded_jobs", "failed_jobs", "blocked_jobs",
            "machines_json", "batches_json", "workload_fingerprint", "machine_config",
            "seed", "queue_policy", "dependency_versions",
        ]:
            row[key] = ""

    # Append to CSV
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)
        f.flush()


def main() -> int:
    """Run batch simulation and collect results."""

    # Load algorithms from configuration
    if not ALGORITHMS:
        print("Error: No algorithms configured in batch_config.py", file=sys.stderr)
        return 1

    print(f"Configured algorithms: {', '.join(a['name'] for a in ALGORITHMS)}")

    # Create timestamped CSV
    timestamp = get_batch_timestamp()
    csv_filename = f"{timestamp}.csv"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / csv_filename

    # Check for collision (shouldn't happen with microseconds)
    if csv_path.exists():
        print(f"Error: CSV file already exists: {csv_path}", file=sys.stderr)
        return 1

    print(f"Creating batch results file: {csv_path}")
    create_csv_with_header(csv_path)

    run_index = 0

    try:
        for algo_config in ALGORITHMS:
            algo_name = algo_config["name"]
            script_path = PROJECT_ROOT / algo_config["script"]
            run_index += 1

            # Check if script exists
            if not script_path.exists():
                print(f"\n[{run_index}/{len(ALGORITHMS)}] Skipping {algo_name} - script not found: {script_path}")
                start_time = datetime.utcnow().isoformat()
                end_time = start_time
                error = f"Script not found: {script_path}"
                append_result_row(csv_path, run_index, algo_name, start_time, end_time, "FAILED", error, None)
                continue

            print(f"\n[{run_index}/{len(ALGORITHMS)}] Running {algo_name}...")

            # Create temporary file for JSON output
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                delete=False,
                prefix=f"{algo_name}_",
            ) as tmp:
                tmp_path = Path(tmp.name)

            try:
                start_time = datetime.utcnow().isoformat()
                status, error = run_algorithm(algo_name, script_path, tmp_path)
                end_time = datetime.utcnow().isoformat()

                print(f"  Status: {status}")
                if error:
                    print(f"  Error: {error}")

                # Load result if successful
                result_data = load_result_json(tmp_path) if status == "SUCCESS" else None

                # Append to CSV
                append_result_row(
                    csv_path,
                    run_index,
                    algo_name,
                    start_time,
                    end_time,
                    status,
                    error,
                    result_data,
                )

                print(f"  Result appended to CSV")

            finally:
                # Clean up temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

    except KeyboardInterrupt:
        print("\n\nBatch interrupted by user", file=sys.stderr)
        print(f"Partial results saved to: {csv_path}")
        return 130

    print(f"\nBatch complete. Results saved to: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
