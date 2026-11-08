"""Unit tests for centralized simulation configuration and pipeline integration."""

from pathlib import Path
import tempfile
import pytest

from source.algorithm.heuristic.ffd import FFD
from source.models.schedule_result import ResultOfSchedule
from source.models.simulation_config import (
    SimulationConfig,
    WorkloadConfig,
    SchedulingConfig,
    ExecutionConfig,
    BatchConfig,
)
from source.flow.input.input_phase import InputPhase
from source.flow.runner import run_pipeline


def test_simulation_config_defaults():
    """Verify standard default configuration values."""
    config = SimulationConfig()
    assert config.workload.benchmark == "ghz"
    assert len(config.workload.jobs) == 4
    assert config.machines == ["FakeBelemV2", "FakeBogotaV2"]
    assert config.scheduling.cutting_policy == "greedy"
    assert config.execution.queue_policy == "strict"
    assert config.execution.seed == 0
    assert config.execution.timeout == 600
    assert "FFD" in config.batch.algorithms
    assert config.batch.auto_compare is True


def test_simulation_config_yaml_io():
    """Verify saving to and loading from YAML."""
    custom_yaml = """
workload:
  benchmark: "qft"
  jobs:
    custom_j1: { qubits: 3, shots: 512, arrival_time: 1.0, priority: 2 }
    custom_j2: { qubits: 5, shots: 512, arrival_time: 2.0, priority: 1 }

machines:
  - "FakeManilaV2"

scheduling:
  cutting_policy: "half"

execution:
  seed: 99
  queue_policy: "backfill"
  timeout: 300

batch:
  algorithms:
    - "FFD"
    - "LPT"
  auto_compare: false
  output_dir: "custom_results"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(custom_yaml)
        temp_path = Path(f.name)

    try:
        config = SimulationConfig.from_yaml(temp_path)
        assert config.workload.benchmark == "qft"
        assert len(config.workload.jobs) == 2
        assert config.workload.jobs["custom_j1"]["qubits"] == 3
        assert config.machines == ["FakeManilaV2"]
        assert config.scheduling.cutting_policy == "half"
        assert config.execution.seed == 99
        assert config.execution.queue_policy == "backfill"
        assert config.execution.timeout == 300
        assert config.batch.algorithms == ["FFD", "LPT"]
        assert config.batch.auto_compare is False
        assert config.batch.output_dir == "custom_results"
    finally:
        temp_path.unlink(missing_ok=True)


def test_simulation_config_strict_validation():
    """Verify strict validation catches typos and invalid parameter configurations."""
    # Invalid cutting policy
    with pytest.raises(ValueError, match="Invalid cutting_policy"):
        SchedulingConfig(cutting_policy="random_policy")

    # Invalid queue policy
    with pytest.raises(ValueError, match="Invalid queue_policy"):
        ExecutionConfig(queue_policy="invalid_queue")

    # Negative seed
    with pytest.raises(ValueError, match="Random seed must be a non-negative integer"):
        ExecutionConfig(seed=-1)

    # Empty machines list
    with pytest.raises(ValueError, match="SimulationConfig machines list must not be empty"):
        SimulationConfig(machines=[])

    # Empty workload without generator
    with pytest.raises(ValueError, match="Workload configuration must specify either 'jobs'"):
        WorkloadConfig(jobs={}, generator=None)


def test_input_phase_custom_config():
    """Verify that InputPhase generates circuits and machines matching config."""
    config = SimulationConfig(
        workload=WorkloadConfig(
            benchmark="ghz",
            jobs={
                "t_job1": {"qubits": 2, "shots": 256, "arrival_time": 0, "priority": 1},
                "t_job2": {"qubits": 4, "shots": 256, "arrival_time": 0, "priority": 1},
            },
        ),
        machines=["FakeBelemV2"],
        execution=ExecutionConfig(seed=42),
    )

    capture = ResultOfSchedule()
    input_phase = InputPhase(config=config)
    jobs, machines = input_phase.create_input(capture)

    assert len(jobs) == 2
    assert "t_job1" in jobs
    assert "t_job2" in jobs
    assert jobs["t_job1"].circuit.num_qubits == 2
    assert jobs["t_job2"].circuit.num_qubits == 4
    assert len(machines) == 1
    assert "fake_belem" in machines
    assert capture.num_circuits == 2
    assert capture.name_circuits == "ghz"


def test_input_phase_generator_mode():
    """Verify workload generation using config generator settings."""
    config = SimulationConfig(
        workload=WorkloadConfig(
            benchmark="ghz",
            jobs={},
            generator={"num_jobs": 3, "min_qubits": 2, "max_qubits": 4, "shots": 512},
        ),
        machines=["FakeBogotaV2"],
        execution=ExecutionConfig(seed=123),
    )

    capture = ResultOfSchedule()
    input_phase = InputPhase(config=config)
    jobs, machines = input_phase.create_input(capture)

    assert len(jobs) == 3
    for job in jobs.values():
        assert 2 <= job.circuit.num_qubits <= 4
        assert job.shots == 512


def test_run_pipeline_single_source_of_truth():
    """Verify run_pipeline executes with parameters directly derived from config."""
    config = SimulationConfig(
        workload=WorkloadConfig(
            benchmark="ghz",
            jobs={
                "mini_j1": {"qubits": 2, "shots": 100},
                "mini_j2": {"qubits": 2, "shots": 100},
            },
        ),
        machines=["FakeBelemV2"],
        scheduling=SchedulingConfig(cutting_policy="greedy"),
        execution=ExecutionConfig(seed=77, queue_policy="strict"),
    )

    result = run_pipeline(
        algorithm=FFD(),
        config=config,
    )

    assert result["num_circuits"] == 2
    assert result["seed"] == 77
    assert result["queue_policy"] == "strict"
    assert result["exceed_cutting_policy"] == "greedy"
    assert "fake_belem" in result["name_machines"]
