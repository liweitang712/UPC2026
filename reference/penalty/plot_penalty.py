"""Render the example data from penalty_model.py to vector figures."""

import csv
import json
import math
from pathlib import Path

from penalty_model import HALF_WIDTH, HEIGHT, RADIUS


HERE = Path(__file__).resolve().parent
INK = "#10283b"
MUTED = "#4d6270"
GRID = "#dbe4e8"
TEAL = "#077d84"
RED = "#b54b36"
WIDTH, PLOT_HEIGHT = 1020, 420


class Canvas:
    def __init__(self):
        self.elements = []

    def line(self, x1, y1, x2, y2, color=GRID, width=1, dash=""):
        pattern = f' stroke-dasharray="{dash}"' if dash else ""
        self.elements.append(
            f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
            f'stroke="{color}" stroke-width="{width}"{pattern}/>'
        )

    def text(self, x, y, value, size=15, color=INK, anchor="start", bold=False):
        weight = 700 if bold else 400
        self.elements.append(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{value}</text>'
        )

    def rect(self, x, y, width, height, color, stroke="none", dash=""):
        pattern = f' stroke-dasharray="{dash}"' if dash else ""
        self.elements.append(
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" height="{height:.3f}" '
            f'fill="{color}" stroke="{stroke}" stroke-width="1.4"{pattern}/>'
        )

    def circle(self, x, y, radius, color, opacity=1, stroke="none"):
        self.elements.append(
            f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{radius}" fill="{color}" '
            f'fill-opacity="{opacity}" stroke="{stroke}" stroke-width="1.8"/>'
        )

    def path(self, points, color, width=2, dash=""):
        if not points:
            return
        positions = " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
        pattern = f' stroke-dasharray="{dash}"' if dash else ""
        self.elements.append(
            f'<polyline points="{positions}" stroke="{color}" stroke-width="{width}" '
            f'fill="none"{pattern}/>'
        )

    def write(self, filename):
        body = "\n".join(self.elements)
        (HERE / filename).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{PLOT_HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {PLOT_HEIGHT}" font-family="Arial, sans-serif">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>\n{body}\n</svg>\n',
            encoding="utf-8",
        )


class Plot:
    def __init__(self, canvas, left, right, xlim, ylim):
        self.canvas = canvas
        self.left, self.right = left, right
        self.top, self.bottom = 64, 327
        self.xlim, self.ylim = xlim, ylim

    def xy(self, x, y):
        xf = (x - self.xlim[0]) / (self.xlim[1] - self.xlim[0])
        yf = (y - self.ylim[0]) / (self.ylim[1] - self.ylim[0])
        return self.left + xf * (self.right - self.left), self.bottom - yf * (self.bottom - self.top)

    def axes(self, xticks, yticks, x_label, y_label):
        c = self.canvas
        for value in yticks:
            _, y = self.xy(self.xlim[0], value)
            c.line(self.left, y, self.right, y)
            c.text(self.left - 9, y + 5, f"{value:g}", color=MUTED, anchor="end")
        for value in xticks:
            x, _ = self.xy(value, self.ylim[0])
            c.line(x, self.top, x, self.bottom)
            c.text(x, self.bottom + 20, f"{value:g}", color=MUTED, anchor="middle")
        c.line(self.left, self.top, self.left, self.bottom, MUTED, 1.5)
        c.line(self.left, self.bottom, self.right, self.bottom, MUTED, 1.5)
        c.text((self.left + self.right) / 2, self.bottom + 44, x_label, anchor="middle")
        c.text(self.left, self.top - 11, y_label)

    def line(self, x1, y1, x2, y2, color, width=1, dash=""):
        self.canvas.line(*self.xy(x1, y1), *self.xy(x2, y2), color, width, dash)

    def point(self, x, y, radius, color, opacity=1, stroke="none"):
        if self.xlim[0] <= x <= self.xlim[1] and self.ylim[0] <= y <= self.ylim[1]:
            self.canvas.circle(*self.xy(x, y), radius, color, opacity, stroke)

    def path(self, points, color, width=2, dash=""):
        self.canvas.path([self.xy(x, y) for x, y in points], color, width, dash)


