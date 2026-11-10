"""Every shot is charged the device's rep_delay, on both batch execution paths."""

import pytest

from source.flow.runner import run_pipeline
from source.models.machine import MachineCharacteristic
from source.models.simulation_config import ExecutionConfig, SimulationConfig, WorkloadConfig
from source.simulator import FakeBelemV2
from source.simulator.backends import default_rep_delay
from source.utils.provenance import workload_fingerprint
from source.utils.timing import shots_duration

BELEM_REP_DELAY = 250e-6  # default_rep_delay of the IBM fake backends, in seconds


def test_backend_default_rep_delay_is_read_in_seconds():
    assert default_rep_delay(FakeBelemV2()) == pytest.approx(BELEM_REP_DELAY)
    assert default_rep_delay(object()) == 0.0


def test_machine_takes_backend_default_unless_overridden():
    backend = FakeBelemV2()
    assert MachineCharacteristic("b", backend, 5).rep_delay == pytest.approx(BELEM_REP_DELAY)
    assert MachineCharacteristic("b", backend, 5, rep_delay=0.0).rep_delay == 0.0
    with pytest.raises(ValueError):
        MachineCharacteristic("b", backend, 5, rep_delay=-1.0)


def test_config_parses_and_validates_rep_delay():
    assert ExecutionConfig.from_dict({"rep_delay": 1e-4}).rep_delay == 1e-4
    assert ExecutionConfig.from_dict({"seed": 1}).rep_delay is None
    with pytest.raises(ValueError):
        ExecutionConfig(rep_delay=-1e-6)


def test_shots_duration_adds_rep_delay_to_every_shot():
    assert shots_duration(10e-6, 1000, 250e-6) == pytest.approx(0.26)


def _batches(jobs: dict, rep_delay: float | None) -> list[dict]:
    config = SimulationConfig(
        workload=WorkloadConfig(benchmark="ghz", jobs=jobs),
        machines=["FakeBelemV2", "FakeBogotaV2"],
        execution=ExecutionConfig(seed=3, rep_delay=rep_delay),
    )
    return run_pipeline("FFD", config=config)["execution_summary"]["batches"]


def _extra_time(jobs: dict) -> list[tuple[list[str], int, float]]:
    """Per batch: jobs, shots, and the time the default rep_delay added over rep_delay=0."""
    without = _batches(jobs, rep_delay=0.0)
    default = _batches(jobs, rep_delay=None)
    assert [b["job_ids"] for b in without] == [b["job_ids"] for b in default]
    return [
        (b["job_ids"], b["shots"], (b["end_time"] - b["start_time"]) - (a["end_time"] - a["start_time"]))
        for a, b in zip(without, default)
    ]


def test_standard_batch_charges_rep_delay_once_per_shot():
    for _, shots, extra in _extra_time({"a": {"qubits": 2, "shots": 512}, "b": {"qubits": 3, "shots": 512}}):
        assert extra == pytest.approx(shots * BELEM_REP_DELAY)


def test_joint_batch_charges_rep_delay_per_subexperiment_circuit():
    # The 7-qubit GHZ is cut at one CNOT: 6 subexperiments, each run as its own circuit
    extra_times = _extra_time({"s": {"qubits": 3, "shots": 512}, "l": {"qubits": 7, "shots": 512}})
    assert any("l_sub_A" in ids for ids, _, _ in extra_times)
    for _, shots, extra in extra_times:
        assert extra == pytest.approx(6 * shots * BELEM_REP_DELAY)


def test_fingerprint_distinguishes_rep_delay():
    backend = FakeBelemV2()
    default = {"b": MachineCharacteristic("b", backend, 5)}
    zero = {"b": MachineCharacteristic("b", backend, 5, rep_delay=0.0)}
    assert workload_fingerprint({}, "ghz", default) != workload_fingerprint({}, "ghz", zero)
