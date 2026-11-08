"""Summarize public predictions and render draft WP2 figures."""

import argparse
import csv
import json
from pathlib import Path
from dataclasses import asdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from physics import SolverConfig, load_case, solve
from .baseline import CASE_PATH
from .m2 import sample

MINIMUM_CONDITIONAL_ESS = 100


def mode_repeat_status(first, second, tolerance=.10):
    points = [s.get(k) for s in (first, second)
              for k in ("entry_mode_yz_m", "entry_mode_check_yz_m")]
    if any(p is None for p in points):
        return dict(status="unavailable", recommended_mode_yz_m=None, estimates_yz_m=points)
    primary, alternate, repeat, repeat_alternate = points
    distances = [float(np.linalg.norm(np.asarray(a) - b)) for a, b in
                 ((primary, repeat), (primary, alternate), (repeat, repeat_alternate))]
    stable = max(distances) <= tolerance
    return dict(status="stable" if stable else "unstable", tolerance_m=tolerance,
                repeat_shift_m=distances[0], bandwidth_shifts_m=distances[1:],
                estimates_yz_m=points, recommended_mode_yz_m=primary if stable else None)


def grid_region(points, weights, width=.1):
    """Frozen highest-mass cells, origin anchored, including cutoff ties."""
    cells = {}
    for point, weight in zip(points, weights / weights.sum()):
        key = tuple(int(x) for x in np.floor(point / width))
        cells[key] = cells.get(key, 0.) + float(weight)
    ordered = sorted(cells, key=lambda key: (-cells[key], key))
    masses = np.array([cells[key] for key in ordered])
    regions = []
    for level in (.5, .8, .95):
        index = min(int(np.searchsorted(np.cumsum(masses), level)), len(masses)-1)
        cutoff = masses[index]
        selected = [key for key in ordered if cells[key] >= cutoff]
        regions.append(dict(level=level, cells=selected, mass=sum(cells[key] for key in selected)))
    return dict(method="weighted highest-mass square cells including cutoff ties",
                width_m=width, origin_yz_m=[0, 0], regions=regions)


def quantile(values, weights, levels):
    order = np.argsort(values)
    return np.interp(levels, np.cumsum(weights[order]) / weights.sum(), values[order])


def cloud(rows, condition):
    subset = [r for r in rows if condition(r)]
    points = np.array([[float(r[k]) for k in ("y_m", "z_m")] for r in subset])
    weights = np.array([float(r["weight"]) for r in subset])
    return points, weights


def ellipse(points, weights):
    center = np.average(points, weights=weights, axis=0)
    covariance = np.cov(points.T, aweights=weights, ddof=0)
    eigenvalues, axes = np.linalg.eigh(covariance)
    if eigenvalues[0] <= 0:
        return None
    distances = np.sum(((points - center) @ axes)**2 / eigenvalues, axis=1)
    levels = quantile(distances, weights, [0.5, 0.8, 0.95])
    return center, axes, eigenvalues, levels


def mode(points, weights, case, bandwidth):
    y = np.arange(case.y_min + .01, case.y_max, .02)
    z = np.arange(case.z_min + .01, case.z_max, .02)
    # Rectangular truncation has a constant normalizer on the search domain.
    ky = np.exp(-.5 * ((y[:, None] - points[:, 0]) / bandwidth)**2)
    kz = np.exp(-.5 * ((z[:, None] - points[:, 1]) / bandwidth)**2)
    i, j = np.unravel_index(np.argmax((ky * weights) @ kz.T), (len(y), len(z)))
    return [float(y[i]), float(z[j])]


