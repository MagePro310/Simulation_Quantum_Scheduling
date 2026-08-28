"""Unit tests for the First-Fit-Decreasing scheduler (algorithm/heuristic/FFD.py).

All expected values in this file were verified against the real
implementation before being written down (not hand-derived only).
"""
from component.dataclass.job_info import JobInfo, SchedulerJobInfo

from algorithm.heuristic.FFD import FFD
from tests.helpers import make_machine, make_scheduler_job


# ---------------------------------------------------------------------------
# FFD.execute
# ---------------------------------------------------------------------------


def test_execute_returns_same_dict_unchanged_for_empty_scheduler_job():
    scheduler_job = {}
    result = FFD.execute(scheduler_job, {"m1": make_machine(5)})
    assert result is scheduler_job
    assert result == {}


def test_execute_assigns_single_job_to_only_machine():
    job = make_scheduler_job("job1", num_qubits=2, depth_value=3, arrival_time=0.0)
    FFD.execute({"job1": job}, {"m1": make_machine(5)})

    assert job.assigned_machine == "m1"
    assert job.scheduled_start_time == 0.0
    assert job.scheduled_end_time == 3.0  # max(1, depth=3)


def test_execute_processes_jobs_in_descending_qubit_order():
    # "big" (4 qubits) must be processed before "small" (2 qubits) despite
    # being inserted second: on a capacity-5 machine, 4+2 > 5 so they cannot
    # run concurrently. If "big" is scheduled first it claims [0, 3); "small"
    # is then squeezed in afterwards, starting at 3.0 - the observable proof
    # that jobs are sorted by qubit count descending, not insertion order.
    small = make_scheduler_job("small", num_qubits=2, depth_value=2, arrival_time=0.0)
    big = make_scheduler_job("big", num_qubits=4, depth_value=3, arrival_time=0.0)
    FFD.execute({"small": small, "big": big}, {"m1": make_machine(5)})

    assert big.scheduled_start_time == 0.0
    assert big.scheduled_end_time == 3.0
    assert small.scheduled_start_time == 3.0
    assert small.scheduled_end_time == 5.0


def test_execute_picks_first_fitting_machine_in_dict_insertion_order():
    job = make_scheduler_job("jobA", num_qubits=2, depth_value=1, arrival_time=0.0)
    # Both machines are equally capable; FFD is first-fit, not best-fit, so
    # the job must land on whichever machine appears first in `machines`.
    FFD.execute({"jobA": job}, {"m1": make_machine(5), "m2": make_machine(5)})

    assert job.assigned_machine == "m1"


def test_execute_prefers_idle_machine_over_busy_first_machine():
    # m1 (first in dict order) is kept busy until t=100 by a large blocking job.
    # m2 is idle the whole time. A later 2-qubit job should land on m2 at its
    # own arrival time, not queue behind m1's backlog.
    blocker = make_scheduler_job("blocker", num_qubits=5, depth_value=100, arrival_time=0.0)
    job = make_scheduler_job("job", num_qubits=2, depth_value=1, arrival_time=1.0)

    FFD.execute(
        {"blocker": blocker, "job": job},
        {"m1": make_machine(5), "m2": make_machine(5)},
    )

    assert blocker.assigned_machine == "m1"
    assert job.assigned_machine == "m2"
    assert job.scheduled_start_time == 1.0
    assert job.scheduled_end_time == 2.0


def test_execute_co_schedules_two_jobs_on_same_machine_when_capacity_allows():
    j1 = make_scheduler_job("j1", num_qubits=2, depth_value=2, arrival_time=0.0)
    j2 = make_scheduler_job("j2", num_qubits=2, depth_value=2, arrival_time=0.0)
    FFD.execute({"j1": j1, "j2": j2}, {"m1": make_machine(5)})

    assert j1.assigned_machine == "m1"
    assert j2.assigned_machine == "m1"
    assert j1.scheduled_start_time == 0.0
    assert j2.scheduled_start_time == 0.0


def test_execute_delays_second_job_when_concurrent_capacity_exceeded():
    # Two 3-qubit jobs cannot both run at once on a 5-qubit machine (3+3 > 5).
    j3 = make_scheduler_job("j3", num_qubits=3, depth_value=2, arrival_time=0.0)
    j4 = make_scheduler_job("j4", num_qubits=3, depth_value=2, arrival_time=0.0)
    FFD.execute({"j3": j3, "j4": j4}, {"m1": make_machine(5)})

    assert j3.scheduled_start_time == 0.0
    assert j3.scheduled_end_time == 2.0
    # j4 (processed second - equal qubit count preserves insertion order)
    # waits until j3's slot frees up.
    assert j4.scheduled_start_time == 2.0
    assert j4.scheduled_end_time == 4.0


def test_execute_raises_value_error_when_no_machine_has_enough_qubits():
    import pytest

    job = make_scheduler_job("jbig", num_qubits=10, depth_value=1, arrival_time=0.0)
    with pytest.raises(ValueError, match="No available machine can host job 'jbig'"):
        FFD.execute({"jbig": job}, {"m1": make_machine(5)})


def test_execute_uses_nonzero_arrival_time_as_earliest_start():
    job = make_scheduler_job("jarr", num_qubits=2, depth_value=2, arrival_time=5.0)
    FFD.execute({"jarr": job}, {"m1": make_machine(5)})

    assert job.scheduled_start_time == 5.0
    assert job.scheduled_end_time == 7.0


