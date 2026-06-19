import sys
sys.path.append('./')
from types import SimpleNamespace
from typing import Any, Dict, List

from component.dataclass.job_info import ExecutionResult
from component.visualize.gantt_chart import GanttChart
from qiskit.quantum_info.analysis import hellinger_fidelity

from flow.execution.main_execution_quantum import MainExecutionResult


class PostExecution:
    def update_job_info_with_results(
        self,
        scheduler_job_simulation: Dict[str, List["MainExecutionResult"]],
    ) -> dict[str, ExecutionResult]:
        """Update the job info with execution results."""
        updated_job_info: dict[str, ExecutionResult] = {}
        for machine_name, execution_results in scheduler_job_simulation.items():
            current_machine_time = 0.0

            for merged_result in execution_results:
                execution_time = float(merged_result.execution_time or 0.0)
                start_time = current_machine_time
                end_time = start_time + execution_time
                current_machine_time = end_time

                fidelity = None
                if (
                    merged_result.distribution_no_noise is not None
                    and merged_result.distribution_with_noise is not None
                ):
                    fidelity = hellinger_fidelity(
                        merged_result.distribution_no_noise,
                        merged_result.distribution_with_noise,
                    )

                for job_info in merged_result.job_info or []:
                    execution_result = ExecutionResult(
                        job_info=job_info,
                        assigned_machine=machine_name,
                        distribution_no_noise=merged_result.distribution_no_noise,
                        distribution_with_noise=merged_result.distribution_with_noise,
                        fidelity=fidelity,
                        start_time=start_time,
                        end_time=end_time,
                        execution_time=execution_time,
                    )
                    updated_job_info[job_info.job_name] = execution_result
        return updated_job_info

    def draw_gantt_chart(
        self,
        execution_results: dict[str, ExecutionResult],
        machines: Dict[str, Any] | None = None,
        output_path: str = "execution_gantt_chart.png",
    ) -> None:
        """Draw a Gantt chart for final execution results."""
        if machines is None:
            machine_names = {
                result.assigned_machine
                for result in execution_results.values()
                if result.assigned_machine is not None
            }
            machines = {
                machine_name: SimpleNamespace(name=machine_name)
                for machine_name in sorted(machine_names)
            }

        gantt_input = {}
        for job_name, result in execution_results.items():
            gantt_input[job_name] = SimpleNamespace(
                assigned_machine=result.assigned_machine,
                scheduled_start_time=result.start_time,
                scheduled_end_time=result.end_time,
            )

        chart = GanttChart(
            title="Quantum Execution (Transpiled)",
            x_axis_label="Time",
            y_axis_label="Machines",
        )
        chart.display(gantt_input, machines, output_path=output_path)

    def execute(
        self,
        machines: Dict[str, Any],
        scheduler_job_simulation: Dict[str, List["MainExecutionResult"]],
    ) -> dict[str, ExecutionResult]:
        print("Post-execution analysis begins.")
        result = self.update_job_info_with_results(scheduler_job_simulation)
        print(result)
        self.draw_gantt_chart(result, machines, output_path="execution_gantt_chart.png")
        print("Post-execution analysis complete.")

        return result
