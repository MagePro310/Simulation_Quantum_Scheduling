"""The fidelity reference is the exact ideal distribution, keyed like Aer's counts on every path."""

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from source.flow.execution import SilentTimelineReporter
from source.flow.execution.batch_executor import BatchExecutor
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.schedule.cutting import SchedulingCutterHelper
from source.flow.schedule.shots import ShotDistributionHelper
from source.models.execution import BatchCounts, PreparedBatch
from source.models.job import JobInfo
from source.models.machine import MachineCharacteristic
from source.simulator import FakeBelemV2, FakeBogotaV2
from source.utils.ideal_distribution import UnsupportedIdealCircuit, ideal_counts, ideal_probabilities
from source.utils.timing import estimate_job_duration, num_circuit_runs


def _asymmetric(num_qubits: int = 3) -> QuantumCircuit:
    """Deterministic output '0..01' (qubit 0 flipped): wrong bit order gives fidelity 0."""
    circuit = QuantumCircuit(num_qubits, num_qubits)
    circuit.x(0)
    circuit.measure(range(num_qubits), range(num_qubits))
    return circuit


def test_ghz_is_exact():
    ghz = get_benchmark("ghz", level=BenchmarkLevel.INDEP, circuit_size=3)
    assert ideal_probabilities(ghz) == pytest.approx({"000": 0.5, "111": 0.5})


def test_keys_match_aer_counts():
    circuit = QuantumCircuit(3, 3)
    circuit.x(0)
    circuit.h(2)
    circuit.measure(range(3), range(3))
    sampled = AerSimulator().run(circuit, shots=2000, seed_simulator=1).result().get_counts()
    assert set(ideal_probabilities(circuit)) == set(sampled) == {"001", "101"}


def test_measurement_into_permuted_clbits():
    circuit = QuantumCircuit(3, 3)
    circuit.x(0)
    circuit.measure([0, 1, 2], [2, 1, 0])
    assert ideal_probabilities(circuit) == pytest.approx({"100": 1.0})


def test_unmeasured_circuit_is_measured_on_every_qubit():
    circuit = QuantumCircuit(2)
    circuit.x(1)
    assert ideal_probabilities(circuit) == pytest.approx({"10": 1.0})


def test_expected_counts_scale_with_shots():
    assert ideal_counts(_asymmetric(), 512, seed=1) == pytest.approx({"001": 512.0})


def test_mid_circuit_measurement_falls_back_to_sampling():
    circuit = QuantumCircuit(1, 2)
    circuit.h(0)
    circuit.measure(0, 0)
    circuit.h(0)
    circuit.measure(0, 1)
    with pytest.raises(UnsupportedIdealCircuit):
        ideal_probabilities(circuit)
    counts = ideal_counts(circuit, 100, seed=3)
    assert sum(counts.values()) == 100
    assert counts == ideal_counts(circuit, 100, seed=3)


def test_split_counts_uses_qiskit_bit_order_per_job():
    batch = PreparedBatch(
        job_ids=("a", "b"),
        merged_circuit=QuantumCircuit(5),
        transpiled_circuit=QuantumCircuit(5),
        classical_bits={"a": (0, 1), "b": (2, 3, 4)},
        logical_qubits=5,
        duration_per_shot=0.0,
    )
    # clbits 4..0 = 1 0 1 1 0: job a has c1=1, c0=0; job b has c4=1, c3=0, c2=1
    split = BatchExecutor.split_counts(batch, BatchCounts({}, {"10110": 7}))
    assert split["a"].distribution_with_noise == {"10": 7}
    assert split["b"].distribution_with_noise == {"101": 7}


def test_job_split_over_both_paths_merges_consistent_counts():
    """One shard runs alone (standard path), the other beside a cut subcircuit (joint
    path). Both must key the same outcome the same way, or the merged counts split it."""
    job = JobInfo(job_name="j", circuit=_asymmetric(), num_qubits=3, shots=1024, arrival_time=0)
    big = JobInfo(
        job_name="big",
        circuit=get_benchmark("ghz", level=BenchmarkLevel.INDEP, circuit_size=7),
        num_qubits=7, shots=1024, arrival_time=0,
    )
    scheduler_job = {
        **ShotDistributionHelper.split_shots(job, 2),
        **SchedulingCutterHelper.cut_job(big, cluster_sizes=[5, 2]),
    }
    placement = {"j_shot0": "bogota", "big_sub_B": "belem", "j_shot1": "belem", "big_sub_A": "bogota"}
    for order, (name, machine) in enumerate(placement.items()):
        scheduler_job[name].assigned_machine = machine
        scheduler_job[name].dispatch_order = order
    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    phase = ExecutionPhase(reporter=SilentTimelineReporter())
    results = phase.execute(machines, scheduler_job, seed=0)

    batches = {name: b for b in phase.execution_summary.batches for name in b.job_ids}
    assert batches["j_shot0"].job_ids == ("j_shot0",)            # standard path
    assert "big_sub_B" in batches["j_shot1"].job_ids             # joint path
    merged = results["j"]
    assert merged.status == "SUCCEEDED"
    assert merged.distribution_no_noise == pytest.approx({"001": 1024.0})
    assert max(merged.distribution_with_noise, key=merged.distribution_with_noise.get) == "001"
    assert merged.fidelity > 0.9


