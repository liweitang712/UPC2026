"""Infer an unobstructed penalty trajectory from two timed center positions.

Usage: python penalty_model.py
       python penalty_model.py --coords X1 Y1 Z1 X2 Y2 Z2 --sigma 0.01
Python 3.10+, standard library only. The example writes results beside this
script. A supplied shot prints its JSON prediction.
"""

import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path


HERE = Path(__file__).resolve().parent
RADIUS = 0.11
MASS = 0.43
AIR_DENSITY = 1.225
GRAVITY = 9.80665
BETA = AIR_DENSITY * math.pi * RADIUS**2 / (2 * MASS)
GOAL_X, HALF_WIDTH, HEIGHT = 11.0, 3.66, 2.44
OBSERVED = (1.50, 0.45, 0.44, 2.96, 0.86, 0.74)
PRIOR_MEANS = (0.27, 0.0, 0.0)
PRIOR_SDS = (0.14, 0.22, 0.22)
SCALES = (1.0, 1.0, 1.0, 0.1, 0.1, 0.1)
DEFAULT_SIGMA = 0.010


def acceleration(t, vx, vy, vz, aero, stress):
    cd, cy, cz = aero
    if stress is not None:
        wind_x, wind_y, transition_speed, phase = stress
        vx -= wind_x
        vy -= wind_y
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        cd += 0.18 / (1 + math.exp((speed - transition_speed) / 1.4))
        cy += 0.14 * math.sin(2 * math.pi * 2 * t + phase)
        cz += 0.08 * math.cos(2 * math.pi * 2 * t + phase)
    else:
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    factor = BETA * speed
    return (
        factor * (-cd * vx - cz * vz - cy * vy),
        factor * (-cd * vy + cy * vx),
        factor * (-cd * vz + cz * vx) - GRAVITY,
    )


def advance(state, time, step, aero, stress=None):
    """Classical RK4 step for the coupled position and velocity."""
    x, y, z, vx, vy, vz = state
    half = step / 2
    a1, b1, c1 = acceleration(time, vx, vy, vz, aero, stress)
    u2, v2, w2 = vx + half * a1, vy + half * b1, vz + half * c1
    a2, b2, c2 = acceleration(time + half, u2, v2, w2, aero, stress)
    u3, v3, w3 = vx + half * a2, vy + half * b2, vz + half * c2
    a3, b3, c3 = acceleration(time + half, u3, v3, w3, aero, stress)
    u4, v4, w4 = vx + step * a3, vy + step * b3, vz + step * c3
    a4, b4, c4 = acceleration(time + step, u4, v4, w4, aero, stress)
    weight = step / 6
    return (
        x + weight * (vx + 2 * u2 + 2 * u3 + u4),
        y + weight * (vy + 2 * v2 + 2 * v3 + v4),
        z + weight * (vz + 2 * w2 + 2 * w3 + w4),
        vx + weight * (a1 + 2 * a2 + 2 * a3 + a4),
        vy + weight * (b1 + 2 * b2 + 2 * b3 + b4),
        vz + weight * (c1 + 2 * c2 + 2 * c3 + c4),
    )


def observations(parameters, steps_per_frame=2, stress=None):
    state = (0.0, 0.0, RADIUS, *parameters[:3])
    aero = parameters[3:]
    step = 0.05 / steps_per_frame
    frames = []
    for index in range(2 * steps_per_frame):
        state = advance(state, index * step, step, aero, stress)
        if (index + 1) % steps_per_frame == 0:
            frames.extend(state[:3])
    return tuple(frames)


def plane_crossing(parameters, step=0.010, stress=None, trace=None):
    """Stop on first arrival at the goal plane or at the turf."""
    state = (0.0, 0.0, RADIUS, *parameters[:3])
    aero = parameters[3:]
    if trace is not None:
        trace.append((0.0, *state))
    for index in range(math.ceil(2.0 / step)):
        time = index * step
        new = advance(state, time, step, aero, stress)
        if state[0] < GOAL_X <= new[0]:
            # An RK4 substep and a short bisection avoid interpolation bias.
            lower, upper = 0.0, step
            for _ in range(24):
                middle = (lower + upper) / 2
                crossing = advance(state, time, middle, aero, stress)
                if crossing[0] < GOAL_X:
                    lower = middle
                else:
                    upper = middle
            duration = (lower + upper) / 2
            crossing = advance(state, time, duration, aero, stress)
            # Treat a simultaneous plane/turf event as ground contact.
            if crossing[2] <= RADIUS + 1e-8:
                return None
            if trace is not None:
                trace.append((time + duration, *crossing))
            return (time + duration, crossing[1], crossing[2])
        if new[2] <= RADIUS:
            return None
        state = new
        if trace is not None:
            trace.append((time + step, *state))
    return None


