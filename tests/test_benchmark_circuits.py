"""Benchmark circuits must reach the pipeline as standard 1- and 2-qubit gates."""

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit import QuantumCircuit
from qiskit.circuit.library.standard_gates import get_standard_gate_name_mapping
from qiskit_aer import AerSimulator

from source.flow.input.benchmark_circuits import expand_to_two_qubit_gates, load_benchmark_circuit
from source.flow.input.input_phase import InputPhase
from source.flow.schedule.cutting import SchedulingCutterHelper
from source.models.job import JobInfo
from source.models.schedule_result import ResultOfSchedule
from source.models.simulation_config import SimulationConfig, WorkloadConfig

STANDARD = set(get_standard_gate_name_mapping())
DIRECTIVES = {"measure", "barrier", "reset", "delay"}


def _assert_pipeline_ready(circuit: QuantumCircuit):
    for instruction in circuit.data:
        name = instruction.operation.name
        if name in DIRECTIVES:
            continue
        assert name in STANDARD, f"non-standard gate {name}"
        assert instruction.operation.num_qubits <= 2, f"{name} acts on more than two qubits"
    assert circuit.num_clbits > 0
    AerSimulator().run(circuit, shots=8, seed_simulator=1).result().get_counts()


@pytest.mark.parametrize("benchmark", ["ghz", "qft", "dj", "grover", "wstate", "qpeexact", "ae", "qaoa"])
def test_loaded_benchmarks_use_standard_two_qubit_gates_and_measure(benchmark):
    _assert_pipeline_ready(load_benchmark_circuit(benchmark, 4))


@pytest.mark.parametrize("benchmark", ["qft", "dj", "grover"])
def test_alg_level_composites_are_gone(benchmark):
    alg = get_benchmark(benchmark, level=BenchmarkLevel.ALG, circuit_size=4)
    loaded = load_benchmark_circuit(benchmark, 4)
    assert alg.depth() < loaded.depth()  # ALG hides the algorithm inside one composite gate


def test_expand_decomposes_multi_qubit_standard_gates():
    circuit = QuantumCircuit(3, 3)
    circuit.ccx(0, 1, 2)
    circuit.measure(range(3), range(3))
    expanded = expand_to_two_qubit_gates(circuit)
    assert "ccx" not in expanded.count_ops()
    _assert_pipeline_ready(expanded)


def test_loaded_qft_can_be_cut():
    qft = load_benchmark_circuit("qft", 4)
    job = JobInfo(job_name="q", circuit=qft, num_qubits=qft.num_qubits, shots=1024)
    assert SchedulingCutterHelper.estimate_overhead(job, [3, 1]) > 1


def test_input_phase_builds_jobs_from_loaded_circuits():
    config = SimulationConfig(workload=WorkloadConfig(benchmark="qft", jobs={"q": {"qubits": 4}}))
    jobs, _ = InputPhase(config).create_input(ResultOfSchedule())
    assert jobs["q"].num_qubits == jobs["q"].circuit.num_qubits == 4
    _assert_pipeline_ready(jobs["q"].circuit)


@pytest.mark.parametrize("benchmark", ["qft", "qpeexact"])
def test_loaded_circuits_carry_no_layout(benchmark):
    assert get_benchmark(benchmark, level=BenchmarkLevel.INDEP, circuit_size=4).layout is not None
    assert load_benchmark_circuit(benchmark, 4).layout is None