def test_duration_estimate_counts_every_subexperiment():
    big = JobInfo(
        job_name="big",
        circuit=get_benchmark("ghz", level=BenchmarkLevel.INDEP, circuit_size=7),
        num_qubits=7, shots=1024, arrival_time=0,
    )
    fragments = SchedulingCutterHelper.cut_job(big, cluster_sizes=[5, 2])
    for s_job in fragments.values():
        info = s_job.job_information
        assert num_circuit_runs(s_job) == len(info.subexperiments) == 6  # one cut CNOT
        assert estimate_job_duration(s_job) == info.circuit.depth() * info.shots * 6
    assert num_circuit_runs(big) == 1


# ---------------------------------------------------------------------------
# Cut jobs are scored on the parent circuit's own classical bits
# ---------------------------------------------------------------------------

from source.algorithm.heuristic.ffd import FFD  # noqa: E402
from source.flow.input.benchmark_circuits import load_benchmark_circuit  # noqa: E402
from source.flow.schedule.schedule_phase import SchedulePhase  # noqa: E402
from source.models.schedule_result import ResultOfSchedule  # noqa: E402
from source.simulator import FakeJakartaV2  # noqa: E402
from source.utils.ideal_distribution import measurement_map, project_to_clbits  # noqa: E402


def test_measurement_map_of_measure_all_is_identity():
    circuit = QuantumCircuit(3)
    circuit.measure_all()
    assert measurement_map(circuit) == ({0: 0, 1: 1, 2: 2}, 3)
    assert measurement_map(QuantumCircuit(2)) == ({0: 0, 1: 1}, 2)


def test_project_to_clbits_reorders_and_marginalises():
    # 3 qubits; clbit 0 <- qubit 2, clbit 1 <- qubit 0; qubit 1 unmeasured
    dist = {"001": 0.25, "011": 0.25, "100": 0.5}  # keys: qubit2 qubit1 qubit0
    projected = project_to_clbits(dist, 3, {0: 2, 1: 0}, 2)
    # "001": q0=1 -> c1=1, q2=0 -> c0=0 -> "10"; "011" same; "100": q2=1 -> "01"
    assert projected == pytest.approx({"10": 0.5, "01": 0.5})


def _run_alone(benchmark: str, qubits: int, backend, capacity: int):
    circuit = load_benchmark_circuit(benchmark, qubits)
    job = JobInfo(job_name="p", circuit=circuit, num_qubits=circuit.num_qubits, shots=1024, arrival_time=0)
    machines = {backend.name: MachineCharacteristic(name=backend.name, quantum_machine=backend, capacity=capacity)}
    scheduled = SchedulePhase(algorithm=FFD()).execute({"p": job}, machines, ResultOfSchedule())
    results = ExecutionPhase(reporter=SilentTimelineReporter()).execute(machines, scheduled, seed=3)
    return results["p"]


# Sizes whose cheapest cut is a single CNOT, within the default budget
@pytest.mark.parametrize(("benchmark", "qubits"), [("dj", 6), ("qpeexact", 4)])
def test_cut_and_uncut_runs_are_scored_on_the_same_bits(benchmark, qubits):
    cut = _run_alone(benchmark, qubits, FakeBelemV2(), capacity=qubits - 1)  # must cut [n-1, 1]
    whole = _run_alone(benchmark, qubits, FakeJakartaV2(), capacity=7)        # runs whole
    assert cut.status == whole.status == "SUCCEEDED"
    assert cut.reconstructed_distribution is not None and whole.reconstructed_distribution is None

    circuit = load_benchmark_circuit(benchmark, qubits)
    width = circuit.num_clbits
    assert width < qubits  # these benchmarks leave one qubit unmeasured
    assert {len(k) for k in cut.distribution_with_noise} == {width}
    assert cut.distribution_no_noise == pytest.approx(ideal_counts(circuit, 1024, seed=0))
    assert cut.distribution_no_noise == pytest.approx(whole.distribution_no_noise)
    top = max(cut.distribution_no_noise, key=cut.distribution_no_noise.get)
    assert max(cut.distribution_with_noise, key=cut.distribution_with_noise.get) == top