def summarize(rows, case):
    total = sum(float(r["weight"]) for r in rows)
    if not np.isclose(total, 1):
        raise ValueError("Prediction group weights must sum to one.")
    mass = {event: sum(float(r["weight"]) for r in rows if r["event"] == event) / total
            for event in ("PLANE_GOAL", "PLANE_WIDE", "GROUND_FIRST", "NO_REACH", "NUMERICAL_FAILURE")}
    reach = mass["PLANE_GOAL"] + mass["PLANE_WIDE"]
    clearance = sum(float(r["weight"]) for r in rows if r["clearance_goal"] == "1") / total
    if not (np.isclose(sum(mass.values()), 1) and clearance <= mass["PLANE_GOAL"] <= reach):
        raise ValueError("Inconsistent first-event accounting.")
    summary = dict(p_reach=reach, p_goal=mass["PLANE_GOAL"], p_clearance_goal=clearance,
                   p_ground_first=mass["GROUND_FIRST"], p_no_reach=mass["NO_REACH"],
                   p_failure=mass["NUMERICAL_FAILURE"], p_plane_wide=mass["PLANE_WIDE"],
                   p_goal_given_reach=mass["PLANE_GOAL"] / reach if reach else None)
    summary["probability_bounds"] = {
        k: [v, min(1, v + summary["p_failure"])] for k, v in summary.copy().items()
        if k in ("p_reach", "p_goal", "p_clearance_goal", "p_ground_first", "p_no_reach")
    }
    for label, events in (("plane", ("PLANE_GOAL", "PLANE_WIDE")), ("goal", ("PLANE_GOAL",))):
        subset = [r for r in rows if r["event"] in events]
        points, weights = cloud(rows, lambda r: r["event"] in events)
        ess = weights.sum()**2 / (weights @ weights) if len(weights) and weights.any() else 0
        stats = dict(condition=label, count=len(weights), weight=float(weights.sum()), ess=float(ess))
        summary[f"{label}_intervals"] = stats
        if ess < MINIMUM_CONDITIONAL_ESS and not np.isclose(ess, MINIMUM_CONDITIONAL_ESS, rtol=1e-12):
            stats["reason"] = "conditional_ess_below_100"
            continue
        stats["quantile_levels"] = [.025, .5, .975]
        for key in ("t_s", "y_m", "z_m"):
            if all(r[key] for r in subset):
                stats[key] = quantile(np.array([float(r[key]) for r in subset]),
                                      weights, stats["quantile_levels"]).tolist()
        stats["joint_region"] = grid_region(points, weights)
        if label == "goal":
            summary["entry_mode_yz_m"] = mode(points, weights, case, .05)
            summary["entry_mode_check_yz_m"] = mode(points, weights, case, .10)
            summary["entry_mode_method"] = dict(kernel="Gaussian", bandwidth_m=.05,
                grid_m=.02, boundary="density restricted to goal interior", tie="first y then z",
                bandwidth_check_m=.10, minimum_conditional_ess=100)
            summary["entry_mode_bandwidth_stable"] = bool(np.linalg.norm(
                np.array(summary["entry_mode_yz_m"]) - summary["entry_mode_check_yz_m"]) <= .10)
        if "t_s" in stats:
            stats["time_after_last_frame_s"] = [t - case.times[-1] for t in stats["t_s"]]
    summary.setdefault("entry_mode_yz_m", None)
    return summary


def save(fig, output, name):
    for extension in ("pdf", "png"):
        fig.savefig(output / f"{name}.{extension}", dpi=170, bbox_inches="tight")
    plt.close(fig)


def figure2(output, case, rows, summary):
    points, weights = cloud(rows, lambda r: r["event"].startswith("PLANE_"))
    fig, ax = plt.subplots(figsize=(9, 4))
    y = np.linspace(min(case.y_min - .3, points[:, 0].min()), max(case.y_max + .3, points[:, 0].max()), 95)
    z = np.linspace(0, max(case.z_max + .35, points[:, 1].max()), 48)
    histogram, _, _ = np.histogram2d(*points.T, bins=[y, z], weights=weights / weights.sum() * 100)
    _, _, _, mesh = ax.hist2d(*points.T, bins=[y, z], weights=weights / weights.sum() * 100,
                             cmap="Blues", cmin=1e-8)
    fig.colorbar(mesh, ax=ax, label="Probability per grid cell (%)")
    ax.add_patch(Rectangle((case.y_min, case.z_min), case.y_max-case.y_min, case.z_max-case.z_min,
                           fill=False, edgecolor="black", linewidth=1.5))
    r = case.radius
    ax.add_patch(Rectangle((case.y_min+r, r), case.y_max-case.y_min-2*r, case.z_max-2*r,
                           fill=False, edgecolor="black", linestyle="--"))
    joint = summary["plane_intervals"].get("joint_region")
    if joint is not None:
        for index, (iy, iz) in enumerate(joint["regions"][-1]["cells"]):
            ax.add_patch(Rectangle((iy*.1, iz*.1), .1, .1, fill=False,
                         edgecolor="tab:orange", linewidth=.4,
                         label="Joint 95% grid region | plane" if index == 0 else None))
    for model, marker in zip(("B0", "B1", "B2"), ("x", "+", "1")):
        event = solve(model, case).event
        if event.y_m is not None:
            ax.scatter(event.y_m, event.z_m, marker=marker, label=model)
    recommendation = summary.get("entry_mode_assessment", {}).get("recommended_mode_yz_m")
    if recommendation is not None:
        ax.scatter(*recommendation, marker="*", c="black", label="Mode | goal")
    off = summary["p_reach"] * max(0, 1 - histogram.sum()/100)
    summary["f2_off_panel_weight"] = off
    ax.set(xlabel="Y (m)", ylabel="Z (m)", aspect="equal",
           title="Public M2 reference · distribution conditional on plane arrival")
    ax.legend(loc="upper left", fontsize=8)
    fig.text(.14, .01, f"Wide {summary['p_plane_wide']:.2%}   No crossing "
             f"{summary['p_ground_first']+summary['p_no_reach']:.2%}   "
             f"Failure {summary['p_failure']:.2%}   Off panel {off:.2%}")
    save(fig, output, "F2")


