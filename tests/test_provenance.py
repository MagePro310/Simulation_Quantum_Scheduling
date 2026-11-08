"""Tests that results record what produced them and refuse unsound comparisons."""

import csv

import pytest

from run_batch import append_result_row, create_csv_with_header
from source.analysis.report_generator import check_compatibility, run_comparison
from source.flow.runner import run_pipeline
from source.models.job import JobInfo
from source.models.simulation_config import SimulationConfig, WorkloadConfig
from source.utils.provenance import TRACKED_PACKAGES, workload_fingerprint


def _jobs(*qubit_counts: int) -> dict[str, JobInfo]:
    return {
        f"job{i}": JobInfo(job_name=f"job{i}", num_qubits=q, shots=1024, arrival_time=0.0, priority=1)
        for i, q in enumerate(qubit_counts)
    }


def test_fingerprint_distinguishes_workloads_with_same_size_and_benchmark():
    machines = ["m0", "m1"]
    assert workload_fingerprint(_jobs(2, 3), "ghz", machines) == workload_fingerprint(_jobs(2, 3), "ghz", machines)
    assert workload_fingerprint(_jobs(2, 3), "ghz", machines) != workload_fingerprint(_jobs(2, 4), "ghz", machines)
    assert workload_fingerprint(_jobs(2, 3), "ghz", machines) != workload_fingerprint(_jobs(2, 3), "qft", machines)
    assert workload_fingerprint(_jobs(2, 3), "ghz", machines) != workload_fingerprint(_jobs(2, 3), "ghz", machines[::-1])


def _row(**overrides) -> dict[str, str]:
    row = {
        "process_status": "SUCCESS",
        "workload_fingerprint": "abc",
        "machine_config": "m",
        "seed": "0",
        "queue_policy": "strict",
        "cutting_policy": "greedy",
    }
    return {**row, **overrides}


def test_check_compatibility_rejects_rows_from_different_setups():
    assert check_compatibility([_row(), _row()]) == (True, [])

    is_compatible, warnings = check_compatibility([_row(), _row(seed="1")])
    assert is_compatible is False
    assert warnings

    assert check_compatibility([_row(), _row(workload_fingerprint="xyz")])[0] is False


def test_failed_rows_do_not_make_results_incompatible():
    assert check_compatibility([_row(), _row(process_status="FAILED", workload_fingerprint="")])[0] is True


@pytest.fixture
def batch_result() -> dict:
    config = SimulationConfig(
        workload=WorkloadConfig(benchmark="ghz", jobs={"j1": {"qubits": 2, "shots": 64}}),
        machines=["FakeBelemV2"],
    )
    return run_pipeline("FFD", config=config)


def test_result_records_provenance(batch_result):
    assert set(TRACKED_PACKAGES) == set(batch_result["dependency_versions"])
    assert batch_result["git_commit"]
    assert batch_result["config"]["workload"]["jobs"] == {"j1": {"qubits": 2, "shots": 64}}
    assert len(batch_result["workload_fingerprint"]) == 16
    assert "numCircuits" not in batch_result


def test_batch_csv_carries_provenance_and_report_enforces_compatibility(tmp_path, batch_result):
    csv_path = tmp_path / "batch.csv"
    create_csv_with_header(csv_path)
    other_workload = {**batch_result, "workload_fingerprint": "different"}
    append_result_row(csv_path, 1, "FFD", "t0", "t1", "SUCCESS", None, batch_result)
    append_result_row(csv_path, 2, "LPT", "t0", "t1", "SUCCESS", None, other_workload)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["git_commit"] == batch_result["git_commit"]
    assert rows[0]["config_json"]
    assert rows[0]["num_circuits"] == "1"

    with pytest.raises(ValueError, match="can't be compared"):
        run_comparison(csv_path)

    assert (run_comparison(csv_path, allow_incompatible=True) / "comparison_report.md").exists()
