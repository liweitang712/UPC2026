"""Aggregate case-level evidence for WP3 figures F5 and F6."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from math import floor, fsum, isclose, isfinite, sqrt
from random import Random
from statistics import mean, quantiles

from validation.score_entry import FAILURE, PHYSICAL_EVENTS, by_case, read_rows

PLANE = {"PLANE_GOAL", "PLANE_WIDE"}
LEVELS = (0.50, 0.80, 0.95)
DISPLAY_GROUPS = {
    "matched": ("matched",),
    "single_factor": ("wind", "drag", "lift", "sensor"),
    "combined": ("combined",),
    "challenge": ("challenge",),
}
DRAW_FIELDS = ("case_id", "model_id", "scenario_id", "draw_id", "weight", "event", "y_m", "z_m")
STATUS_FIELDS = ("case_id", "model_id", "scenario_id", "point_status")


@dataclass(frozen=True)
class Forecast:
    technical: bool = True
    resolved: bool = False
    entry: float | None = None
    arrival: float | None = None
    hits: tuple | None = None
    squared_error: float | None = None


@dataclass(frozen=True)
class Shot:
    stratum: str
    event: str
    forecasts: dict
    point_status: dict


def cell(y, z, width):
    return floor(y / width), floor(z / width)


def summarize_draws(draws, true_point, decision):
    """Keep event resolution separate from support for a conditional region."""
    seen, weights = set(), defaultdict(list)
    plane = []
    for row in draws:
        draw_id, event = row["draw_id"], row["event"]
        try:
            weight = float(row["weight"])
        except ValueError:
            return Forecast()
        if (not draw_id.strip() or draw_id in seen or event not in PHYSICAL_EVENTS | {FAILURE}
                or not isfinite(weight) or not 0 <= weight <= 1):
            return Forecast()
        seen.add(draw_id)
        weights[event].append(weight)
        if event in PLANE and weight:
            try:
                y, z = float(row["y_m"]), float(row["z_m"])
            except ValueError:
                return Forecast()
            if not (isfinite(y) and isfinite(z)):
                return Forecast()
            if true_point is not None:
                plane.append((weight, y, z))
    mass = {event: fsum(parts) for event, parts in weights.items()}
    total = fsum(mass.values())
    if not isclose(total, 1, abs_tol=1e-9, rel_tol=0):
        return Forecast()
    goal = mass.get("PLANE_GOAL", 0)
    crossing = goal + mass.get("PLANE_WIDE", 0)
    failure = mass.get(FAILURE, 0)
    has_resolved = any(mass.get(event, 0) > 0 for event in PHYSICAL_EVENTS)
    entry = goal / total if not failure else None
    arrival = crossing / total if not failure else None
    summary = Forecast(bool(failure), has_resolved, entry, arrival)
    if not plane:
        return summary
    # An equal-weight ESS can land one rounding unit below the integer.
    ess = 1 / fsum((w / crossing) ** 2 for w, _, _ in plane)
    minimum = decision["minimum_conditional_effective_draws"]
    if ess < minimum and not isclose(ess, minimum, rel_tol=1e-12):
        return summary
    width = decision["joint_region_grid_m"]
    cells = defaultdict(list)
    for w, y, z in plane:
        cells[cell(y, z, width)].append(w)
    masses = {key: fsum(parts) for key, parts in cells.items()}
    true_mass = masses.get(cell(*true_point, width), 0)
    heavier = fsum(mass for mass in masses.values() if mass > true_mass)
    hits = tuple(true_mass > 0 and heavier < level * crossing for level in LEVELS)
    y_hat = fsum(w * y for w, y, _ in plane) / crossing
    z_hat = fsum(w * z for w, _, z in plane) / crossing
    distance_squared = (y_hat - true_point[0]) ** 2 + (z_hat - true_point[1]) ** 2
    return Forecast(bool(failure), has_resolved, entry, arrival, hits, distance_squared)


def load_shots(cases_path, truth_path, draws_path, status_path, models, protocol):
    cases = by_case(read_rows(cases_path, ("case_id", "split", "stratum", "scenario_id")), "cases")
    truth = by_case(read_rows(truth_path, ("case_id", "event", "y_m", "z_m")), "truth")
    strata = set(protocol["core_strata"]) | {protocol["challenge_stratum"]}
    if not cases or cases.keys() != truth.keys():
        raise ValueError("Blind cases and truth must have exactly the same case IDs")
    for row in cases.values():
        if (row["split"] != "blind" or row["stratum"] not in strata
                or row["scenario_id"] != protocol["scenario_id"] or row["case_id"] == "upc2026-b"):
            raise ValueError("Unexpected case, split, stratum, or scenario in blind evidence")

    def bundle_key(row):
        key = row["case_id"], row["model_id"]
        if (key[0] not in cases or key[1] not in models
                or row["scenario_id"] != cases[key[0]]["scenario_id"]):
            raise ValueError(f"Unexpected forecast key {key!r}")
        return key

    status = {}
    for row in read_rows(status_path, STATUS_FIELDS):
        key = bundle_key(row)
        value = row["point_status"]
        if key in status or value not in ("available", "abstained"):
            raise ValueError(f"Duplicate or invalid point status for {key!r}")
        status[key] = value

    points = {}
    for case_id, row in truth.items():
        if row["event"] not in PHYSICAL_EVENTS | {FAILURE}:
            raise ValueError(f"Invalid truth event for {case_id!r}")
        if row["event"] in PLANE:
            point = float(row["y_m"]), float(row["z_m"])
            if not all(map(isfinite, point)):
                raise ValueError(f"Invalid truth crossing for {case_id!r}")
            points[case_id] = point

    forecasts = {}
    for key, draws in groupby(read_rows(draws_path, DRAW_FIELDS), bundle_key):
        if key in forecasts:
            raise ValueError(f"Draw rows must be contiguous for {key!r}")
        forecasts[key] = summarize_draws(draws, points.get(key[0]), protocol["decision"])
    for key, forecast in forecasts.items():
        if forecast.resolved and key not in status:
            raise ValueError(f"Missing locked point status for {key!r}")

    return [
        Shot(row["stratum"], truth[case_id]["event"],
             {model: forecasts.get((case_id, model), Forecast()) for model in models},
             {model: status.get((case_id, model)) for model in models})
        for case_id, row in cases.items()
    ]


def wilson(successes, count):
    if not count:
        return None, None
    z = 1.959963984540054
    p = successes / count
    denominator = 1 + z ** 2 / count
    center = (p + z ** 2 / (2 * count)) / denominator
    half_width = z * sqrt(p * (1 - p) / count + z ** 2 / (4 * count ** 2)) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def reliability_rows(shots, group, model, bins, minimum):
    exact = [shot for shot in shots if shot.forecasts[model].entry is not None]
    for target, events in (("entry", {"PLANE_GOAL"}), ("arrival", PLANE)):
        by_bin = [[] for _ in range(bins)]
        for shot in exact:
            p = getattr(shot.forecasts[model], target)
            by_bin[min(int(p * bins), bins - 1)].append((p, shot.event in events))
        for index, values in enumerate(by_bin):
            n = len(values)
            row = dict(group=group, model=model, target=target, bin_lo=index / bins,
                       bin_hi=(index + 1) / bins, n_truth=len(shots), n_exact=len(exact), n=n,
                       mean_forecast=None, observed_rate=None, lo=None, hi=None)
            if n >= minimum:
                successes = sum(outcome for _, outcome in values)
                lo, hi = wilson(successes, n)
                row.update(mean_forecast=mean(p for p, _ in values), observed_rate=successes / n,
                           lo=lo, hi=hi)
            yield row


def coverage_rows(shots, group, model):
    hits = [shot.forecasts[model].hits for shot in shots if shot.forecasts[model].hits is not None]
    n = len(hits)
    for index, level in enumerate(LEVELS):
        covered = sum(hit[index] for hit in hits)
        lo, hi = wilson(covered, n)
        yield dict(group=group, model=model, nominal=level, n_truth_plane=len(shots), n_available=n,
                   n_covered=covered, observed=covered / n if n else None, lo=lo, hi=hi)


def paired_rmse(shots, group, models, decision, rng):
    selected, comparator = models
    pairs = [(shot.forecasts[selected].squared_error, shot.forecasts[comparator].squared_error)
             for shot in shots]
    common = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(common)
    row = dict(group=group, selected=selected, comparator=comparator, n_truth_plane=len(shots),
               n_selected=sum(a is not None for a, _ in pairs),
               n_comparator=sum(b is not None for _, b in pairs), n_paired=n,
               selected_rmse=None, comparator_rmse=None, delta=None, lo=None, hi=None)
    if n < decision["minimum_paired_truth_plane_cases"]:
        return row

    def rmse_pair(data):
        a, b = zip(*data)
        return sqrt(mean(a)), sqrt(mean(b))

    a, b = rmse_pair(common)
    differences = []
    for _ in range(decision["bootstrap_replicates"]):
        x, y = rmse_pair(rng.choices(common, k=n))
        differences.append(x - y)
    bounds = quantiles(differences, n=40, method="inclusive")
    row.update(selected_rmse=a, comparator_rmse=b, delta=a - b, lo=bounds[0], hi=bounds[-1])
    return row


def aggregate(shots, models, protocol):
    decision = protocol["decision"]
    strata = (*protocol["core_strata"], protocol["challenge_stratum"])
    groups = {key: (key,) for key in strata}
    groups["single_factor"] = DISPLAY_GROUPS["single_factor"]
    reliability, failure, coverage, comparisons = [], [], [], []
    rng = Random(decision["bootstrap_seed"])
    for group, members in groups.items():
        eligible = [shot for shot in shots if shot.stratum in members and shot.event != FAILURE]
        plane = [shot for shot in eligible if shot.event in PLANE]
        for model in models:
            reliability.extend(reliability_rows(eligible, group, model, decision["reliability_bin_count"],
                                               decision["minimum_reliability_bin_cases"]))
            coverage.extend(coverage_rows(plane, group, model))
            known = [shot.point_status[model] for shot in eligible if shot.forecasts[model].resolved]
            failure.append(dict(group=group, model=model, n_truth=len(eligible),
                                n_technical=sum(shot.forecasts[model].technical for shot in eligible),
                                n_entirely_invalid=sum(not shot.forecasts[model].resolved for shot in eligible),
                                n_point_assessed=len(known), n_abstained=known.count("abstained")))
        if group in strata:
            comparisons.append(paired_rmse(plane, group, models, decision, rng))
    return reliability, failure, coverage, comparisons