def goal_and_sensitivity(result):
    c = Canvas()
    c.text(54, 23, "A   Goal-plane crossing near the right corner", size=18, bold=True)
    c.text(568, 23, "B   Sensitivity to coordinate error", size=18, bold=True)
    plot = Plot(c, 64, 473, (1.5, 4.1), (0.9, 3.0))
    x1, y1 = plot.xy(1.5, HEIGHT)
    x2, y2 = plot.xy(HALF_WIDTH, 0.9)
    c.rect(x1, y1, x2 - x1, y2 - y1, "#edf7f7")
    plot.axes([1.5, 2, 2.5, 3, 3.5, 4], [1, 1.5, 2, 2.5, 3], "Lateral position, y (m)", "Height, z (m)")
    plot.line(1.5, HEIGHT, HALF_WIDTH, HEIGHT, INK, 2.2)
    plot.line(HALF_WIDTH, HEIGHT, HALF_WIDTH, 0.9, INK, 2.2)
    plot.line(1.5, HEIGHT - RADIUS, HALF_WIDTH - RADIUS, HEIGHT - RADIUS, MUTED, 1.3, "5 4")
    plot.line(HALF_WIDTH - RADIUS, HEIGHT - RADIUS, HALF_WIDTH - RADIUS, 0.9, MUTED, 1.3, "5 4")
    with (HERE / "penalty_crossings.csv").open(encoding="utf-8", newline="") as file:
        for i, row in enumerate(csv.DictReader(file)):
            if i % 3 == 0:
                color = TEAL if row["inside_goal"] == "1" else RED
                plot.point(float(row["y_m"]), float(row["z_m"]), 2.2, color, opacity=0.24)
    summary = result["scenarios"]["0.010"]
    y0, z0, var_y, cov, var_z, cutoff = summary["joint_95_ellipse"]
    spread_y = math.sqrt(var_y)
    scale_z = math.sqrt(var_z - cov * cov / var_y)
    perimeter = []
    for index in range(101):
        angle = 2 * math.pi * index / 100
        a, b = math.sqrt(cutoff) * math.cos(angle), math.sqrt(cutoff) * math.sin(angle)
        perimeter.append((y0 + spread_y * a, z0 + cov / spread_y * a + scale_z * b))
    plot.path(perimeter, TEAL, 2.0)
    y_mode, z_mode = summary["entry_mode_y_z"]
    plot.point(y_mode, z_mode, 5.5, "#ffffff", stroke=TEAL)
    _, y_base, z_base = result["baseline_t_y_z"]
    bx, by = plot.xy(y_base, z_base)
    c.line(bx - 4, by - 4, bx + 4, by + 4, INK, 2)
    c.line(bx + 4, by - 4, bx - 4, by + 4, INK, 2)
    c.circle(67, 397, 4.5, "#ffffff", stroke=TEAL)
    c.text(80, 402, "Entry mode", size=13)
    c.text(177, 402, "×", size=16, bold=True)
    c.text(193, 402, "Quadratic baseline", size=13)
    c.line(336, 397, 357, 397, TEAL, 2)
    c.text(364, 402, "Joint 95% ellipse", size=13)

    sens = Plot(c, 573, 996, (0, 42), (55, 102))
    sens.axes([0, 5, 10, 20, 30, 40], [60, 70, 80, 90, 100], "Assumed per-coordinate SD, σ (mm)", "Entry probability (%)")
    for field, color, dash in (("geometric_entry_probability", TEAL, ""), ("radius_inset_probability", RED, "6 5")):
        points = [(1000 * float(sigma), 100 * values[field]) for sigma, values in result["scenarios"].items()]
        sens.path(points, color, width=2.4, dash=dash)
        for x, y in points:
            sens.point(x, y, 4, "#ffffff", stroke=color)
    c.line(583, 397, 611, 397, TEAL, 2.4)
    c.text(620, 402, "Center inside goal", size=13)
    c.line(780, 397, 808, 397, RED, 2.4, "6 5")
    c.text(817, 402, "One-radius clearance", size=13)
    c.write("penalty_prediction.svg")


def trajectory(result):
    c = Canvas()
    c.text(54, 23, "A   Lateral path", size=18, bold=True)
    c.text(568, 23, "B   Vertical path", size=18, bold=True)
    with (HERE / "penalty_trajectory.csv").open(encoding="utf-8", newline="") as file:
        model = [tuple(float(row[key]) for key in ("x_m", "y_m", "z_m")) for row in csv.DictReader(file)]
    t_goal = result["baseline_t_y_z"][0]
    times = [t_goal * index / 100 for index in range(101)]
    quadratic = [(30.4 * t - 8 * t * t, 9.4 * t - 8 * t * t, 0.11 + 6.9 * t - 6 * t * t) for t in times]
    data = result["observations"]
    measured = [(0, 0, RADIUS), data[:3], data[3:]]
    for dim, left, right, upper, label in ((1, 64, 473, 3.4, "Lateral position, y (m)"),
                                           (2, 573, 996, 2.3, "Height, z (m)")):
        p = Plot(c, left, right, (0, 11.1), (0, upper))
        x1, y1 = p.xy(0, upper)
        x2, y2 = p.xy(2.96, 0)
        c.rect(x1, y1, x2 - x1, y2 - y1, "#edf7f7")
        yticks = [0, 1, 2, 3] if dim == 1 else [0, 0.5, 1, 1.5, 2]
        p.axes([0, 2, 4, 6, 8, 10, 11], yticks, "Downfield distance, x (m)", label)
        p.line(11, 0, 11, upper, MUTED, 1.2, "5 5")
        p.path([(row[0], row[dim]) for row in quadratic], RED, width=2, dash="6 5")
        p.path([(row[0], row[dim]) for row in model], TEAL, width=2.7)
        for row in measured:
            p.point(row[0], row[dim], 4, "#ffffff", stroke=INK)
    c.line(65, 397, 92, 397, TEAL, 2.7)
    c.text(100, 402, "Local aerodynamic fit", size=13)
    c.line(287, 397, 314, 397, RED, 2, "6 5")
    c.text(323, 402, "Quadratic baseline", size=13)
    c.circle(579, 397, 4, "#ffffff", stroke=INK)
    c.text(590, 402, "Initial and measured positions", size=13)
    c.write("penalty_paths.svg")


if __name__ == "__main__":
    data = json.loads((HERE / "penalty_results.json").read_text(encoding="utf-8"))
    goal_and_sensitivity(data)
    trajectory(data)
