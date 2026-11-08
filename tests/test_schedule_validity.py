"""Behaviour tests for LPT and QGroup schedules."""

import pytest
from qiskit import QuantumCircuit

from source.algorithm.heuristic.lpt import LPT
from source.algorithm.heuristic.qgroup import QGroup, qgroup
from source.flow.runner import run_pipeline
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.models.simulation_config import SimulationConfig, WorkloadConfig


def _circuit(qubits: int, depth: int) -> QuantumCircuit:
    circuit = QuantumCircuit(qubits)
    for _ in range(depth):
        circuit.h(0)
    return circuit


def _jobs(*specs: tuple[str, int, int]) -> dict[str, SchedulerJobInfo]:
    return {
        name: SchedulerJobInfo(
            job_information=JobInfo(
                job_name=name,
                circuit=_circuit(qubits, depth),
                num_qubits=qubits,
                shots=1024,
                arrival_time=0.0,
            )
        )
        for name, qubits, depth in specs
    }


def _machines(*capacities: int) -> dict[str, MachineCharacteristic]:
    return {
        f"m{i}": MachineCharacteristic(name=f"m{i}", quantum_machine=None, capacity=capacity)
        for i, capacity in enumerate(capacities)
    }


WORKLOAD = (("a", 5, 10), ("b", 3, 8), ("c", 2, 5), ("d", 2, 3), ("e", 4, 1))


@pytest.mark.parametrize("algorithm", [LPT, QGroup])
def test_every_job_is_assigned_to_a_machine_it_fits(algorithm):
    machines = _machines(5, 5)
    result = algorithm().execute(_jobs(*WORKLOAD), machines)

    assert set(result) == {spec[0] for spec in WORKLOAD}
    for job in result.values():
        assert job.assigned_machine in machines
        assert job.dispatch_order is not None
        assert job.job_information.num_qubits <= machines[job.assigned_machine].capacity


def test_lpt_assigns_longest_jobs_first_to_least_loaded_machine():
    result = LPT().execute(_jobs(("a", 2, 10), ("b", 2, 8), ("c", 2, 5), ("d", 2, 3)), _machines(5, 5))

    assert result["a"].assigned_machine == "m0"
    assert result["b"].assigned_machine == "m1"
    assert result["c"].assigned_machine == "m1"  # m1 finishes at 8, m0 at 10
    assert result["d"].assigned_machine == "m0"  # m0 finishes at 10, m1 at 13


def test_lpt_chains_jobs_sequentially_on_each_machine():
    result = LPT().execute(_jobs(*WORKLOAD), _machines(5, 5))

    for machine_name in ("m0", "m1"):
        queue = sorted(
            (job for job in result.values() if job.assigned_machine == machine_name),
            key=lambda job: job.dispatch_order,
        )
        assert [job.dispatch_order for job in queue] == list(range(len(queue)))
        for previous, current in zip(queue, queue[1:]):
            assert any(dep is previous.job_information for dep in current.depends_on)


def test_lpt_keeps_oversized_jobs_off_smaller_machines():
    result = LPT().execute(_jobs(("big", 5, 1), ("long", 2, 50)), _machines(2, 5))

    assert result["big"].assigned_machine == "m1"


def test_qgroup_plan_respects_capacity_in_every_time_slot():
    """A QGroup group can exceed capacity overall; each of its time slots must not."""
    algorithm = QGroup()
    machines = _machines(5, 5)
    jobs = _jobs(*WORKLOAD)
    plan = qgroup(
        machines=algorithm._convert_machines(machines),
        queue=algorithm._convert_jobs(jobs),
        runtime=algorithm._runtime_callback,
        fidelity=algorithm._fidelity_callback,
        p=algorithm.params,
        compress=True,
    )

    for machine_name, assignments in plan.assignments.items():
        for assignment in assignments:
            schedule = assignment.schedule
            qubits = [job.qubits for job in schedule.jobs]
            used_per_slot = (qubits @ schedule.X).tolist()
            assert max(used_per_slot) <= machines[machine_name].capacity

def test_qgroup_jobs_only_depend_on_earlier_groups_on_their_machine():
    result = QGroup().execute(_jobs(*WORKLOAD), _machines(5, 5))
    jobs_by_info = {id(job.job_information): job for job in result.values()}

    for job in result.values():
        for dependency in job.depends_on or []:
            earlier = jobs_by_info[id(dependency)]
            assert earlier.assigned_machine == job.assigned_machine
            assert earlier.dispatch_order < job.dispatch_order


@pytest.mark.parametrize("algorithm", ["LPT", "QGroup"])
def test_schedule_runs_end_to_end_with_a_cut_job(algorithm):
    config = SimulationConfig(
        workload=WorkloadConfig(
            benchmark="ghz",
            jobs={
                "small": {"qubits": 2, "shots": 128},
                "medium": {"qubits": 3, "shots": 128},
                "large": {"qubits": 7, "shots": 128},
            },
        ),
        machines=["FakeBelemV2", "FakeBogotaV2"],
    )

    summary = run_pipeline(algorithm, config=config)["execution_summary"]

    assert summary["succeeded_jobs"] == 3
    assert summary["failed_jobs"] == 0
    assert summary["blocked_jobs"] == 0
    for batch in summary["batches"]:
        assert batch["logical_qubits"] <= 5