def figure3(output, case):
    sigma = .01
    draws, _, _ = sample(case, sigma, 400, 2028, "M2", None, 0, .27, .22)
    best = max(draws, key=lambda d: d[1])[2]
    vector = np.array([*best["v0"], best["cd"], best["cy"], best["cz"]])
    scales = np.array([40/np.sqrt(12), 40/np.sqrt(12), 20/np.sqrt(12), .14, .22, .22])

    def solve_vector(theta, trace=False):
        return solve("M2", case, dict(v0=theta[:3], cd=theta[3], cy=theta[4], cz=theta[5]),
                     include_trace=trace)

    def jacobian(step):
        columns = []
        for delta in np.diag(step * scales):
            upper = np.asarray(solve_vector(vector + delta).observations).ravel()
            lower = np.asarray(solve_vector(vector - delta).observations).ravel()
            columns.append((upper - lower) / (2 * step * sigma))
        return np.column_stack(columns)

    matrix = jacobian(1e-4)
    u, _ = np.linalg.qr(matrix[:, :3])
    spectrum = np.linalg.svd(matrix, compute_uv=False)
    aero = np.linalg.svd(matrix[:, 3:] - u @ (u.T @ matrix[:, 3:]), compute_uv=False)
    eligible = []
    for _, _, p in draws:
        fit = solve("M2", case, p)
        error = np.linalg.norm((np.asarray(fit.observations) - case.observations) / sigma)
        if error <= 2.5 and fit.event.z_m is not None:
            eligible.append((fit.event.z_m, p, error))
    eligible.sort(key=lambda d: d[0])
    fig, (left, right) = plt.subplots(1, 2, figsize=(9, 3.8))
    left.semilogy(range(1, 7), spectrum, "o-", label="Full")
    left.semilogy(range(1, 4), aero, "s--", label="Aerodynamics | velocity projected out")
    left.set(xlabel="Singular value index", ylabel="Scaled singular value")
    left.legend(fontsize=8)
    pairs = []
    if eligible:
        for label, (_, p, error) in zip(("Low crossing", "High crossing"), (eligible[0], eligible[-1])):
            fit = solve("M2", case, p, include_trace=True)
            refined = solve("M2", case, p, SolverConfig(max_step_s=.005))
            right.plot([t.x_m for t in fit.trace], [t.z_m for t in fit.trace], label=f"{label}: {fit.event.event}")
            pairs.append(dict(parameters=p, whitened_residual_norm=error, event=asdict(fit.event),
                              half_step_event=asdict(refined.event),
                              trace=[asdict(point) for point in fit.trace]))
    right.scatter([q[0] for q in case.observations], [q[2] for q in case.observations],
                  c="black", label="Shared observations")
    right.axvline(case.goal_x, color="grey", linestyle=":")
    right.axhline(case.z_max, color="grey", linestyle=":")
    right.set(xlabel="X (m)", ylabel="Z (m)")
    right.legend(fontsize=7)
    fig.tight_layout()
    save(fig, output, "F3")
    return dict(sigma_m=sigma, parameter_scales=scales.tolist(), parameters=vector.tolist(),
                parameter_order=["vx0", "vy0", "vz0", "cd", "cy", "cz"],
                bounds={"vx0": [8, 48], "vy0": [-20, 20], "vz0": [0, 20],
                        "cd": [.08, .55], "transverse_radius": .55},
                observed_frames_m=case.observations, times_s=case.times,
                singular_values=spectrum.tolist(), projected_aero_singular_values=aero.tolist(),
                derivative_step_max_change=float(np.max(np.abs(matrix - jacobian(5e-5)))),
                seed=2028, proposals=400, residual_norm_limit=2.5, eligible=len(eligible), pair=pairs)


