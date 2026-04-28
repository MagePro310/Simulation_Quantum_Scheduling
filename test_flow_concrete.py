import sys
import os

# Add the project root to sys.path
sys.path.append('/home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/')

from component.dataclass.result_schedule import ResultOfSchedule
from flow.input.phase_input import ConcreteInputPhase
from flow.schedule.phase_schedule import ConcreteSchedulePhase
from flow.transpile.phase_transpile import ConcreteTranspilePhase
from flow.execution.phase_execution import ConcreteExecutionPhase
# from flow.result.result_phase import ConcreteResultPhase
from component.visualize.gantt_chart import GanttChart
from component.relation.job_relation import build_job_relations_from_schedule


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
    input_phase = ConcreteInputPhase()
    # Create circuit jobs
    input_job, machines = input_phase.create_input(capture_result_schedule)
    print_success("Input Phase Complete.")
    
    # Schedule Phase
    print_info("Starting Schedule Phase...")
    schedule_phase = ConcreteSchedulePhase()
    # Schedule jobs on machines
    scheduler_job_estimate = schedule_phase.execute(input_job, machines, capture_result_schedule)
    print_success("Schedule Phase Complete.")

    # Build prev/next relation on each machine from scheduling output.
    execution_job_relations = build_job_relations_from_schedule(
        scheduler_job_estimate=scheduler_job_estimate,
    )

    print_highlight("Built machine neighbor relations from schedule output.")
    for job_name, relation in execution_job_relations.items():
        print(
            f"{job_name}: machine={relation.machine_name}, "
            f"prev={relation.prev_job_on_machine}, "
            f"next={relation.next_job_on_machine}"
        )

    # Visualize schedule as a Gantt chart
    chart = GanttChart(title="Quantum Schedule", x_axis_label="Time", y_axis_label="Machines")
    chart.display(scheduler_job_estimate, machines)
    print_highlight("Gantt chart generated.")

    # Transpile Phase    
    print_info("Starting Transpile Phase...")
    transpile_phase = ConcreteTranspilePhase()
    transpiled_job = transpile_phase.execute(
        scheduler_job_estimate,
        machines,
        capture_result_schedule,
        execution_job_relations=execution_job_relations,
    )
    print_success("Transpile Phase Complete.")
    print(transpiled_job)
    
    # Execution Phase
    print_info("Starting Execution Phase...")
    execution_phase = ConcreteExecutionPhase()
    scheduler_job_simulation = execution_phase.execute(
        scheduler_job_estimate,
        machines,
        transpiled_job,
        execution_job_relations,
    )
    print_success("Execution Phase Complete.")
    print(scheduler_job_simulation)
    
    # Visualize simulated execution as a Gantt chart
    chart = GanttChart(title="Quantum Execution (Transpiled)", x_axis_label="Time", y_axis_label="Machines")
    chart.display(scheduler_job_simulation, machines)
    print_highlight("Execution Gantt chart generated.")
    
    # print("Starting Result Phase...")
    # result_phase = ConcreteResultPhase()
    # final_result = result_phase.execute(scheduler_job, origin_job_info, data, utilization_permachine, result_Schedule)
    # print("Result Phase Complete.")
    

if __name__ == "__main__":
    test_concrete_flow()