def cholesky(matrix):
    size = len(matrix)
    lower = [[0.0] * size for _ in matrix]
    for i in range(size):
        for j in range(i + 1):
            rest = matrix[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            lower[i][j] = math.sqrt(rest) if i == j else rest / lower[j][j]
    return lower


def lower_solve(lower, rhs):
    value = [0.0] * len(rhs)
    for i in range(len(rhs)):
        value[i] = (rhs[i] - sum(lower[i][j] * value[j] for j in range(i))) / lower[i][i]
    return value


def upper_solve(lower, rhs):
    value = [0.0] * len(rhs)
    for i in range(len(rhs) - 1, -1, -1):
        value[i] = (rhs[i] - sum(lower[j][i] * value[j] for j in range(i + 1, len(rhs)))) / lower[i][i]
    return value


def linearize(parameters, data, sigma):
    pred = observations(parameters)
    residual = [(p - d) / sigma for p, d in zip(pred, data)]
    residual.extend((p - m) / s for p, m, s in zip(parameters[3:], PRIOR_MEANS, PRIOR_SDS))
    columns = []
    for i, scale in enumerate(SCALES):
        shifted = list(parameters)
        shifted[i] += 0.001 * scale
        new = observations(shifted)
        column = [(after - before) / (0.001 * sigma) for before, after in zip(pred, new)]
        column.extend(scale / sd if i == k + 3 else 0.0 for k, sd in enumerate(PRIOR_SDS))
        columns.append(column)
    precision = [[sum(a * b for a, b in zip(ci, cj)) for cj in columns] for ci in columns]
    direction = [-sum(a * b for a, b in zip(col, residual)) for col in columns]
    return cholesky(precision), direction


def log_target(parameters, data, sigma):
    vx, vy, vz, cd, cy, cz = parameters
    if not (8 < vx < 48 and abs(vy) < 20 and 0 < vz < 20):
        return -math.inf
    if not (0.08 < cd < 0.55 and math.hypot(cy, cz) < 0.55):
        return -math.inf
    obs_error = sum(((p - d) / sigma)**2 for p, d in zip(observations(parameters), data))
    prior_error = sum(((p - m) / s)**2 for p, m, s in zip(parameters[3:], PRIOR_MEANS, PRIOR_SDS))
    return -0.5 * (obs_error + prior_error)


def predict(data, sigma, rng, draws=8192, propagated=4096):
    """Draw a local Gaussian proposal and reweight using the full model."""
    if len(data) != 6 or not all(math.isfinite(value) for value in data):
        raise ValueError("Supply six finite frame coordinates in metres.")
    if not (math.isfinite(sigma) and sigma > 0):
        raise ValueError("Coordinate noise sigma must be positive and finite.")
    parameters = [data[0] / 0.05, data[1] / 0.05, (data[2] - RADIUS) / 0.05, *PRIOR_MEANS]
    for _ in range(5):
        lower, direction = linearize(parameters, data, sigma)
        change = upper_solve(lower, lower_solve(lower, direction))
        parameters = [p + scale * delta for p, scale, delta in zip(parameters, SCALES, change)]
    lower, _ = linearize(parameters, data, sigma)
    candidates, log_weights = [], []
    for _ in range(draws):
        standard = [rng.gauss(0, 1) for _ in SCALES]
        offset = upper_solve(lower, standard)
        sample = tuple(p + scale * delta for p, scale, delta in zip(parameters, SCALES, offset))
        log_weight = log_target(sample, data, sigma) + 0.5 * sum(z * z for z in standard)
        if math.isfinite(log_weight):
            candidates.append(sample)
            log_weights.append(log_weight)
    if not candidates:
        raise ValueError("No supported proposal draws. Check coordinates, noise or prior bounds.")
    peak = max(log_weights)
    weights = [math.exp(value - peak) for value in log_weights]
    total = sum(weights)
    ess = total * total / sum(weight * weight for weight in weights)
    points = []
    crossings = {}
    for sample in rng.choices(candidates, weights=weights, k=propagated):
        if sample not in crossings:
            crossings[sample] = plane_crossing(sample)
        point = crossings[sample]
        if point is not None:
            points.append(point)
    return points, ess, tuple(parameters)


def quantile(values, fraction):
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (index - lower) * (ordered[upper] - ordered[lower])


def in_goal(point, inset=0):
    _, y, z = point
    return abs(y) < HALF_WIDTH - inset and inset < z < HEIGHT - inset


def ellipse(points):
    ys, zs = zip(*[(p[1], p[2]) for p in points])
    y0, z0 = statistics.mean(ys), statistics.mean(zs)
    if len(points) < 3:
        return None
    # The tiny diagonal term is only relevant to a degenerate point cloud.
    var_y = statistics.variance(ys) + 1e-12
    var_z = statistics.variance(zs) + 1e-12
    cov = statistics.covariance(ys, zs)
    determinant = var_y * var_z - cov * cov
    squared = [(var_z * (y - y0)**2 - 2 * cov * (y - y0) * (z - z0) + var_y * (z - z0)**2)
               / determinant for y, z in zip(ys, zs)]
    return y0, z0, var_y, cov, var_z, quantile(squared, 0.95)


def inside_ellipse(point, region):
    _, y, z = point
    y0, z0, var_y, cov, var_z, cutoff = region
    squared = (var_z * (y - y0)**2 - 2 * cov * (y - y0) * (z - z0) + var_y * (z - z0)**2)
    return squared <= cutoff * (var_y * var_z - cov * cov)


def mode(points, bandwidth=0.05):
    """Binned Gaussian KDE on a 0.02 m grid."""
    if not points:
        return None
    spacing = 0.02
    histogram = {}
    for _, y, z in points:
        center = (round(y / spacing), round(z / spacing))
        histogram[center] = histogram.get(center, 0) + 1
    scores = {}
    radius = math.ceil(3 * bandwidth / spacing)
    kernel = [
        (dy, dz, math.exp(-0.5 * (dy * dy + dz * dz) * (spacing / bandwidth)**2))
        for dy in range(-radius, radius + 1) for dz in range(-radius, radius + 1)
    ]
    for (iy, iz), count in histogram.items():
        for dy, dz, weight in kernel:
            key = (iy + dy, iz + dz)
            if in_goal((0, key[0] * spacing, key[1] * spacing)):
                scores[key] = scores.get(key, 0) + count * weight
    y, z = max(scores, key=scores.get)
    return [y * spacing, z * spacing]


def summarize(points, ess, parameters, total, with_mode=False):
    entries = [point for point in points if in_goal(point)]
    intervals = [
        [quantile(axis, fraction) for fraction in (0.025, 0.5, 0.975)]
        for axis in zip(*points)
    ] or None
    return {
        "reachable_fraction": len(points) / total,
        "geometric_entry_probability": len(entries) / total,
        "radius_inset_probability": sum(in_goal(p, RADIUS) for p in points) / total,
        "intervals_t_y_z": intervals,
        "entry_mode_y_z": mode(entries) if with_mode else None,
        "joint_95_ellipse": ellipse(points) if points else None,
        "proposal_ess": ess,
        "local_fit_vx_vy_vz_cd_cy_cz": parameters,
        "local_fit_plane_t_y_z": plane_crossing(parameters),
        "local_fit_observations": observations(parameters),
    }


def acceleration_baseline(data):
    start = (0, 0, RADIUS)
    velocity = [(4 * a - b - 3 * p) / 0.10 for p, a, b in zip(start, data[:3], data[3:])]
    a = [(b - 2 * u + p) / 0.05**2 for p, u, b in zip(start, data[:3], data[3:])]
    discriminant = velocity[0]**2 + 2 * a[0] * GOAL_X
    if discriminant < 0 or velocity[0] + math.sqrt(discriminant) <= 0:
        return None
    time = 2 * GOAL_X / (velocity[0] + math.sqrt(discriminant))
    y = velocity[1] * time + 0.5 * a[1] * time**2
    z = RADIUS + velocity[2] * time + 0.5 * a[2] * time**2
    if z < RADIUS:
        return None
    return time, y, z


def validation(scenario, count, rng):
    """Compare with synthetic shots, including deliberately misspecified aerodynamics."""
    results = []
    attempts = 0
    while len(results) < count:
        attempts += 1
        if attempts > 20 * count:
            raise RuntimeError("Validation design did not yield enough goal-plane crossings.")
        cd, cy, cz = (rng.gauss(m, s) for m, s in zip(PRIOR_MEANS, PRIOR_SDS))
        if not (0.08 < cd < 0.55 and math.hypot(cy, cz) < 0.55):
            continue
        parameters = (rng.uniform(22, 35), rng.uniform(-7, 9), rng.uniform(4, 10), cd, cy, cz)
        stress = None
        if scenario == "stress":
            stress = (rng.uniform(-2, 2), rng.uniform(-4, 4), rng.uniform(24, 30), rng.uniform(0, 2 * math.pi))
        truth = plane_crossing(parameters, step=0.005, stress=stress)
        if truth is None:
            continue
        data = tuple(p + rng.gauss(0, DEFAULT_SIGMA) for p in observations(parameters, 10, stress))
        points, ess, _ = predict(data, DEFAULT_SIGMA, rng, draws=384, propagated=256)
        if len(points) < 10:
            continue
        region = ellipse(points)
        predicted = (region[0], region[1])
        baseline = acceleration_baseline(data)
        truth_yz = truth[1:]
        goal_probability = sum(in_goal(p) for p in points) / 256
        results.append({
            "truth_in_goal": in_goal(truth),
            "goal_probability": goal_probability,
            "covered": inside_ellipse(truth, region),
            "squared_error": math.dist(predicted, truth_yz)**2,
            "baseline_squared_error": math.dist(baseline[1:], truth_yz)**2 if baseline else None,
            "ess": ess,
        })
    baseline_pairs = [r for r in results if r["baseline_squared_error"] is not None]
    return {
        "count": count,
        "joint_coverage": statistics.mean(r["covered"] for r in results),
        "rmse_m": math.sqrt(statistics.mean(r["squared_error"] for r in results)),
        "paired_aero_rmse_m": math.sqrt(statistics.mean(r["squared_error"] for r in baseline_pairs)),
        "paired_baseline_rmse_m": math.sqrt(statistics.mean(r["baseline_squared_error"] for r in baseline_pairs)),
        "paired_baseline_count": len(baseline_pairs),
        "brier_score": statistics.mean((r["goal_probability"] - r["truth_in_goal"])**2 for r in results),
        "median_ess": statistics.median(r["ess"] for r in results),
    }


def analytic_checks(parameters):
    vacuum = (28, 2, 8, 0, 0, 0)
    time = GOAL_X / vacuum[0]
    exact = (time, vacuum[1] * time, RADIUS + vacuum[2] * time - 0.5 * GRAVITY * time**2)
    calculated = plane_crossing(vacuum)
    coarse = plane_crossing(parameters, 0.020)
    fine = plane_crossing(parameters, 0.005)
    errors = {
        "vacuum_yz_error_m": math.dist(exact[1:], calculated[1:]),
        "vacuum_time_error_s": abs(exact[0] - calculated[0]),
        "step_halving_yz_error_m": math.dist(coarse[1:], fine[1:]),
        "step_halving_time_error_s": abs(coarse[0] - fine[0]),
    }
    if max(errors.values()) > 0.0001:
        raise AssertionError(f"Integrator check exceeded tolerance: {errors}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coords", nargs=6, type=float, metavar=("X1", "Y1", "Z1", "X2", "Y2", "Z2"))
    parser.add_argument("--sigma", type=float, default=DEFAULT_SIGMA)
    args = parser.parse_args()
    sample_count = 4096
    if args.coords is not None:
        try:
            points, ess, parameters = predict(args.coords, args.sigma, random.Random(20261108), propagated=sample_count)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(summarize(points, ess, parameters, sample_count, with_mode=True), indent=2))
        return
    scenarios = {}
    reference_points = None
    reference_fit = None
    for sigma in (0.003, 0.005, DEFAULT_SIGMA, 0.020, 0.040):
        points, ess, parameters = predict(OBSERVED, sigma, random.Random(20261108), propagated=sample_count)
        scenarios[f"{sigma:.3f}"] = summarize(points, ess, parameters, sample_count, with_mode=sigma == DEFAULT_SIGMA)
        if sigma == DEFAULT_SIGMA:
            reference_points, reference_fit = points, parameters
    validations = {
        scenario: validation(scenario, 120, random.Random(3072 + i))
        for i, scenario in enumerate(("matched", "stress"))
    }
    repeat_points, _, _ = predict(OBSERVED, DEFAULT_SIGMA, random.Random(7014), propagated=sample_count)
    mode_checks = {
        "bandwidth_0.10_y_z": mode([point for point in reference_points if in_goal(point)], 0.10),
        "independent_seed_y_z": mode([point for point in repeat_points if in_goal(point)]),
    }
    result = {
        "observations": OBSERVED,
        "baseline_t_y_z": acceleration_baseline(OBSERVED),
        "scenarios": scenarios,
        "validation": validations,
        "checks": analytic_checks(reference_fit),
        "mode_checks": mode_checks,
    }
    (HERE / "penalty_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (HERE / "penalty_crossings.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("time_s", "y_m", "z_m", "inside_goal", "radius_inset"))
        writer.writerows((*p, int(in_goal(p)), int(in_goal(p, RADIUS))) for p in reference_points)
    trajectory = []
    plane_crossing(reference_fit, trace=trajectory)
    with (HERE / "penalty_trajectory.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("time_s", "x_m", "y_m", "z_m", "vx_m_s", "vy_m_s", "vz_m_s"))
        writer.writerows(trajectory)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
