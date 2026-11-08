"""Render F1 and F2 from the frozen supplied-shot forecasts and WP1 traces."""

import argparse
from collections import defaultdict
from math import ceil, floor, fsum, isclose
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np

from figures.evidence import PLANE, cell
from validation.generate_cases import CASE_PATH, PROTOCOL_PATH, read_json, sha256, write_csv
from validation.release_wp3 import FIGURE_FIELDS
from validation.score_entry import read_rows
from validation.summarize_wp3 import FIELDS, compare_kick, summarize_file


MODELS = {
    "B0": ("#2166a6", "-", "D"),
    "B1": ("#714b9a", "--", "+"),
    "B2": ("#a65320", "-.", "x"),
}
REGION = "#1f766e"
MODE = "#e0a71b"
FAN = "#66a9d1"
INK = "#1e2b36"


def path_line(ax, points, axis, **style):
    ax.plot([point["x_m"] for point in points], [point[axis] for point in points], **style)


def f1(case, traces):
    fig, panels = plt.subplots(2, 1, sharex=True, figsize=(9.0, 6.4),
                               layout="constrained")
    fig.suptitle("F1   |   Observed flight and extrapolated trajectories",
                 x=.06, ha="left", color=INK, fontweight="bold")
    cutoff = case["observations"][-1]
    observations = [case["initial"], *case["observations"]]
    goal_x = case["goal"]["x_m"]
    for ax, axis, ylabel in zip(panels, ("y_m", "z_m"), ("Lateral y (m)", "Height z (m)")):
        ax.axvspan(observations[0]["x_m"], cutoff["x_m"], color="#e6edf3", zorder=0)
        ax.axvline(cutoff["x_m"], color="#667785", linestyle=":", linewidth=1)
        ax.axvline(goal_x, color="#333c44", linestyle=":", linewidth=1)
        for draw in traces["fan"]:
            path_line(ax, draw["trace"], axis, color=FAN, alpha=.16, lw=.9)
        for baseline in traces["baselines"]:
            color, linestyle, _ = MODELS[baseline["model_id"]]
            path_line(ax, baseline["trace"], axis, color=color, linestyle=linestyle, lw=1.65)
        ax.scatter([point["x_m"] for point in observations], [point[axis] for point in observations],
                   color=INK, edgecolor="white", linewidth=.65, s=30, zorder=5)
        ax.set(xlim=(-.15, goal_x + .25), ylabel=ylabel)
        ax.grid(axis="y", color="#dfe5e9", linewidth=.65)
    for x, caption, anchor in ((cutoff["x_m"], f"{cutoff['t_s']:.2f} s cutoff", "left"),
                               (goal_x, f"Goal plane ({goal_x:g} m)", "right")):
        panels[0].annotate(caption, (x, .96), xycoords=panels[0].get_xaxis_transform(),
                           xytext=(4 if anchor == "left" else -4, 0), textcoords="offset points",
                           ha=anchor, va="top", color="#51616e", fontsize=8.5)
    panels[-1].set_xlabel("Forward x (m)")
    handles = [
        Line2D([], [], color=INK, marker="o", linestyle="none", label="Release and two observations"),
        Patch(color="#e6edf3", label="Observed span"),
        Line2D([], [], color=FAN, lw=2, label=f"{traces['model_id']} posterior fan"),
    ]
    for model, (color, linestyle, _) in MODELS.items():
        handles.append(Line2D([], [], color=color, ls=linestyle, label=f"{model} point fit"))
    panels[0].legend(handles=handles, loc="lower right", ncol=2, fontsize=8, framealpha=.94)
    return fig


def grid_edges(indices, width):
    return np.arange(indices[0], indices[1] + 1, dtype=float) * width


def probability_grid(predictions, model, width):
    weights_by_cell = defaultdict(list)
    total_weights = []
    plane_points = []
    for row in read_rows(predictions, FIELDS):
        if row["model_id"] != model:
            continue
        weight = float(row["weight"])
        total_weights.append(weight)
        if row["event"] in PLANE and weight:
            y, z = float(row["y_m"]), float(row["z_m"])
            weights_by_cell[cell(y, z, width)].append(weight)
            plane_points.append((y, z, weight))
    total = fsum(total_weights)
    plane_mass = fsum(w for _, _, w in plane_points)
    grid = {key: fsum(weights) / plane_mass for key, weights in weights_by_cell.items()}
    return grid, plane_points, total, plane_mass


