"""Reduce immutable draw bundles to the WP3 per-case result contract."""

from collections import defaultdict
from itertools import groupby
from math import dist, fsum, isclose, isfinite

from figures.evidence import LEVELS, PLANE, cell
from validation.score_entry import FAILURE, PHYSICAL_EVENTS, read_rows

KEY = ("case_id", "model_id", "scenario_id")
FIELDS = (*KEY, "draw_id", "weight", "event", "t_s", "y_m", "z_m", "clearance_goal", "reason")
PROBABILITIES = ("p_reach", "p_goal", "p_clearance_goal", "p_ground_first", "p_no_reach")
QUANTILES = (0.025, 0.50, 0.975)


def number(value, field):
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"Nonfinite {field} in forecast")
    return result


def weighted_quantiles(values, mass):
    ordered = sorted(values)
    values_at_levels = []
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        while len(values_at_levels) < len(QUANTILES) and cumulative >= QUANTILES[len(values_at_levels)] * mass:
            values_at_levels.append(value)
    return values_at_levels


def highest_mass_grid(points, width, mass):
    weights_by_cell = defaultdict(list)
    for weight, _, y, z in points:
        weights_by_cell[cell(y, z, width)].append(weight)
    ordered = sorted(((fsum(weights), yz) for yz, weights in weights_by_cell.items()),
                     key=lambda item: (-item[0], item[1]))
    cumulative = 0.0
    levels = []
    cells = []
    for weight, ties in groupby(ordered, key=lambda item: item[0]):
        tied_cells = [yz for _, yz in ties]
        cumulative += weight * len(tied_cells)
        cells.extend(tied_cells)
        while len(levels) < len(LEVELS) and cumulative >= LEVELS[len(levels)] * mass:
            levels.append({"level": LEVELS[len(levels)], "n_cells": len(cells),
                           "area_m2": len(cells) * width ** 2})
        if len(levels) == len(LEVELS):
            break
    return {"method": "weighted highest-mass square cells, including cutoff ties",
            "origin_yz_m": (0, 0), "cell_width_m": width, "cells_in_descending_mass_order": cells,
            "levels": levels}


def conditional(points, condition, decision, total):
    mass = fsum(row[0] for row in points)
    ess = 1 / fsum((row[0] / mass) ** 2 for row in points) if mass else 0.0
    minimum = decision["minimum_conditional_effective_draws"]
    supported = ess >= minimum or isclose(ess, minimum, rel_tol=1e-12)
    diag = {"condition": condition, "count": len(points), "weight": mass / total,
            "ess": ess, "minimum_ess": minimum}
    if not supported:
        return None, dict(diag, reason="insufficient conditional support" if mass else "zero conditional mass")
    timed = [(time, weight) for weight, time, _, _ in points if time is not None]
    time_mass = fsum(weight for _, weight in timed)
    time_ess = 1 / fsum((weight / time_mass) ** 2 for _, weight in timed) if timed else 0
    return dict(
        diag, quantile_method="inverse weighted empirical CDF", quantile_levels=QUANTILES,
        t_s=weighted_quantiles(timed, time_mass)
        if time_ess >= minimum or isclose(time_ess, minimum, rel_tol=1e-12) else None,
        y_m=weighted_quantiles([(y, weight) for weight, _, y, _ in points], mass),
        z_m=weighted_quantiles([(z, weight) for weight, _, _, z in points], mass),
        timed_count=len(timed), timed_weight=time_mass / total, timed_ess=time_ess,
        joint_region=highest_mass_grid(points, decision["joint_region_grid_m"], mass),
    ), diag


def grid_mode(points, width, total):
    by_cell = defaultdict(list)
    for weight, _, y, z in points:
        by_cell[cell(y, z, width)].append(weight)
    cell_masses = {key: fsum(weights) for key, weights in by_cell.items()}
    highest = max(cell_masses.values())
    winners = [key for key, weight in cell_masses.items() if weight == highest]
    if len(winners) != 1:
        return None, {"reason": "multiple maximum-mass cells"}
    y, z = winners[0]
    return [(y + 0.5) * width, (z + 0.5) * width], {
        "estimator": "centre of unique highest-mass entry-conditioned square cell",
        "cell_width_m": width, "origin_yz_m": [0, 0], "contributing_count": len(points),
        "contributing_weight": fsum(row[0] for row in points) / total,
        "mode_cell_mass_given_entry": highest / fsum(row[0] for row in points),
        "numerical_stability": "not independently assessed",
    }


