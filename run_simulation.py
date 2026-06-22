import sys
import os

# Add the project root to sys.path
sys.path.append('/home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/')

from component.dataclass.result_schedule import ResultOfSchedule
from flow.input.phase_input import ConcreteInputPhase
from flow.schedule.phase_schedule import ConcreteSchedulePhase
from flow.execution.phase_execution import ConcreteExecutionPhase
# from flow.result.result_phase import ConcreteResultPhase
# from component.visualize.gantt_chart import GanttChart


class TerminalColor:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


def print_info(message: str):
    print(f"{TerminalColor.BLUE}{message}{TerminalColor.RESET}")

def print_success(message: str):
    print(f"{TerminalColor.GREEN}{message}{TerminalColor.RESET}")

def print_highlight(message: str):
    print(f"{TerminalColor.CYAN}{message}{TerminalColor.RESET}")


def test_concrete_flow():

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()
    # Input Phase
    print_info("Starting Input Phase...")
    # Create circuit jobs
    input_job, machines = ConcreteInputPhase().create_input(capture_result_schedule)
    print_success("Input Phase Complete.")
    
    # Schedule Phase
    print_info("Starting Schedule Phase...")
    # Schedule jobs on machines
    execution_job_relations = ConcreteSchedulePhase().execute(input_job, machines, capture_result_schedule)
    print_success("Schedule Phase Complete.")

    print_info("Starting Execution Phase (transpile merged)...")
    scheduler_job_simulation =  ConcreteExecutionPhase().execute(
        machines,
        execution_job_relations=execution_job_relations,
    )

if __name__ == "__main__":
    test_concrete_flow()