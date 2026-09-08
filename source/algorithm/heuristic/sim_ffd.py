import sys
sys.path.append('./')
from source.algorithm.heuristic.ffd_qpu import Job, QPU, ffd_pack, to_schedule

jobs = [
    Job("job1", 6),
    Job("job2", 6),
    Job("job3", 4),
    Job("job4", 2),
    Job("job5", 2),
]
qpus = [QPU("qpu_4", 4), QPU("qpu_6", 6)]

bins = ffd_pack(jobs, qpus)
print("Packed Bins:")
print(bins)
for assignment in to_schedule(bins, slot_duration=1.0):
    print(assignment)