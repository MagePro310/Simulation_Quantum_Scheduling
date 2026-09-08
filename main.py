import sys
# Add the project root to sys.path
sys.path.append('/home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/')

from source.component.dataclass.result_schedule import ResultOfSchedule

from source.flow.input.phase_input import ConcreteInputPhase
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase
from source.flow.execution.phase_execution import ConcreteExecutionPhase

def test_concrete_flow():

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()
    # Create input circuit, and quantum machine (notchanged))
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)
    
    # Schedule Phase (change algorithm here)
    from source.algorithm.heuristic.FFD import FFD
    schedule_result = ConcreteSchedulePhase(algorithm=FFD()).execute(input_job, machines_set, capture_result_schedule)
    execution = ConcreteExecutionPhase()
    results = execution.execute(machines_set, schedule_result, capture_result_schedule)
    return results

if __name__ == "__main__":
    test_concrete_flow()
