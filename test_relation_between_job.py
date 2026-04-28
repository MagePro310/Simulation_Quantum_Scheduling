from component.relation.job_relation import build_job_relations

jobs = [
    {"job": "job1", "machine": "fake_belem",  "start": 4.0, "end": 7.0},
    {"job": "job2", "machine": "fake_bogota", "start": 0.0, "end": 3.0},
    {"job": "job3", "machine": "fake_bogota", "start": 0.0, "end": 4.0},
    {"job": "job4", "machine": "fake_bogota", "start": 3.0, "end": 6.0},
]

if __name__ == "__main__":
    relations = build_job_relations(jobs)
    for r in relations:
        print(r)