def outline(cells, width):
    segments = []
    for y, z in sorted(cells):
        edges = (
            ((y-1, z), ((y, z), (y, z+1))),
            ((y+1, z), ((y+1, z), (y+1, z+1))),
            ((y, z-1), ((y, z), (y+1, z))),
            ((y, z+1), ((y, z+1), (y+1, z+1))),
        )
        segments.extend([(a * width, b * width) for a, b in points]
                        for neighbour, points in edges if neighbour not in cells)
    return segments


def goal_frame(ax, goal, radius):
    y0, y1, z0, z1 = (goal[key] for key in ("y_min_m", "y_max_m", "z_min_m", "z_max_m"))
    ax.add_patch(Rectangle((y0, z0), y1-y0, z1-z0, fill=False, ec=INK, lw=1.6, zorder=4))
    ax.add_patch(Rectangle((y0+radius, radius), y1-y0-2*radius, z1-2*radius,
                           fill=False, ec="#667785", ls="--", lw=1.0, zorder=4))


def plane_panel(ax, limits, grid, region_edges, baselines, mode, case, width, vmax):
    yrange, zrange = limits
    values = np.zeros((zrange[1] - zrange[0], yrange[1] - yrange[0]))
    for (y, z), probability in grid.items():
        if yrange[0] <= y < yrange[1] and zrange[0] <= z < zrange[1]:
            values[z - zrange[0], y - yrange[0]] = 100 * probability
    heat = ax.pcolormesh(grid_edges(yrange, width), grid_edges(zrange, width),
                         np.ma.masked_equal(values, 0), shading="flat", cmap="Blues",
                         vmin=0, vmax=vmax, rasterized=False)
    ax.add_collection(LineCollection(region_edges, linewidths=1.6, colors=REGION, zorder=5))
    goal_frame(ax, case["goal"], case["nominal_assumptions"]["radius_m"])
    for model, y, z in baselines:
        color, _, marker = MODELS[model]
        ax.plot(y, z, marker=marker, ms=7, mew=1.5, mfc="white", mec=color,
                linestyle="none", zorder=6)
    if mode is not None:
        ax.plot(*mode, marker="*", ms=12, mew=.8, mfc=MODE, mec="#3b321e",
                linestyle="none", zorder=7)
    ax.set(xlim=[point*width for point in yrange], ylim=[point*width for point in zrange],
           xlabel="Y (m)")
    ax.set_aspect("equal", adjustable="box")
    return heat


