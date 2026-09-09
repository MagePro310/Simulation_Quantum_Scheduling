import sys
# Add the project root to sys.path
sys.path.append('/home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/')

from source.component.dataclass.result_schedule import ResultOfSchedule

from source.flow.input.phase_input import ConcreteInputPhase
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase
from source.flow.execution.orchestrator import ConcreteExecutionPhase

def test_concrete_flow():

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()
    # Create input circuit, and quantum machine (notchanged))
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)
    
    # Schedule Phase (change algorithm here)
    from source.algorithm.heuristic.LPT import LPT
    schedule_result = ConcreteSchedulePhase(algorithm=FFD()).execute(input_job, machines_set, capture_result_schedule)
    results = ConcreteExecutionPhase().execute(machines_set, schedule_result, capture_result_schedule=capture_result_schedule)

    # Debug: Print results
    print(f"\nExecution Results:")
    for job_name, result in results.items():
        print(f"  {job_name}: {result.status} - completed {result.completed_shots}/{result.requested_shots} shots")
        
    print(capture_result_schedule)

    return results

if __name__ == "__main__":
    test_concrete_flow()