def kde_mode(points, bounds, total):
    """Use the public-shot grid and bandwidths for the entry-conditioned mode."""
    import numpy as np

    weights, _, y, z = zip(*points)
    weights = np.asarray(weights)
    grid_y = np.arange(bounds["y_min_m"] + 0.01, bounds["y_max_m"], 0.02)
    grid_z = np.arange(bounds["z_min_m"] + 0.01, bounds["z_max_m"], 0.02)

    def peak(bandwidth):
        kernel_y = np.exp(-0.5 * ((grid_y[:, None] - np.asarray(y)) / bandwidth) ** 2)
        kernel_z = np.exp(-0.5 * ((grid_z[:, None] - np.asarray(z)) / bandwidth) ** 2)
        surface = (kernel_y * weights) @ kernel_z.T
        i, j = np.unravel_index(np.argmax(surface), surface.shape)
        return [float(grid_y[i]), float(grid_z[j])]

    estimate, sensitivity = peak(0.05), peak(0.10)
    return estimate, {
        "estimator": "weighted isotropic Gaussian kernel density on the goal interior",
        "cell_width_m": 0.02, "bandwidth_m": 0.05,
        "contributing_count": len(points), "contributing_weight": fsum(weights) / total,
        "bandwidth_sensitivity": {"bandwidth_m": 0.10, "mode_yz_m": sensitivity,
                                  "distance_from_primary_m": dist(estimate, sensitivity)},
        "numerical_stability": "not independently assessed",
    }


def summarize_bundle(key, draws, decision, provides_time, goal_bounds=None):
    parts = defaultdict(list)
    reasons = defaultdict(list)
    plane = []
    goal = []
    clearance = []
    ids = set()
    for draw in draws:
        draw_id = draw["draw_id"]
        event = draw["event"]
        weight = number(draw["weight"], "weight")
        if (not draw_id.strip() or draw_id in ids or event not in PHYSICAL_EVENTS | {FAILURE}
                or not 0 <= weight <= 1):
            raise ValueError(f"Invalid forecast row for {key!r}")
        ids.add(draw_id)
        parts[event].append(weight)
        time = number(draw["t_s"], "time") if draw["t_s"] else None
        if time is not None and (time < 0 or not provides_time):
            raise ValueError(f"Invalid forecast time for {key!r}")
        if event in PLANE:
            y = number(draw["y_m"], "plane y")
            z = number(draw["z_m"], "plane z")
            if draw["clearance_goal"] not in ("0", "1") or (
                draw["clearance_goal"] == "1" and event != "PLANE_GOAL"
            ):
                raise ValueError(f"Invalid clearance label for {key!r}")
            if weight:
                point = (weight, time, y, z)
                plane.append(point)
                if event == "PLANE_GOAL":
                    goal.append(point)
                if draw["clearance_goal"] == "1":
                    clearance.append(weight)
        elif any(draw[field] for field in ("y_m", "z_m", "clearance_goal")):
            raise ValueError(f"Non-plane forecast has plane coordinates or clearance for {key!r}")
        if event == FAILURE:
            reasons[draw["reason"] or "unrecorded reason"].append(weight)
    mass = {event: fsum(weights) for event, weights in parts.items()}
    total = fsum(mass.values())
    if not isclose(total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"Forecast weights do not sum to one for {key!r}")
    failure = mass.get(FAILURE, 0.0) / total
    goal_mass = mass.get("PLANE_GOAL", 0.0)
    reach_mass = fsum((goal_mass, mass.get("PLANE_WIDE", 0.0)))
    probs = dict(p_reach=reach_mass / total, p_goal=goal_mass / total,
                 p_clearance_goal=fsum(clearance) / total,
                 p_ground_first=mass.get("GROUND_FIRST", 0.0) / total,
                 p_no_reach=mass.get("NO_REACH", 0.0) / total)
    plane_intervals, plane_diagnostics = conditional(plane, "plane", decision, total)
    goal_intervals, goal_diagnostics = conditional(goal, "goal", decision, total)
    if goal_intervals and goal_bounds:
        mode, mode_details = kde_mode(goal, goal_bounds, total)
    elif goal_intervals:
        mode, mode_details = grid_mode(goal, decision["joint_region_grid_m"], total)
    else:
        mode, mode_details = None, {"reason": goal_diagnostics["reason"]}
    return dict(zip(KEY, key), **probs, p_failure=failure,
                p_goal_given_reach=goal_mass / reach_mass if reach_mass else None,
                probability_bounds={field: (value, min(1.0, value + failure)) for field, value in probs.items()},
                plane_intervals=plane_intervals, goal_intervals=goal_intervals, entry_mode_yz_m=mode,
                entry_mode=mode_details,
                diagnostics=dict(draw_count=len(ids),
                                 ess=1 / fsum((weight / total) ** 2 for values in parts.values() for weight in values),
                                 maximum_weight=max(weight / total for values in parts.values() for weight in values),
                                 failure_reasons={reason: {"count": len(weights), "weight": fsum(weights) / total}
                                                  for reason, weights in sorted(reasons.items())},
                                 plane=plane_diagnostics, goal=goal_diagnostics))