def test_execute_defaults_missing_shots_without_error():
    job = make_scheduler_job("jshots", num_qubits=2, depth_value=2, arrival_time=0.0, shots=None)
    FFD.execute({"jshots": job}, {"m1": make_machine(5)})

    assert job.assigned_machine == "m1"
    assert job.scheduled_end_time == 2.0


def test_execute_floors_execution_time_at_one_for_zero_depth_circuit():
    job = make_scheduler_job("jzero", num_qubits=2, depth_value=0, arrival_time=0.0)
    FFD.execute({"jzero": job}, {"m1": make_machine(5)})

    assert job.scheduled_end_time - job.scheduled_start_time == 1.0


def test_execute_mutates_the_same_scheduler_job_info_objects_in_place():
    job = make_scheduler_job("jmut", num_qubits=2, depth_value=1, arrival_time=0.0)
    scheduler_job = {"jmut": job}
    result = FFD.execute(scheduler_job, {"m1": make_machine(5)})

    assert result is scheduler_job
    assert result["jmut"] is job


# ---------------------------------------------------------------------------
# FFD._job_qubits / _machine_qubits / _job_arrival_time
# ---------------------------------------------------------------------------


def test_job_qubits_returns_zero_when_job_information_is_none():
    assert FFD._job_qubits(SchedulerJobInfo(job_information=None)) == 0


def test_job_qubits_returns_zero_when_circuit_is_none():
    job_info = SchedulerJobInfo(job_information=JobInfo(job_name="x", circuit=None))
    assert FFD._job_qubits(job_info) == 0


def test_job_qubits_reads_circuit_num_qubits():
    assert FFD._job_qubits(make_scheduler_job("x", num_qubits=3)) == 3


def test_machine_qubits_reads_num_qubits_attribute_and_defaults_to_zero():
    assert FFD._machine_qubits(object()) == 0
    assert FFD._machine_qubits(make_machine(7)) == 7


def test_job_arrival_time_defaults_to_zero_when_job_information_none():
    assert FFD._job_arrival_time(SchedulerJobInfo(job_information=None)) == 0.0


def test_job_arrival_time_defaults_to_zero_when_arrival_time_none():
    job_info = SchedulerJobInfo(job_information=JobInfo(job_name="x", arrival_time=None))
    assert FFD._job_arrival_time(job_info) == 0.0


def test_job_arrival_time_returns_float_of_arrival_time():
    job = make_scheduler_job("x", num_qubits=1, arrival_time=4.5)
    assert FFD._job_arrival_time(job) == 4.5


# ---------------------------------------------------------------------------
# FFD._capacity_available
# ---------------------------------------------------------------------------


def test_capacity_available_true_when_under_capacity():
    machine_state = {"machine": make_machine(5), "allocations": [{"start": 0.0, "end": 2.0, "qubits": 3}]}
    assert FFD._capacity_available(machine_state, 1.0, 3.0, 2) is True  # 3 + 2 = 5 <= 5


def test_capacity_available_false_when_overlap_exceeds_capacity():
    machine_state = {"machine": make_machine(5), "allocations": [{"start": 0.0, "end": 2.0, "qubits": 3}]}
    assert FFD._capacity_available(machine_state, 1.0, 3.0, 3) is False  # 3 + 3 = 6 > 5


def test_capacity_available_ignores_non_overlapping_allocations():
    machine_state = {"machine": make_machine(5), "allocations": []}
    assert FFD._capacity_available(machine_state, 0.0, 1.0, 5) is True


def test_capacity_available_treats_touching_intervals_as_non_overlapping():
    # An allocation ending exactly when the new interval starts (or starting
    # exactly when it ends) does not count as concurrent - strict `<`/`>`.
    machine_state = {"machine": make_machine(5), "allocations": [{"start": 0.0, "end": 2.0, "qubits": 5}]}
    assert FFD._capacity_available(machine_state, 2.0, 4.0, 5) is True
    assert FFD._capacity_available(machine_state, -2.0, 0.0, 5) is True


# ---------------------------------------------------------------------------
# FFD._find_first_fitting_machine
# ---------------------------------------------------------------------------


def test_find_first_fitting_machine_skips_undersized_machines():
    small = {"name": "small", "machine": make_machine(1), "available_time": 0.0}
    big = {"name": "big", "machine": make_machine(5), "available_time": 0.0}
    job = make_scheduler_job("job", num_qubits=3, depth_value=1, arrival_time=0.0)

    found = FFD._find_first_fitting_machine(job, [small, big])

    assert found is big


def test_find_first_fitting_machine_returns_none_when_no_machine_qualifies():
    small = {"name": "small", "machine": make_machine(1), "available_time": 0.0}
    job = make_scheduler_job("job", num_qubits=3, depth_value=1, arrival_time=0.0)

    assert FFD._find_first_fitting_machine(job, [small]) is None


# ---------------------------------------------------------------------------
# FFD._earliest_start_for_machine
# ---------------------------------------------------------------------------


def test_earliest_start_for_machine_returns_arrival_when_free():
    machine_state = {"machine": make_machine(5), "allocations": []}
    job = make_scheduler_job("job2", num_qubits=2, depth_value=2, arrival_time=3.0)

    assert FFD._earliest_start_for_machine(machine_state, 3.0, job, 2) == 3.0


def test_earliest_start_for_machine_returns_next_free_slot_when_arrival_slot_full():
    machine_state = {
        "machine": make_machine(5),
        "allocations": [{"start": 0.0, "end": 4.0, "qubits": 5}],
    }
    job = make_scheduler_job("job3", num_qubits=2, depth_value=2, arrival_time=0.0)

    assert FFD._earliest_start_for_machine(machine_state, 0.0, job, 2) == 4.0
