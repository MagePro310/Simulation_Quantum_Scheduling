"""FFD cho QPU dị thể, hiện thực độc lập Algorithm 1, mục VI-C (trang 6).

Nguồn: Seitz, Geiger, Mendl (2024),
Multithreaded Parallelism for Heterogeneous Clusters of QPUs.
Python >= 3.10, chỉ dùng thư viện chuẩn. Không cần Qiskit/Gurobi.

Chạy ví dụ:       python ffd_qpu.py
Chạy kiểm thử:    python ffd_qpu.py --test
Đọc JSON:        python ffd_qpu.py --input input.json --slot-duration 2
Lưu kết quả:     python ffd_qpu.py > schedule.json

Định dạng input.json:
{
  "qpus": [{"name": "qpu0", "num_qubits": 5}],
  "jobs": [{"name": "job0", "num_qubits": 3}]
}

ffd_pack trả bins theo đúng thứ tự closed + open của giả mã, kể cả bin rỗng.
Giữ thứ tự QPU đầu vào; các job bằng kích thước giữ thứ tự đầu vào.
Mỗi lần mở thêm bins phải tạo objects mới, không sao chép trạng thái đã dùng.
Job vượt QPU lớn nhất bị từ chối: circuit cutting nằm ngoài thuật toán này.

to_schedule là lớp chuyển đổi bổ sung, không phải bước trong Algorithm 1:
copy_index k tương ứng slot [k*d, (k+1)*d), với d là tổng thời lượng slot
chung (có thể bao gồm setup). Job trong cùng bin chạy đồng thời. Các bản sao
của cùng QPU chạy tuần tự. Bin rỗng không tạo assignment nhưng giữ chỉ số slot.
qubit_start/stop chỉ là đoạn chỉ số logic để minh họa dung lượng, không phải
mapping lên coupling graph vật lý. Không xét shots, thời lượng riêng từng job,
arrival_time, priority, dependencies, noise hoặc connectivity. Đây là scheduler,
không thực thi quantum circuits và không hiện thực mô hình MILP của bài báo.

Độ phức tạp bản quét tuyến tính: O(n log n + n^2*m), bộ nhớ O(n*m),
với n jobs, m QPUs (tối đa n nhóm bản sao khi n > 0).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from typing import Iterable


def _validate(name: str, num_qubits: int) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name phải là chuỗi không rỗng")
    if type(num_qubits) is not int or num_qubits <= 0:
        raise ValueError("num_qubits phải là số nguyên dương")


@dataclass(frozen=True)
class Job:
    name: str
    num_qubits: int

    def __post_init__(self) -> None:
        _validate(self.name, self.num_qubits)


@dataclass(frozen=True)
class QPU:
    name: str
    num_qubits: int

    def __post_init__(self) -> None:
        _validate(self.name, self.num_qubits)


@dataclass(eq=False)
class Bin:
    """Một bản sao QPU; identity riêng cho mỗi cặp (QPU, copy_index)."""

    qpu: QPU
    copy_index: int
    jobs: list[Job] = field(default_factory=list)
    used_qubits: int = field(default=0, init=False)

    @property
    def remaining_qubits(self) -> int:
        return self.qpu.num_qubits - self.used_qubits

    def add(self, job: Job) -> None:
        if job.num_qubits > self.remaining_qubits:
            raise ValueError(f"Job {job.name!r} không vừa bin")
        self.jobs.append(job)
        self.used_qubits += job.num_qubits


def find_first_fitting(job: Job, bins: Iterable[Bin]) -> Bin | None:
    """Trả bin đầu tiên đủ qubit trống; None nếu không có."""
    return next((b for b in bins if job.num_qubits <= b.remaining_qubits), None)


def ffd_pack(jobs: Iterable[Job], qpus: Iterable[QPU]) -> list[Bin]:
    """Xếp batch jobs vào bins theo Algorithm 1; không sửa collections đầu vào.

    Input: jobs độc lập, QPUs theo thứ tự ưu tiên first-fit.
    Output: bins đầy theo thứ tự đóng, sau đó các bins còn mở.
    Raises ValueError: tên trùng, không có QPU, hoặc job quá lớn.
    Batch rỗng vẫn trả nhóm bins rỗng đầu tiên như giả mã.
    """
    jobs, qpus = list(jobs), list(qpus)
    if not qpus:
        raise ValueError("Cần ít nhất một QPU")
    for items, label in ((jobs, "job"), (qpus, "QPU")):
        if len({item.name for item in items}) != len(items):
            raise ValueError(f"Tên {label} phải duy nhất")
    max_capacity = max(q.num_qubits for q in qpus)
    for job in jobs:
        if job.num_qubits > max_capacity:
            raise ValueError(f"Job {job.name!r} cần {job.num_qubits} qubit, "
                             f"vượt QPU lớn nhất ({max_capacity})")

    ordered_jobs = sorted(jobs, key=lambda j: j.num_qubits, reverse=True)
    open_bins = [Bin(q, 0) for q in qpus]
    closed_bins: list[Bin] = []
    copy_index = 0
    for job in ordered_jobs:
        target = find_first_fitting(job, open_bins)
        if target is None:
            copy_index += 1
            new_bins = [Bin(q, copy_index) for q in qpus]
            target = find_first_fitting(job, new_bins)
            open_bins.extend(new_bins)
        # Luôn tồn tại sau kiểm tra max_capacity; không bỏ job âm thầm.
        if target is None:
            raise RuntimeError("Không tìm được bin sau khi mở nhóm QPU mới")
        target.add(job)
        if target.remaining_qubits == 0:
            open_bins.remove(target)
            closed_bins.append(target)
    return closed_bins + open_bins


def to_schedule(bins: Iterable[Bin], slot_duration: float = 1.0) -> list[dict]:
    """Chuyển bins thành assignments với slot đều; xem quy ước ở đầu file."""
    if (isinstance(slot_duration, bool)
            or not isinstance(slot_duration, (int, float))
            or not math.isfinite(slot_duration) or slot_duration <= 0):
        raise ValueError("slot_duration phải hữu hạn và > 0")
    assignments = []
    for b in bins:
        offset = 0
        for job in b.jobs:
            assignments.append({
                "job_name": job.name,
                "num_qubits": job.num_qubits,
                "assigned_machine": b.qpu.name,
                "slot": b.copy_index,
                "scheduled_start_time": b.copy_index * slot_duration,
                "scheduled_end_time": (b.copy_index + 1) * slot_duration,
                "qubit_start": offset,
                "qubit_stop": offset + job.num_qubits,
            })
            offset += job.num_qubits
    return sorted(assignments, key=lambda a: (a["slot"], a["assigned_machine"],
                                              a["qubit_start"]))


def run_tests() -> None:
    """Regression tests + kiểm tra bất biến trên 100 batch ngẫu nhiên."""
    import random
    import unittest

    class FFDTests(unittest.TestCase):
        def test_whole_group_and_backfill(self):
            jobs = [Job(str(i), n) for i, n in enumerate([6, 6, 4, 2, 2])]
            bins = ffd_pack(jobs, [QPU("small", 4), QPU("large", 6)])
            actual = {(b.qpu.name, b.copy_index): [j.num_qubits for j in b.jobs]
                      for b in bins}
            self.assertEqual(actual, {("small", 0): [4], ("large", 0): [6],
                                      ("small", 1): [2, 2], ("large", 1): [6]})

        def test_first_fit_not_best_fit(self):
            bins = ffd_pack([Job("a", 4)], [QPU("big", 8), QPU("small", 4)])
            self.assertEqual(bins[0].jobs, [Job("a", 4)])

        def test_stable_ties_and_closed_order(self):
            jobs = [Job("a", 3), Job("b", 3), Job("c", 2)]
            bins = ffd_pack(jobs, [QPU("q", 5)])
            self.assertEqual([[j.name for j in b.jobs] for b in bins],
                             [["a", "c"], ["b"]])
            self.assertEqual([j.name for j in jobs], ["a", "b", "c"])
            self.assertEqual(to_schedule(bins)[-1]["scheduled_start_time"], 1)

        def test_empty(self):
            bins = ffd_pack([], [QPU("q", 5)])
            self.assertEqual(len(bins), 1)
            self.assertEqual(to_schedule(bins), [])

        def test_invalid(self):
            with self.assertRaises(ValueError):
                ffd_pack([Job("a", 6)], [QPU("q", 5)])
            with self.assertRaises(ValueError):
                ffd_pack([], [])
            with self.assertRaises(ValueError):
                ffd_pack([Job("a", 1)] * 2, [QPU("q", 5)])
            with self.assertRaises(ValueError):
                ffd_pack([], [QPU("q", 5)] * 2)
            for value in (0, -1, 1.5, True):
                with self.assertRaises(ValueError):
                    Job("a", value)
            for value in (0, -1, float("nan"), float("inf"), True):
                with self.assertRaises(ValueError):
                    to_schedule([], value)

        def test_random_invariants(self):
            rng = random.Random(42)
            for _ in range(100):
                qpus = [QPU(f"q{i}", rng.randint(1, 20)) for i in range(3)]
                jobs = [Job(f"j{i}", rng.randint(1, max(q.num_qubits for q in qpus)))
                        for i in range(rng.randint(0, 60))]
                bins = ffd_pack(jobs, qpus)
                self.assertCountEqual([j.name for b in bins for j in b.jobs],
                                      [j.name for j in jobs])
                self.assertEqual(len({id(b) for b in bins}), len(bins))
                for b in bins:
                    self.assertEqual(b.used_qubits, sum(j.num_qubits for j in b.jobs))
                    self.assertLessEqual(b.used_qubits, b.qpu.num_qubits)
                assignments = to_schedule(bins, 2.5)
                for a in assignments:
                    self.assertEqual(a["scheduled_end_time"] - a["scheduled_start_time"], 2.5)
                for i, a in enumerate(assignments):
                    for b in assignments[i + 1:]:
                        if a["assigned_machine"] == b["assigned_machine"] and a["slot"] == b["slot"]:
                            self.assertTrue(a["qubit_stop"] <= b["qubit_start"]
                                            or b["qubit_stop"] <= a["qubit_start"])

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FFDTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, help="JSON chứa jobs và qpus")
    parser.add_argument("--slot-duration", type=float, default=1.0)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        run_tests()
        return
    try:
        if args.input:
            data = json.loads(args.input.read_text(encoding="utf-8"))
            jobs = [Job(**j) for j in data["jobs"]]
            qpus = [QPU(**q) for q in data["qpus"]]
        else:
            # Dữ liệu minh họa tự tạo, không phải kết quả benchmark của bài báo.
            jobs = [Job(f"job{i}", n) for i, n in enumerate([6, 6, 4, 2, 2], 1)]
            qpus = [QPU("qpu_4", 4), QPU("qpu_6", 6)]
        bins = ffd_pack(jobs, qpus)
        schedule = to_schedule(bins, args.slot_duration)
        print(json.dumps({"bins": [asdict(b) for b in bins],
                          "schedule": schedule,
                          "makespan": max((a["scheduled_end_time"] for a in schedule), default=0)},
                         ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