def summarize_file(draws_path, expected, decision, goal_bounds=None):
    """Read one contiguous case/model/scenario group at a time."""
    found = {}
    for key, draws in groupby(read_rows(draws_path, FIELDS), key=lambda row: tuple(row[field] for field in KEY)):
        if key not in expected or key in found:
            raise ValueError(f"Unexpected or noncontiguous forecast group {key!r}")
        found[key] = summarize_bundle(key, draws, decision, provides_time=key[1] != "B2", goal_bounds=goal_bounds)
    for key in sorted(expected):
        if key not in found:
            missing = dict(zip(FIELDS, (*key, "missing", "1", FAILURE, "", "", "", "", "missing forecast group")))
            found[key] = summarize_bundle(key, [missing], decision, provides_time=key[1] != "B2")
        yield found[key]


def compare_kick(primary, repeat):
    """Apply the registered public-shot repeat tolerances to reported statistics."""
    probability_deltas = {key: abs(primary[key] - repeat[key]) for key in (*PROBABILITIES, "p_failure")}
    interval_deltas = {}
    interval_missing = []
    for condition in ("plane_intervals", "goal_intervals"):
        a, b = primary[condition], repeat[condition]
        if a is None or b is None:
            interval_missing.append(condition)
            continue
        for coordinate in ("y_m", "z_m"):
            interval_deltas[f"{condition}.{coordinate}"] = max(
                abs(a[coordinate][i] - b[coordinate][i]) for i in (0, -1)
            )
    a, b = primary["entry_mode_yz_m"], repeat["entry_mode_yz_m"]
    mode_distance = dist(a, b) if a is not None and b is not None else None
    sensitivity = primary["entry_mode"].get("bandwidth_sensitivity", {})
    repeat_sensitivity = repeat["entry_mode"].get("bandwidth_sensitivity", {})
    maximum_bandwidth_distance = max(sensitivity.get("distance_from_primary_m", 0),
                                     repeat_sensitivity.get("distance_from_primary_m", 0))
    return {
        "probability_absolute_deltas": probability_deltas,
        "maximum_interval_endpoint_deltas_m": interval_deltas,
        "unavailable_intervals": interval_missing,
        "entry_mode_distance_m": mode_distance,
        "maximum_bandwidth_mode_distance_m": maximum_bandwidth_distance,
        "probabilities_stable": max(probability_deltas.values()) <= 0.01,
        "intervals_stable": not interval_missing and max(interval_deltas.values(), default=0) <= 0.03,
        "entry_mode_stable": mode_distance is not None and max(mode_distance, maximum_bandwidth_distance) <= 0.10,
    }
