# Hướng dẫn Phát triển Thuật toán Lập lịch (Algorithm Developer Guide)

Thư mục [`source/algorithm/`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/) chứa toàn bộ các giải thuật lập lịch cho hệ thống mô phỏng lượng tử.

---

## 1. Cấu trúc Thư mục

- [`interfaces.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/interfaces.py): Định nghĩa giao diện chuẩn [`ScheduleAlgorithmProtocol`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/interfaces.py#L11).
- `heuristic/`: Chứa các thuật toán triển khai sẵn:
  - [`FFD.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/FFD.py): First Fit Decreasing cổ điển (xếp theo số qubit giảm dần).
  - [`FFD_v2.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/FFD_v2.py): First Fit Decreasing tích hợp thư viện Circuit Cutting Helper (Pre-sort cutting: cắt tất cả trước khi xếp).
  - [`Adaptive_FFD.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/Adaptive_FFD.py) (hoặc `FFD_v3`): First Fit Decreasing thích ứng (On-the-fly slack cutting: chỉ cắt khi có khoảng trống bin để bảo toàn tối đa fidelity).
  - [`LPT.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/LPT.py): Longest Processing Time (xếp mạch có thời gian ước tính dài nhất trước).
  - [`QGroup.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/algorithm/heuristic/QGroup.py): Thuật toán tối ưu song song (IEEE QCE 2024) dựa trên phân nhóm và quy hoạch tuyến tính nguyên hỗn hợp (MILP).

---

## 2. Hướng dẫn Viết một Thuật toán Lập lịch Mới

Mọi thuật toán mới **chỉ cần viết một class thông thường có hàm `execute(self, scheduler_job, machines)`** là hệ thống tự động nhận diện, không cần kế thừa phức tạp:

```python
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic

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

## 3. Sử dụng Thư Viện Hỗ Trợ Circuit Cutting Trong Giải Thuật

Hệ thống cung cấp sẵn thư viện công cụ cắt mạch [`SchedulingCutterHelper`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/source/flow/schedule/cutting/schedule_cutter_helper.py). Giải thuật có thể import trực tiếp và gọi cắt on-demand:

```python
from source.algorithm import SchedulingCutterHelper
```

### Các hàm công cụ chính:

1. **Cắt hàng loạt các mạch trước khi xếp lịch**:
   ```python
   # Cắt các mạch gốc với target_qubits (mặc định chia đôi cân bằng)
   max_capacity = SchedulingCutterHelper.get_max_capacity(machines)
   jobs_to_schedule = SchedulingCutterHelper.cut_jobs(scheduler_job, target_qubits=max_capacity)
   ```

2. **Ước lượng overhead trước khi cắt**:
   ```python
   # Ước lượng chi phí sampling QPD trước khi cắt để ra quyết định
   overhead = SchedulingCutterHelper.estimate_overhead(s_job, cluster_sizes=[2, 2])
   if overhead <= 81.0:
       # Chấp nhận cắt nếu overhead trong ngưỡng
       sub_jobs = SchedulingCutterHelper.cut_job(s_job, cluster_sizes=[2, 2])
   ```

3. **Cắt động 1 job đơn lẻ theo khoảng trống còn lại của bin (On-the-fly cutting)**:
   ```python
   # Kiểm tra điều kiện cắt trước khi cắt
   if SchedulingCutterHelper.can_cut(s_job):
       # Truyền số qubit mong muốn của từng cụm (ví dụ [slack, remainder])
       sub_jobs = SchedulingCutterHelper.cut_job(s_job, cluster_sizes=[slack, remainder])
   ```

> [!NOTE]
> Thư viện `SchedulingCutterHelper` tự động bảo toàn toàn bộ ràng buộc: liên kết `parentJob` - `childrenJobs`, tính `cutting_overhead`, sinh `subexperiments`, sao chép `depends_on`, `shots`, `arrival_time`, `priority`.

---

## 4. Cách Sử dụng Thuật toán Mới

1. **Chạy độc lập (Standalone)**:
   Xem template tại [`implement/algorithm_template.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/implement/algorithm_template.py):
   ```python
   from source.flow.schedule.phase_schedule import ConcreteSchedulePhase

   schedule_result = ConcreteSchedulePhase(algorithm=MySimpleAlgorithm()).execute(...)
   ```

2. **Chạy thử nghiệm so sánh hàng loạt (Batch Runner)**:
   Thêm thuật toán vào danh sách `ALGORITHMS` trong [`run_batch.py`](file:///home/trieu/D/Quantum_Repo/Simulation_Quantum_Scheduling/run_batch.py) để tự động thu thập kết quả và vẽ biểu đồ so sánh.