def f2(case, primary, repeat, traces, prediction_file):
    stability = compare_kick(primary, repeat)
    mode = primary["entry_mode_yz_m"] if stability["entry_mode_stable"] else None
    interval = primary["plane_intervals"]
    if interval is None:
        raise ValueError("F2 requires a supported plane-conditioned forecast")
    region = interval["joint_region"]
    width = region["cell_width_m"]
    n_cells = next(level["n_cells"] for level in region["levels"] if level["level"] == .95)
    cells = {tuple(index) for index in region["cells_in_descending_mass_order"][:n_cells]}
    grid, points, total, plane_mass = probability_grid(prediction_file, primary["model_id"], width)
    if not isclose(plane_mass / total, primary["p_reach"], abs_tol=1e-12):
        raise ValueError("F2 plane mass differs from the source summary")
    baselines = [(fit["model_id"], fit["event"]["y_m"], fit["event"]["z_m"])
                 for fit in traces["baselines"] if fit["event"]["event"] in PLANE]
    goal = case["goal"]
    y_reference = [goal["y_min_m"], goal["y_max_m"], *(y for _, y, _ in baselines)]
    z_reference = [goal["z_min_m"], goal["z_max_m"], *(z for _, _, z in baselines)]
    full_y = (floor((min(y_reference)-.3)/width), ceil((max(y_reference)+.3)/width))
    full_z = (floor((min(z_reference)-.15)/width), ceil((max(z_reference)+.4)/width))
    iy, iz = zip(*cells)
    zoom_y = (min(iy)-2, max(iy)+3)
    zoom_z = (min(iz)-2, max(iz)+3)
    clipped_mass = fsum(w for y, z, w in points
                       if not (full_y[0]*width <= y < full_y[1]*width
                               and full_z[0]*width <= z < full_z[1]*width)) / total

    fig = plt.figure(figsize=(11.1, 5.6), layout="constrained")
    panel = fig.add_gridspec(2, 2, width_ratios=(2.15, 1), height_ratios=(5.0, 1.1))
    overview, zoom = fig.add_subplot(panel[0, 0]), fig.add_subplot(panel[0, 1])
    fig.suptitle("F2   |   Forecast at the goal plane", x=.06, ha="left",
                 color=INK, fontweight="bold")
    overview.set(title=f"{primary['model_id']}  |  Goal front view", ylabel="Z (m)")
    zoom.set(title="Detail of the 95% region", ylabel="Z (m)")
    vmax = max(grid.values()) * 100
    region_edges = outline(cells, width)
    heat = plane_panel(overview, (full_y, full_z), grid, region_edges, baselines,
                       mode, case, width, vmax)
    plane_panel(zoom, (zoom_y, zoom_z), grid, region_edges, baselines,
                mode, case, width, vmax)
    bar = fig.colorbar(heat, ax=(overview, zoom), shrink=.76, pad=.025)
    bar.set_label("Probability per grid cell (%)\ngiven plane arrival", fontsize=9)

    notes = fig.add_subplot(panel[1, :])
    notes.axis("off")
    handles = [
        Line2D([], [], color=INK, label="Goal frame"),
        Line2D([], [], color="#667785", ls="--", label="Radius clearance"),
        Line2D([], [], color=REGION, label="Joint 95% region"),
    ]
    for model, _, _ in baselines:
        color, _, marker = MODELS[model]
        handles.append(Line2D([], [], mfc="white", mec=color, marker=marker,
                              linestyle="none", label=f"{model} point fit"))
    if mode is not None:
        handles.append(Line2D([], [], mfc=MODE, mec="#3b321e", marker="*",
                              linestyle="none", label="Mode given entry"))
    notes.legend(handles=handles, loc="upper center", ncol=4, frameon=False, fontsize=8.5)
    p_wide = primary["p_reach"] - primary["p_goal"]
    p_noncross = primary["p_ground_first"] + primary["p_no_reach"]
    summary = (
        f"Unconditional assigned mass   |   Wide {p_wide:.2%}     "
        f"No crossing {p_noncross:.2%}     Numerical failure {primary['p_failure']:.2%}     "
        f"Off-panel {clipped_mass:.2%}"
    )
    notes.text(.5, .09, summary, transform=notes.transAxes, ha="center", va="bottom",
               color="#374b5a", fontsize=9)
    detail = {"off_panel_probability": clipped_mass,
              "full_y_limits_m": [point * width for point in full_y],
              "full_z_limits_m": [point * width for point in full_z],
              "p_wide": p_wide, "p_noncross": p_noncross, "mode_displayed": mode is not None}
    return fig, grid, cells, width, detail


