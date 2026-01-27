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


def test_concrete_flow():

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()
    
    # Input Phase
    print("Starting Input Phase...")
    input_phase = ConcreteInputPhase()
    # Create circuit jobs
    input_job = input_phase.create_circuit_jobs(capture_result_schedule)
    # Setup quantum machines
    machines = input_phase.setup_quantum_machines(capture_result_schedule)
    print("Input Phase Complete.")
    
    # Schedule Phase
    print("Starting Schedule Phase...")
    schedule_phase = ConcreteSchedulePhase()
    # Schedule jobs on machines
    scheduler_job_estimate = schedule_phase.execute(input_job, machines, capture_result_schedule)
    print("Schedule Phase Complete.")

    # # Visualize schedule as a Gantt chart
    # chart = GanttChart(title="Quantum Schedule", x_axis_label="Time", y_axis_label="Machines")
    # chart.display(scheduler_job_estimate, machines)
    # print("Gantt chart generated.")

    # Transpile Phase    
    print("Starting Transpile Phase...")
    transpile_phase = ConcreteTranspilePhase()
    transpiled_job = transpile_phase.execute(scheduler_job_estimate, machines, capture_result_schedule)
    print("Transpile Phase Complete.")
    
    # # # Execution Phase
    # print("Starting Execution Phase...")
    # execution_phase = ConcreteExecutionPhase()
    # scheduler_job_simulation = execution_phase.execute(scheduler_job_estimate, machines, transpiled_job, capture_result_schedule)
    # print("Execution Phase Complete.")
    
    # # Visualize schedule as a Gantt chart
    # chart = GanttChart(title="Quantum Schedule", x_axis_label="Time", y_axis_label="Machines")
    # chart.display(scheduler_job_simulation, machines)
    # print("Gantt chart generated.")
    
    # print("Starting Result Phase...")
    # result_phase = ConcreteResultPhase()
    # final_result = result_phase.execute(scheduler_job, origin_job_info, data, utilization_permachine, result_Schedule)
    # print("Result Phase Complete.")
    

if __name__ == "__main__":
    test_concrete_flow()