def figure4(output, t2):
    fig, (left, right, lateral) = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    measurement = [("sigma5", 5), ("m2", 10), ("sigma20", 20)]
    left.plot([x for _, x in measurement], [100*t2[k]["p_goal"] for k, _ in measurement], "o-", label="Gaussian")
    left.scatter(10, 100*t2["rounded"]["p_goal"], marker="D", label="Gaussian + rounding")
    if "rounding" in t2:
        left.scatter(0, 100*t2["rounding"]["p_goal"], marker="s", label="Rounding only")
    left.set(xlabel="Coordinate error SD (mm)", ylabel="Goal probability (%)")
    left.legend(fontsize=8)
    variants = ("m2", "trionda", "jabulani", "wind", "transverse-prior")
    labels = ("M2 reference", "Trionda", "Jabulani", "Wind +3 m/s Y", "Transverse prior SD 0.12")
    for ax, coordinate in ((right, "z_m"), (lateral, "y_m")):
        for i, key in enumerate(variants):
            interval = t2[key]["plane_intervals"].get(coordinate)
            if interval is not None:
                lo, median, hi = interval
                ax.errorbar(median, i, xerr=[[median-lo], [hi-median]], fmt="o")
    right.set(yticks=range(len(variants)), yticklabels=labels, xlabel="Crossing Z (m) | plane")
    lateral.set(yticks=range(len(variants)), yticklabels=[], xlabel="Crossing Y (m) | plane")
    right.axvline(2.44, color="grey", linestyle=":")
    save(fig, output, "F4")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--repeat", type=Path)
    parser.add_argument("--mode-audit", type=Path,
                        help="Additional same-scenario independent stability evidence")
    args = parser.parse_args()
    case = load_case(CASE_PATH)
    t2 = {}
    for path in sorted(args.run.glob("*/predictions.csv")):
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        key = path.parent.name
        stats = summarize(rows, case)
        diagnostics = json.loads(path.with_name("diagnostics.json").read_text(encoding="utf-8"))
        stats["diagnostics"] = diagnostics
        stats["draft_sampling_flags"] = [
            flag for flag, triggered in (
                ("ess_below_10_percent_of_attempts", diagnostics["ess"] < .1 * diagnostics["attempted"]),
                ("max_weight_above_1_percent", diagnostics["max_weight"] > .01),
            ) if triggered
        ]
        if key == "m2":
            m2_rows = rows
        t2[key] = stats
    if args.repeat:
        with (args.repeat / "predictions.csv").open(encoding="utf-8", newline="") as stream:
            repeat = summarize(list(csv.DictReader(stream)), case)
        t2["m2"]["independent_repeat"] = {
            "diagnostics": json.loads((args.repeat / "diagnostics.json").read_text(encoding="utf-8")),
            "p_goal": repeat["p_goal"], "p_clearance_goal": repeat["p_clearance_goal"],
            "plane_intervals": repeat["plane_intervals"], "entry_mode_yz_m": repeat["entry_mode_yz_m"],
        }
        first_mode = t2["m2"]["entry_mode_yz_m"]
        second_mode = repeat["entry_mode_yz_m"]
        shift = (float(np.linalg.norm(np.array(first_mode) - second_mode))
                 if first_mode is not None and second_mode is not None else None)
        t2["m2"]["independent_repeat"]["mode_shift_m"] = shift
        t2["m2"]["independent_repeat"]["mode_stable"] = shift is not None and shift <= .10
        t2["m2"]["entry_mode_assessment"] = mode_repeat_status(t2["m2"], repeat)
    else:
        t2["m2"]["entry_mode_assessment"] = mode_repeat_status(t2["m2"], {})
    if args.mode_audit:
        audit = json.loads(args.mode_audit.read_text(encoding="utf-8"))
        additional = mode_repeat_status(audit["first"], audit["repeat"])
        t2["m2"]["additional_mode_assessment"] = additional
        if additional["status"] != "stable":
            t2["m2"]["entry_mode_assessment"].update(
                status=additional["status"], recommended_mode_yz_m=None)
    figure2(args.run, case, m2_rows, t2["m2"])
    figure4(args.run, t2)
    f3 = figure3(args.run, case)
    (args.run / "F3-data.json").write_text(json.dumps(f3, indent=2) + "\n", encoding="utf-8")
    (args.run / "T2.json").write_text(json.dumps(t2, indent=2) + "\n", encoding="utf-8")
    with (args.run / "figures_manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["figure_id", "run_id", "source", "summary_keys", "condition",
                         "display_units", "owner", "pdf", "preview", "caption"])
        for name, source, keys, condition, units, caption in (
            ("F2", "T2.json;m2/predictions.csv", "m2.plane_intervals;m2.entry_mode_yz_m",
             "plane for histogram and joint region; goal for mode", "m;%",
             "Public kick under M2 and 10 mm Gaussian errors. The histogram and joint region "
             "condition on plane arrival. The mode conditions on the ball center entering the goal."),
            ("F3", "F3-data.json", "singular_values;projected_aero_singular_values;pair",
             "public M2, residual norm at most 2.5 for pair", "dimensionless;m",
             "Public M2 local sensitivities and two candidate trajectories compatible with the same "
             "early observations under the stated 10 mm error scale."),
            ("F4", "T2.json", "p_goal;plane_intervals", "all draws for goal; plane for intervals", "%;mm;m",
             "Each public scenario was refitted to both frames. The left panel gives unconditional "
             "goal probabilities. The other panels give conditional 95% crossing intervals."),
        ):
            writer.writerow([name, "wp2-public-draft", source, keys, condition, units, "b_inference",
                             f"{name}.pdf", f"{name}.png", caption])


if __name__ == "__main__":
    main()
