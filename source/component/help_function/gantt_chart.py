from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict
import math

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.patheffects as path_effects
from matplotlib.patches import Patch

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "results" / "charts" / "gantt_chart.png"


@dataclass
class GanttChart:
    """
    Modern Gantt chart visualization for quantum circuit scheduling with publication-ready styling.
    """
    title: str = "Schedule Gantt Chart"
    x_axis_label: str = "Time (seconds)"
    y_axis_label: str = "Machines"

    # Refined modern palette: high-contrast, colorblind-friendly, publication-ready
    colors: List[str] = field(default_factory=lambda: [
        "#2563EB",  # Vibrant Blue
        "#0D9488",  # Teal / Dark Emerald
        "#D97706",  # Warm Amber
        "#7C3AED",  # Royal Violet
        "#E11D48",  # Rose Red
        "#0284C7",  # Sky Blue
        "#059669",  # Green
        "#9333EA",  # Purple
        "#EA580C",  # Orange
        "#4F46E5",  # Indigo
    ])

    # Hatch patterns (optional, kept for backwards compatibility / B&W printing)
    hatch_patterns: List[str] = field(default_factory=lambda: [
        '/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*'
    ])
    show_hatch: bool = False
    show_batch_splits: bool = True
    show_makespan: bool = True
    show_legend: bool = True

    @staticmethod
    def is_dark(hex_color: str) -> bool:
        """Determine if color is dark for optimal text contrast."""
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
        return luminance < 0.55

    def display(
        self,
        schedule_job: Dict[str, Any],
        machines: Dict[str, Any],
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
        execution_summary: Any = None,
    ) -> None:
        if not schedule_job or not machines:
            return

        # 1. Setup typography and theme
        plt.rcParams.update({
            'font.size': 10,
            'font.family': 'sans-serif',
            'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
            'axes.edgecolor': '#94A3B8',
            'axes.linewidth': 0.8,
        })

        # 2. Extract machines and sort
        machine_names = sorted(machines.keys())
        y_map = {name: i for i, name in enumerate(machine_names)}

        job_names = sorted(schedule_job.keys())
        c_map = {n: self.colors[i % len(self.colors)] for i, n in enumerate(job_names)}
        h_map = {n: self.hatch_patterns[i % len(self.hatch_patterns)] for i, n in enumerate(job_names)}

        drawables = []
        overall_end = 0.0

        for name, info in schedule_job.items():
            assigned = getattr(info, "assigned_machine", None)

            start = getattr(info, "scheduled_start_time", None)
            if start is None:
                start = getattr(info, "start_time", None)

            end = getattr(info, "scheduled_end_time", None)
            if end is None:
                end = getattr(info, "end_time", None)

            if assigned not in y_map or start is None or end is None:
                continue

            duration = float(end) - float(start)
            if duration <= 0:
                continue

            # Resolve qubits
            num_qubits = getattr(info, "num_qubits", None)
            for attr_chain in ["job_info", "job_information"]:
                if num_qubits is None and hasattr(info, attr_chain) and getattr(info, attr_chain):
                    sub = getattr(info, attr_chain)
                    num_qubits = getattr(sub, "num_qubits", None)
                    if num_qubits is None and hasattr(sub, "circuit") and sub.circuit:
                        num_qubits = getattr(sub.circuit, "num_qubits", None)

            # Resolve shots
            shots = getattr(info, "requested_shots", None) or getattr(info, "shots", None)
            for attr_chain in ["job_info", "job_information"]:
                if shots is None and hasattr(info, attr_chain) and getattr(info, attr_chain):
                    sub = getattr(info, attr_chain)
                    shots = getattr(sub, "requested_shots", None) or getattr(sub, "shots", None)

            # Resolve fidelity & status
            fidelity = getattr(info, "fidelity", None)
            status = getattr(info, "status", None)

            drawables.append({
                'y': y_map[assigned],
                'start': float(start),
                'end': float(end),
                'duration': duration,
                'name': name,
                'qubits': num_qubits,
                'shots': shots,
                'fidelity': fidelity,
                'status': status,
                'color': c_map.get(name, "#3B82F6"),
                'hatch': h_map.get(name, "") if self.show_hatch else "",
            })
            overall_end = max(overall_end, float(end))

        if not drawables:
            return

        # If execution_summary provides exact makespan
        if execution_summary and getattr(execution_summary, "makespan", None):
            overall_end = max(overall_end, float(execution_summary.makespan))

        # Check for batch segments
        job_batch_segments = defaultdict(list)
        if self.show_batch_splits and execution_summary and hasattr(execution_summary, "batches"):
            for b in execution_summary.batches:
                for jid in b.job_ids:
                    job_batch_segments[jid].append((float(b.start_time), float(b.end_time), b.shots))

        # 3. Dynamic figure sizing
        fig_width = 11.5
        fig_height = max(4.0, 1.25 * len(machine_names) + 1.8)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        # 4. Swimlane backgrounds & Machine dividers
        for idx in range(len(machine_names)):
            row_color = "#F8FAFC" if idx % 2 == 0 else "#FFFFFF"
            ax.axhspan(idx - 0.5, idx + 0.5, facecolor=row_color, edgecolor="none", zorder=0)
            if idx > 0:
                ax.axhline(idx - 0.5, color="#E2E8F0", linewidth=0.8, linestyle="-", zorder=1)

        # 5. Greedy lane assignment per machine for overlapping jobs (multi-programming)
        jobs_by_machine = defaultdict(list)
        for d in drawables:
            jobs_by_machine[d['y']].append(d)

        for mach_y, m_jobs in jobs_by_machine.items():
            m_jobs.sort(key=lambda x: (x['start'], -x['duration']))

            lanes = []
            for job in m_jobs:
                assigned_lane = -1
                for l_idx, lane_end in enumerate(lanes):
                    if job['start'] >= lane_end - 1e-9:
                        assigned_lane = l_idx
                        lanes[l_idx] = job['end']
                        break
                if assigned_lane == -1:
                    assigned_lane = len(lanes)
                    lanes.append(job['end'])
                job['lane'] = assigned_lane

            num_lanes = len(lanes)
            total_lane_span = 0.68
            lane_slot = total_lane_span / num_lanes
            bar_height = min(0.32, lane_slot * 0.85)

            for job in m_jobs:
                offset = (job['lane'] - (num_lanes - 1) / 2.0) * lane_slot
                center_y = mach_y + offset

                ax.barh(
                    center_y,
                    job['duration'],
                    left=job['start'],
                    height=bar_height,
                    align='center',
                    color=job['color'],
                    edgecolor='#1E293B',
                    linewidth=0.8,
                    hatch=job['hatch'],
                    alpha=0.92,
                    zorder=3
                )

                # Batch separators inside the bar if multiple batches exist
                if job['name'] in job_batch_segments and len(job_batch_segments[job['name']]) > 1:
                    segments = job_batch_segments[job['name']]
                    for seg_start, seg_end, seg_shots in segments[:-1]:
                        ax.vlines(
                            x=seg_end,
                            ymin=center_y - bar_height / 2.0,
                            ymax=center_y + bar_height / 2.0,
                            color="#FFFFFF",
                            linestyle="--",
                            linewidth=1.2,
                            alpha=0.9,
                            zorder=4
                        )

                makespan_ref = max(overall_end, 1e-6)
                bar_ratio = job['duration'] / makespan_ref

                text_color = "#FFFFFF" if self.is_dark(job['color']) else "#0F172A"
                stroke_color = "#000000" if text_color == "#FFFFFF" else "#FFFFFF"

                font_size = max(6.5, min(9.0, 9.0 - (num_lanes - 1) * 0.8))
                if bar_ratio >= 0.22:
                    sub_text = []
                    if job['qubits']: sub_text.append(f"{job['qubits']}Q")
                    if job['shots']: sub_text.append(f"{job['shots']} shots")
                    text_str = f"{job['name']} ({', '.join(sub_text)})" if sub_text else job['name']
                elif bar_ratio >= 0.12:
                    text_str = f"{job['name']} ({job['qubits']}Q)" if job['qubits'] else job['name']
                elif bar_ratio >= 0.06:
                    text_str = job['name']
                else:
                    text_str = ""

                if text_str:
                    t = ax.text(
                        job['start'] + job['duration'] / 2.0,
                        center_y,
                        text_str,
                        va="center",
                        ha="center",
                        fontsize=font_size,
                        fontweight='bold',
                        color=text_color,
                        zorder=5
                    )
                    t.set_path_effects([
                        path_effects.withStroke(linewidth=2, foreground=stroke_color, alpha=0.35)
                    ])
                elif bar_ratio < 0.06:
                    ax.text(
                        job['end'] + makespan_ref * 0.01,
                        center_y,
                        job['name'],
                        va="center",
                        ha="left",
                        fontsize=font_size,
                        fontweight='bold',
                        color="#1E293B",
                        zorder=5
                    )

        # 6. Makespan reference line and badge
        if self.show_makespan and overall_end > 0:
            ax.axvline(overall_end, color="#DC2626", linestyle="--", linewidth=1.5, alpha=0.85, zorder=4)
            badge_y = len(machine_names) - 0.5 + 0.08
            if overall_end < 0.01:
                ms_text = f"Makespan: {overall_end:.5f}s"
            elif overall_end < 1.0:
                ms_text = f"Makespan: {overall_end:.4f}s"
            else:
                ms_text = f"Makespan: {overall_end:.2f}s"

            ax.text(
                overall_end,
                badge_y,
                f" {ms_text} ",
                va="bottom",
                ha="right",
                fontsize=8.5,
                fontweight='bold',
                color="#991B1B",
                bbox=dict(boxstyle="round,pad=0.25", fc="#FEF2F2", ec="#F87171", lw=0.9),
                zorder=6
            )

        # 7. Axes Configuration
        # TIME STARTS STRICTLY FROM 0 (no negative margins)
        x_min = 0.0
        x_max = overall_end * 1.07 if overall_end > 0 else 1.0
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(-0.5, len(machine_names) - 0.5 + 0.22)

        def format_time(val, pos):
            if abs(val) < 1e-9:
                return "0"
            if x_max < 0.01:
                return f"{val:.4f}"
            elif x_max < 0.1:
                return f"{val:.3f}"
            elif x_max < 10.0:
                return f"{val:.2f}"
            else:
                return f"{val:.1f}"

        ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_time))
        ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=8, min_n_ticks=5))

        # 8. Legend at the top
        legend_handles = []
        if self.show_legend:
            for name in job_names:
                info = schedule_job[name]
                q = getattr(info, "num_qubits", None)
                for attr_chain in ["job_info", "job_information"]:
                    if q is None and hasattr(info, attr_chain) and getattr(info, attr_chain):
                        sub = getattr(info, attr_chain)
                        q = getattr(sub, "num_qubits", None)
                        if q is None and hasattr(sub, "circuit") and sub.circuit:
                            q = getattr(sub.circuit, "num_qubits", None)

                s = getattr(info, "requested_shots", None) or getattr(info, "shots", None)
                for attr_chain in ["job_info", "job_information"]:
                    if s is None and hasattr(info, attr_chain) and getattr(info, attr_chain):
                        sub = getattr(info, attr_chain)
                        s = getattr(sub, "requested_shots", None) or getattr(sub, "shots", None)

                label_parts = [name]
                meta = []
                if q is not None: meta.append(f"{q}Q")
                if s is not None: meta.append(f"{s} shots")
                fid = getattr(info, "fidelity", None)
                if fid is not None: meta.append(f"fid: {fid:.3f}")
                if meta:
                    label_parts.append(f"({', '.join(meta)})")

                legend_handles.append(
                    Patch(facecolor=c_map[name], edgecolor="#1E293B", linewidth=0.8, label=" ".join(label_parts))
                )

        num_legend_cols = min(len(legend_handles), 4)
        legend_rows = math.ceil(len(legend_handles) / num_legend_cols) if num_legend_cols > 0 else 1
        title_pad = 22 + (18 * legend_rows if self.show_legend and legend_handles else 0)

        ax.set_title(self.title, pad=title_pad, fontsize=13, fontweight='bold', color="#0F172A")
        ax.set_xlabel(self.x_axis_label, fontweight='bold', fontsize=11, color="#1E293B", labelpad=8)
        ax.set_ylabel(self.y_axis_label, fontweight='bold', fontsize=11, color="#1E293B", labelpad=10)

        # Machine Y-ticks
        ax.set_yticks(range(len(machine_names)))
        y_labels = []
        for key in machine_names:
            machine_obj = machines[key]
            m_name = getattr(machine_obj, 'name', key)
            qubits = getattr(machine_obj, 'capacity', None)
            if qubits is None and hasattr(machine_obj, 'configuration'):
                try:
                    config = machine_obj.configuration()
                    if hasattr(config, 'num_qubits'):
                        qubits = config.num_qubits
                except Exception:
                    pass
            if qubits is not None:
                y_labels.append(f"{m_name}\n({qubits} qubits)")
            else:
                y_labels.append(m_name)

        ax.set_yticklabels(y_labels, fontsize=10, fontweight='bold', color="#1E293B")

        # Gridlines
        ax.grid(True, axis="x", linestyle="--", linewidth=0.7, alpha=0.6, color="#CBD5E1", zorder=2)
        ax.set_axisbelow(True)

        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color("#94A3B8")
        ax.spines["bottom"].set_color("#94A3B8")

        if self.show_legend and legend_handles:
            ax.legend(
                handles=legend_handles,
                loc="upper center",
                bbox_to_anchor=(0.5, 1.13 + 0.03 * (legend_rows - 1)),
                ncol=num_legend_cols,
                frameon=True,
                facecolor="#F8FAFC",
                edgecolor="#CBD5E1",
                fontsize=8.5,
                handlelength=1.2,
                handleheight=0.8,
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close('all')
        print(f"Gantt chart saved to: {output_path}")