def figures(args):
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 10,
        "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 140,
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })
    case, protocol = read_json(CASE_PATH), read_json(PROTOCOL_PATH)
    scenario = protocol["scenario_id"]
    traces_path = args.primary / "traces.json"
    traces = read_json(traces_path)
    first, second = (read_json(folder / "forecast.json") for folder in (args.primary, args.repeat))
    key = (case["case_id"], args.model, scenario)
    if (args.run_id != protocol["run_id"] or any(config["input_run_id"] != args.run_id
        for config in (first, second)) or (traces["case_id"], traces["model_id"], traces["scenario_id"]) != key):
        raise ValueError("The forecasts or traces do not match the frozen run, case and model")
    if (first["seed"] != traces["forecast_seed"] or first["seed"] == second["seed"]
            or 2 * first["models"][args.model]["draw_budget"] != second["models"][args.model]["draw_budget"]):
        raise ValueError("The trace seed or public repeat budget differs from the frozen plan")
    if first["source_commit"] != second["source_commit"] or first["scenario_sha256"] != second["scenario_sha256"]:
        raise ValueError("The forecast and repeat use different source or scenario")
    prediction_paths = [folder / "predictions.csv" for folder in (args.primary, args.repeat)]
    results = []
    for prediction_file, config in zip(prediction_paths, (first, second)):
        if sha256(prediction_file) != config["predictions_sha256"]:
            raise ValueError("A supplied-shot prediction differs from its recorded hash")
        expected = {(case["case_id"], model, scenario) for model in config["models"]}
        summary = summarize_file(prediction_file, expected, protocol["decision"], case["goal"])
        results.append(next(row for row in summary if tuple(row[k] for k in
                            ("case_id", "model_id", "scenario_id")) == key))
    fig1 = f1(case, traces)
    fig2, grid, region, width, details = f2(case, *results, traces, prediction_paths[0])
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(traces_path, args.output / "F1-traces.json")
    rows = [{"y_min_m": f"{y*width:.12g}", "z_min_m": f"{z*width:.12g}", "cell_width_m": width,
             "probability_given_plane": grid[(y, z)], "region_95": int((y, z) in region)}
            for y, z in sorted(grid)]
    write_csv(args.output / "F2-plane-grid.csv", tuple(rows[0]), rows)
    f1_caption = (
        f"Figure F1. Supplied kick under the {args.model} nominal two-frame forecast. "
        "Filled circles mark release and observed ball centres. The shaded interval ends at the "
        f"{case['observations'][-1]['t_s']:.2f} s observation. The blue fan contains "
        f"{len(traces['fan'])} resolved draws selected systematically with trace seed {traces['trace_seed']}. "
        "Deterministic point-fit baselines share the same observations. Each trace ends at its first event."
    )
    mode_note = ("The star is the weighted Gaussian KDE mode conditional on entry "
                 "with bandwidth 0.05 m. It passed the independent repeat and 0.10 m bandwidth checks."
                 if details["mode_displayed"] else
                 "The entry-conditioned mode is unavailable or outside the repeat stability tolerance.")
    y_span = ", ".join(f"{value:g}" for value in details["full_y_limits_m"])
    z_span = ", ".join(f"{value:g}" for value in details["full_z_limits_m"])
    f2_caption = (
        f"Figure F2. {args.model} crossing distribution for the supplied kick under the nominal scenario. "
        "Positive Y denotes the positive y side of the specified frame, toward the kicker's left "
        "when facing the goal. The color scale gives the plane-conditioned probability in each 0.10 m square. "
        "The outline encloses the highest-mass cells of the 95% joint region, including cutoff ties. "
        "Symbols identify deterministic baseline crossings. The dashed rectangle is the one-radius "
        f"clearance proxy. {mode_note} The full panel spans Y=[{y_span}] m "
        f"and Z=[{z_span}] m. Off-panel mass {details['off_panel_probability']:.4%} "
        "uses the total assigned forecast weight."
    )
    manifest = []
    for asset, fig, caption, source, condition, statistic, units, hashes in (
        ("F1", fig1, f1_caption, "F1-traces.json", "resolved first-event trajectories",
         "observations, point-fit baselines and systematically sampled trajectories", "m",
         f"traces={sha256(traces_path)}"),
        ("F2", fig2, f2_caption, "summary.json; F2-plane-grid.csv", "plane arrival; centre entry for mode",
         "grid probability, joint 95% region and entry-conditioned KDE mode", "m; %",
         f"primary={first['predictions_sha256']}; repeat={second['predictions_sha256']}"),
    ):
        pdf, png, caption_file = f"{asset}.pdf", f"{asset}.png", f"{asset}_caption.md"
        fig.savefig(args.output / pdf, metadata={"CreationDate": None})
        fig.savefig(args.output / png, dpi=180)
        plt.close(fig)
        (args.output / caption_file).write_text(caption + "\n", encoding="utf-8")
        manifest.append(dict(asset_id=asset, run_id=args.run_id, version="v1", owner="WP3",
                             population="supplied kick", scenario_id=scenario, condition=condition,
                             statistic=statistic, units=units, source_artifact=source,
                             row_filters=f"case_id={case['case_id']}, model_id={args.model}",
                             pdf=pdf, png=png, caption=caption_file, source_hashes=hashes))
    write_csv(args.output / "figures_manifest.csv", FIGURE_FIELDS, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", required=True, type=Path)
    parser.add_argument("--repeat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", default="upc2026-wp3-v1")
    args = parser.parse_args()
    try:
        figures(args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
