import asyncio
import json
from collections import defaultdict, deque


class Dispatcher:
    def __init__(self, plan, machine_capacity):
        self.available_cpu = dict(machine_capacity)
        self.status = {}
        self.queues = {}

        grouped = defaultdict(list)
        assignments = plan["assignments"]
        ids = [a["assignment_id"] for a in assignments]

        if len(ids) != len(set(ids)):
            raise ValueError("assignment_id bị trùng")

        known_ids = set(ids)

        for assignment in assignments:
            aid = assignment["assignment_id"]
            machine = assignment["machine_id"]
            cpu = assignment["resources"]["cpu"]

            if machine not in machine_capacity:
                raise ValueError(f"Machine không tồn tại: {machine}")

            if cpu <= 0 or cpu > machine_capacity[machine]:
                raise ValueError(f"CPU yêu cầu không hợp lệ: {aid}")

            for dependency in assignment.get("depends_on", []):
                if dependency not in known_ids:
                    raise ValueError(f"Dependency không tồn tại: {dependency}")

            self.status[aid] = "PENDING"
            grouped[machine].append(assignment)

        for machine, items in grouped.items():
            orders = [a["dispatch_order"] for a in items]
            if len(orders) != len(set(orders)):
                raise ValueError(f"dispatch_order bị trùng trên {machine}")

            self.queues[machine] = deque(
                sorted(items, key=lambda a: a["dispatch_order"])
            )

    async def execute_on_machine(self, assignment):
        """Mô phỏng worker: chỉ trả về khi job đã hoàn thành."""
        durations = {
            "job-A": 2,
            "job-B": 4,
            "job-C": 8,
            "job-D": 1,
        }

        job = assignment["job_id"]
        print(f"START {job}")
        await asyncio.sleep(durations.get(job, 1))
        print(f"DONE  {job}")

    async def execute(self, assignment):
        aid = assignment["assignment_id"]
        machine = assignment["machine_id"]
        cpu = assignment["resources"]["cpu"]

        self.status[aid] = "RUNNING"

        try:
            await self.execute_on_machine(assignment)
        except Exception as error:
            self.status[aid] = "FAILED"
            print(f"FAILED {assignment['job_id']}: {error}")
        else:
            self.status[aid] = "SUCCEEDED"
        finally:
            self.available_cpu[machine] += cpu

    async def run(self):
        running = set()

        while any(self.queues.values()) or running:
            for machine, queue in self.queues.items():
                while queue:
                    assignment = queue[0]  # Chỉ xét đầu hàng
                    aid = assignment["assignment_id"]
                    deps = assignment.get("depends_on", [])

                    # Dependency thất bại: job này không thể chạy.
                    if any(
                        self.status[d] in {"FAILED", "BLOCKED"}
                        for d in deps
                    ):
                        self.status[aid] = "BLOCKED"
                        queue.popleft()
                        continue

                    if not all(
                        self.status[d] == "SUCCEEDED" for d in deps
                    ):
                        break  # Không vượt qua job đầu hàng

                    cpu = assignment["resources"]["cpu"]
                    if self.available_cpu[machine] < cpu:
                        break

                    # Giữ CPU trước khi tạo task; không await ở đây.
                    self.available_cpu[machine] -= cpu
                    self.status[aid] = "DISPATCHING"
                    queue.popleft()

                    task = asyncio.create_task(self.execute(assignment))
                    running.add(task)

            if running:
                _, running = await asyncio.wait(
                    running,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            elif any(self.queues.values()):
                pending = [
                    a["assignment_id"]
                    for queue in self.queues.values()
                    for a in queue
                ]
                raise RuntimeError(
                    "Không thể tiến tiếp: dependency vòng hoặc "
                    f"xung đột với thứ tự nghiêm ngặt: {pending}"
                )

        return self.status


async def main():
    with open("schedule_plan.json", encoding="utf-8") as file:
        plan = json.load(file)

    dispatcher = Dispatcher(
        plan,
        machine_capacity={"machine-01": 3},
    )

    statuses = await dispatcher.run()
    print(json.dumps(statuses, indent=2))


if __name__ == "__main__":
    asyncio.run(main())