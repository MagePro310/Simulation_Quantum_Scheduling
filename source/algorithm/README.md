# Hướng dẫn Phát triển Thuật toán Lập lịch (Algorithm Developer Guide)

Thư mục [`source/algorithm/`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/) chứa toàn bộ các giải thuật lập lịch cho hệ thống mô phỏng lượng tử.

---

## 1. Cấu trúc Thư mục

- [`interfaces.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/interfaces.py): Định nghĩa duy nhất một chuẩn [`ScheduleAlgorithmProtocol`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/interfaces.py#L11).
- `heuristic/`: Chứa các thuật toán triển khai sẵn:
  - [`FFD.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/FFD.py): First Fit Decreasing cổ điển (xếp theo số qubit giảm dần).
  - [`FFD_v2.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/FFD_v2.py): First Fit Decreasing cải tiến kết hợp cắt mạch tùy chọn.
  - [`LPT.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/LPT.py): Longest Processing Time (xếp mạch có thời gian ước tính dài nhất trước).
  - [`QGroup.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/QGroup.py): Thuật toán tối ưu song song (IEEE QCE 2024) dựa trên phân nhóm và quy hoạch tuyến tính nguyên hỗn hợp (MILP).

---

## 2. Hướng dẫn Viết một Thuật toán Lập lịch Mới

Mọi thuật toán mới **chỉ cần viết một class thông thường có hàm `execute(self, scheduler_job, machines)`** là hệ thống tự động nhận diện, không cần kế thừa phức tạp:

```python
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.help_function.estimated_time import EstimatedTime

class MySimpleAlgorithm:
    """Thuật toán của bạn: chỉ cần có đúng hàm execute() nhận 2 tham số."""

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        machine_names = list(machines.keys())
        dispatch_counters = {m: 0 for m in machine_names}

        # Duyệt và gán máy + thứ tự dispatch cho từng job
        for idx, (job_name, job) in enumerate(scheduler_job.items()):
            assigned_machine = machine_names[idx % len(machine_names)]
            job.assigned_machine = assigned_machine
            job.dispatch_order = dispatch_counters[assigned_machine]
            dispatch_counters[assigned_machine] += 1

        return scheduler_job
```

---

## 3. Cách Sử dụng Thuật toán Mới

1. **Chạy độc lập (Standalone)**:
   Xem template tại [`implement/algorithm_template.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/implement/algorithm_template.py):
   ```python
   from source.flow.schedule.phase_schedule import ConcreteSchedulePhase

   schedule_result = ConcreteSchedulePhase(algorithm=MySimpleAlgorithm()).execute(...)
   ```

2. **Chạy thử nghiệm so sánh hàng loạt (Batch Runner)**:
   Thêm thuật toán vào danh sách `ALGORITHMS` trong [`run_batch.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/run_batch.py) để tự động thu thập kết quả và vẽ biểu đồ so sánh.
