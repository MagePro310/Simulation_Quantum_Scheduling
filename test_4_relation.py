from collections import defaultdict

def get_machine_intervals(job_dict):
    # 1. Group jobs by machine
    machine_map = defaultdict(list)
    for job_key, job_info in job_dict.items():
        machine_map[job_info.assigned_machine].append(job_info)

    result = {}

    for machine, jobs in machine_map.items():
        # 2. Find all unique start and end times
        timestamps = set()
        for job in jobs:
            timestamps.add(job.scheduled_start_time)
            timestamps.add(job.scheduled_end_time)
        
        sorted_times = sorted(list(timestamps))
        machine_intervals = []

        # 3. Check each interval between sorted timestamps
        for i in range(len(sorted_times) - 1):
            t_start = sorted_times[i]
            t_end = sorted_times[i+1]
            
            # Find all jobs active during this specific window
            # A job is active if it starts at or before t_start AND ends at or after t_end
            active_jobs = [
                job.job_information.job_name 
                for job in jobs 
                if job.scheduled_start_time <= t_start and job.scheduled_end_time >= t_end
            ]
            
            # 4. Add to list if there are active jobs and avoid duplicate consecutive sets
            if active_jobs and (not machine_intervals or machine_intervals[-1] != active_jobs):
                machine_intervals.append(active_jobs)

        result[machine] = machine_intervals

    return result

# --- Example Usage ---
# Mocking your SchedulerJobInfo and JobInfo structure
class JobInfo:
    def __init__(self, job_name): self.job_name = job_name

class SchedulerJobInfo:
    def __init__(self, name, start, end, machine):
        self.job_information = JobInfo(name)
        self.scheduled_start_time = start
        self.scheduled_end_time = end
        self.assigned_machine = machine

# Your provided data + Job 5 example
data = {
    'job1': SchedulerJobInfo('job1', 0.0, 3.0, 'fake_belem'),
    'job2': SchedulerJobInfo('job2', 0.0, 3.0, 'fake_bogota'),
    'job3': SchedulerJobInfo('job3', 0.0, 4.0, 'fake_belem'),
    'job4': SchedulerJobInfo('job4', 0.0, 3.0, 'fake_bogota'),
    'job5': SchedulerJobInfo('job5', 3.0, 5.0, 'fake_belem') # Starts when job1 ends
}

output = get_machine_intervals(data)

for machine, schedule in output.items():
    print(f'machine["{machine}"] = {schedule}')