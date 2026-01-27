from dataclasses import dataclass, field
from typing import Any, Dict, List
import math
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt

@dataclass
class GanttChart:
    """
    Simplified Gantt chart visualization with scientific styling.
    """
    title: str = "Schedule Gantt Chart"
    x_axis_label: str = "Time"
    y_axis_label: str = "Machines"
    
    # Okabe-Ito color palette
    colors: List[str] = field(default_factory=lambda: [
        "#E69F00", "#56B4E9", "#009E73", "#F0E442", 
        "#0072B2", "#D55E00", "#CC79A7"
    ])
    # Hatch patterns for black & white printing
    hatch_patterns: List[str] = field(default_factory=lambda: [
        '/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*'
    ])

    def display(self, schedule_job: Dict[str, Any], machines: Dict[str, Any], output_path: str = "gantt_chart.png") -> None:
        if not schedule_job or not machines:
            return

        # 1. Setup plotting style
        plt.rcParams.update({'font.size': 12, 'font.family': 'sans-serif'})
        
        # 2. Prepare Data
        machine_names = sorted(machines.keys())
        y_map = {name: i for i, name in enumerate(machine_names)}
        
        job_names = sorted(schedule_job.keys())
        c_map = {n: self.colors[i % len(self.colors)] for i, n in enumerate(job_names)}
        h_map = {n: self.hatch_patterns[i % len(self.hatch_patterns)] for i, n in enumerate(job_names)}

        drawables = []
        overall_start, overall_end = math.inf, -math.inf

        for name, info in schedule_job.items():
            assigned = getattr(info, "assigned_machine", None)
            start = getattr(info, "scheduled_start_time", None)
            end = getattr(info, "scheduled_end_time", None)

            if assigned not in y_map or start is None or end is None:
                continue

            duration = float(end) - float(start)
            if duration <= 0: continue

            drawables.append({
                'y': y_map[assigned],
                'start': float(start),
                'duration': duration,
                'name': name,
                'color': c_map.get(name, "#999999"),
                'hatch': h_map.get(name, "")
            })
            overall_start = min(overall_start, float(start))
            overall_end = max(overall_end, float(end))

        if not drawables: return

        # 3. Create Figure
        fig_height = max(4, 0.8 * len(machine_names) + 1)
        fig, ax = plt.subplots(figsize=(10, fig_height))

        # 4. Process Overlaps and Draw
        # Group jobs by machine index (y)
        from collections import defaultdict
        jobs_by_machine = defaultdict(list)
        for d in drawables:
            jobs_by_machine[d['y']].append(d)

        for mach_y, jobs in jobs_by_machine.items():
            # Sort by start time
            jobs.sort(key=lambda x: x['start'])
            
            # Simple greedy interval scheduling to assign lanes
            lanes = [] # stores end time of the last job in each lane
            for job in jobs:
                assigned_lane = -1
                for i, lane_end in enumerate(lanes):
                    if job['start'] >= lane_end:
                        assigned_lane = i
                        lanes[i] = job['start'] + job['duration']
                        break
                if assigned_lane == -1:
                    assigned_lane = len(lanes)
                    lanes.append(job['start'] + job['duration'])
                job['lane'] = assigned_lane

            num_lanes = len(lanes)
            row_height_total = 0.6
            lane_height = row_height_total / num_lanes
            
            for job in jobs:
                # Calculate vertical position
                # Base is center (mach_y). Top limit is mach_y + 0.3. Bottom is mach_y - 0.3.
                # We stack from top to bottom or bottom to top. Let's do bottom to top (lane 0 at bottom).
                # Bottom of row = mach_y - 0.3
                base_y = mach_y - 0.3
                center_y = base_y + (job['lane'] * lane_height) + (lane_height * 0.5)
                
                # Draw bar
                ax.barh(
                    center_y, job['duration'], left=job['start'], height=lane_height * 0.9, align='center',
                    color=job['color'], edgecolor='black', linewidth=0.5, alpha=0.9, hatch=job['hatch']
                )
                
                # Draw label if bar is big enough
                text_color = "white" if is_dark(job['color']) else "black"
                # Only show text if height is reasonable
                fontsize = 9 if num_lanes == 1 else max(6, 9 - num_lanes)
                
                ax.text(
                    job['start'] + job['duration'] / 2.0, center_y, job['name'],
                    va="center", ha="center", fontsize=fontsize, fontweight='bold', color=text_color,
                    bbox=dict(boxstyle="square,pad=0.2", fc=job['color'], ec="none") if num_lanes < 3 else None
                )

        # 5. Configure Axes
        ax.set_title(self.title, pad=20, weight='bold')
        ax.set_xlabel(self.x_axis_label, weight='bold')
        ax.set_ylabel(self.y_axis_label, weight='bold')
        
        ax.set_yticks(range(len(machine_names)))
        
        # Generate labels: use .name and qubit count if available, else use key
        y_labels = []
        for key in machine_names:
            machine_obj = machines[key]
            label = key
            
            # Check for name attribute
            if hasattr(machine_obj, 'name'):
                label = str(machine_obj.name)
            
            # Check for qubit count
            qubits = None
            if hasattr(machine_obj, 'configuration'):
                try:
                    config = machine_obj.configuration()
                    if hasattr(config, 'num_qubits'):
                        qubits = config.num_qubits
                except Exception:
                    pass
            
            if qubits is not None:
                label = f"{label}\n({qubits} qubits)"
                
            y_labels.append(label)
        
        ax.set_yticklabels(y_labels)
        
        ax.grid(True, axis="x", linestyle="--", alpha=0.3, color="gray")
        ax.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_linewidth(0.5)
        ax.spines["bottom"].set_linewidth(0.5)

        # Limits
        span = overall_end - overall_start
        margin = max(1.0, 0.05 * span)
        ax.set_xlim(overall_start - margin, overall_end + margin)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close('all')
        print(f"Gantt chart saved to: {output_path}")

def is_dark(hex_color: str) -> bool:
    """Check if color is dark for text contrast."""
    hex_color = hex_color.lstrip('#')
    return ((int(hex_color[0:2], 16) * 299 + 
             int(hex_color[2:4], 16) * 587 + 
             int(hex_color[4:6], 16) * 114) / 1000) < 128