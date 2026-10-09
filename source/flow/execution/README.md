# Cẩm nang Module Execution (Developer & Customization Guide)

Chào mừng bạn đến với module **Execution** của nền tảng Mô phỏng Lập lịch Lượng tử (**Quantum Scheduling Simulation**).

Mục tiêu của module này là thực thi lịch trình các mạch lượng tử trên cụm máy QPU theo mô hình **Mô phỏng sự kiện rời rạc (Discrete-Event Simulation)**, hỗ trợ đa chương trình (**Multi-programming**) và cắt mạch (**Circuit Cutting**).

---

## 1. Bản đồ Cấu trúc Module (`source/flow/execution/`)

| Tên File | Trách nhiệm chính |
| :--- | :--- |
| [`orchestrator.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/orchestrator.py) | **Engine điều phối trung tâm**: Quản lý dòng thời gian ảo (`now`), hàng đợi sự kiện min-heap (`events`), và trạng thái máy (`MachineState`). Hỗ trợ Dependency Injection. |
| [`interfaces.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/interfaces.py) | **Hợp đồng giao diện (Protocols)**: Định nghĩa `JobDispatcherProtocol`, `LayoutStrategy`, `TimelineReporterProtocol`. Không dùng tiền tố `I`, chuẩn Pythonic PEP 8. |
| [`job_dispatcher.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/job_dispatcher.py) | **Bộ bốc việc**: Quản lý hàng đợi, kiểm tra arrival time, kiểm tra DAG dependencies, hỗ trợ chính sách `strict` và `backfill`, lan truyền lỗi cascade (`BLOCKED`). |
| [`batch_executor.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/batch_executor.py) | **Bộ thực thi Batch**: Điều phối chạy mạch trên QPU/Aer, phân biệt rõ mạch thường (Standard) và mạch cắt (True Joint Cutting), tích hợp cổng chờ `LayoutStrategy`. |
| [`circuit_composer.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/circuit_composer.py) | **Bộ đóng gói mạch**: Ghép nhiều mạch độc lập lên không gian qubit rời rạc (`prepare_batch`) hoặc ghép mạch cắt QPD với mạch thường (`compose_joint_cutting_batch`). |
| [`quantum_simulator.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/quantum_simulator.py) | **Trình giả lập QPU**: Chạy mô phỏng ideal (không nhiễu) và noisy (mô hình nhiễu backend QPU thật) qua Qiskit Aer. |
| [`reconstruction_handler.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/reconstruction_handler.py) | **Bộ quản lý kết quả & tái tạo**: Tích lũy số shots đo lường, phát hiện khi các subcircuits của một mạch cha đã chạy xong để kích hoạt tái tạo. |
| [`circuit_reconstructor.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/circuit_reconstructor.py) | **Giải thuật tái tạo FWHT**: Tái tạo phân phối xác suất bitstring từ các kỳ vọng Pauli Z bằng biến đổi Fast Walsh-Hadamard Transform, tính Hellinger Fidelity & TVD. |
| [`timeline_reporter.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/timeline_reporter.py) | **Tầng hiển thị / Logging**: Tách riêng việc in ấn status card `┌─ Time: ... └─` ra khỏi logic tính toán (`ConsoleTimelineReporter` và `SilentTimelineReporter`). |
| [`metrics_calculator.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/execution/metrics_calculator.py) | **Bộ tính toán chỉ số**: Tính Makespan, Turnaround time, Waiting time, Qubit space-time utilization, Cutting overhead... |

---

## 2. Hướng dẫn Tùy biến Chức năng (Extensibility How-To)

Nhờ kiến trúc **Dependency Injection**, bạn có thể thay thế hoặc mở rộng bất kỳ thành phần nào mà không cần sửa code lõi của hệ thống.

### Ví dụ 1: Tự viết một Custom Job Dispatcher (Ưu tiên theo Priority)

Giả sử bạn muốn một bộ bốc việc ưu tiên chạy các mạch có độ ưu tiên cao (`job.priority`) trước thay vì chỉ theo thứ tự FIFO:

```python
from source.flow.execution.orchestrator import ConcreteExecutionPhase
from source.flow.execution.job_dispatcher import JobDispatcher

class PriorityJobDispatcher(JobDispatcher):
    @classmethod
    def select_jobs(cls, now, scheduler_job, results, queue, active, capacity, policy):
        # 1. Sắp xếp lại hàng đợi theo độ ưu tiên giảm dần
        queue.sort(key=lambda name: scheduler_job[name].job_information.priority or 0, reverse=True)
        # 2. Gọi logic bốc việc chuẩn
        return super().select_jobs(now, scheduler_job, results, queue, active, capacity, policy)

# Cắm vào Execution Phase:
custom_phase = ConcreteExecutionPhase(dispatcher=PriorityJobDispatcher())
results = custom_phase.execute(machines, scheduled_jobs)
```

---

### Ví dụ 2: Tự viết một Custom Layout Strategy (Dành cho Tương lai)

Hiện tại, hệ thống mặc định để trống `initial_layout=None` để Qiskit Pass Manager tự chạy `SabreLayout` hoặc `VF2Layout`.
Khi bạn muốn nghiên cứu giải thuật gán qubit vật lý (ví dụ né crosstalk giữa subcircuit và uncut circuit):

```python
from source.flow.execution.interfaces import LayoutStrategy
from source.flow.execution.orchestrator import ConcreteExecutionPhase

class MyCrosstalkAwareLayout(LayoutStrategy):
    def get_initial_layout(self, backend, jobs: dict):
        # Thuật toán của bạn phân tích coupling_map của backend:
        # Trả về danh sách physical qubit IDs tương ứng với từng virtual qubit
        # Ví dụ: Mạch A (2q) -> physical [0, 1], Mạch B (2q) -> physical [3, 4]
        return [0, 1, 3, 4]

# Cắm giải thuật layout của bạn vào hệ thống:
phase_with_custom_layout = ConcreteExecutionPhase(layout_strategy=MyCrosstalkAwareLayout())
results = phase_with_custom_layout.execute(machines, scheduled_jobs)
```

---

### Ví dụ 3: Chạy mô phỏng ở Chế độ Im lặng (Silent Mode - Không in terminal)

Khi chạy benchmark hàng trăm thử nghiệm hoặc chạy song song nhiều batch:

```python
from source.flow.execution.timeline_reporter import SilentTimelineReporter
from source.flow.execution.orchestrator import ConcreteExecutionPhase

# Sử dụng SilentTimelineReporter để tắt hoàn toàn các print log ra terminal
silent_phase = ConcreteExecutionPhase(reporter=SilentTimelineReporter())
results = silent_phase.execute(machines, scheduled_jobs)
```

