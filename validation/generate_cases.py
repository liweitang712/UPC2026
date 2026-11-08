"""Generate frozen public observations and separate private truth for WP3."""

import argparse
import csv
import hashlib
import json
import math
import random
import secrets
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE_PATH = HERE.parent / "spec" / "case.json"
PROTOCOL_PATH = HERE / "protocol-v1.json"
CASE_FIELDS = ("case_id", "split", "stratum", "scenario_id", "t1_s", "x1_m", "y1_m", "z1_m",
               "t2_s", "x2_m", "y2_m", "z2_m")
TRUTH_FIELDS = ("case_id", "event", "t_s", "y_m", "z_m", "clearance_goal", "reason")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_csv(path, fields, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path, *, text_source=False):
    data = path.read_bytes()
    if text_source:
        data = data.replace(bytes((13, 10)), bytes((10,)))
    return hashlib.sha256(data).hexdigest()


def advance(rhs, t, state, dt):
    """Third-order Runge–Kutta step, independent of WP1's integrator."""
    k1 = rhs(t, state)
    k2 = rhs(t + dt / 2, tuple(x + dt * k / 2 for x, k in zip(state, k1)))
    k3 = rhs(t + dt, tuple(x + dt * (2 * b - a) for x, a, b in zip(state, k1, k2)))
    return tuple(x + dt * (a + 4 * b + c) / 6 for x, a, b, c in zip(state, k1, k2, k3))


def locate(rhs, t, state, dt, axis, boundary, direction, tolerance):
    lo, hi = 0.0, dt
    while hi - lo > tolerance:
        mid = (lo + hi) / 2
        if direction * (advance(rhs, t, state, mid)[axis] - boundary) >= 0:
            hi = mid
        else:
            lo = mid
    offset = (lo + hi) / 2
    return t + offset, advance(rhs, t, state, offset)


def simulate(case, solver, rhs, velocity, step):
    initial = case["initial"]
    state = (initial["x_m"], initial["y_m"], initial["z_m"], *velocity)
    goal, defaults = case["goal"], case["protocol_defaults"]
    radius = case["nominal_assumptions"]["radius_m"]
    times = [frame["t_s"] for frame in case["observations"]]
    horizon = defaults["horizon_s"]
    tie = defaults["event_tie_tolerance_s"]
    tolerance = solver["root_bracket_s"]
    t = 0.0
    frames = []
    for target in (*times, horizon):
        while t < target:
            next_t = min(t + step, target)
            dt = next_t - t
            following = advance(rhs, t, state, dt)
            ground = plane = None
            if following[2] <= radius and following[5] < 0:
                ground = locate(rhs, t, state, dt, 2, radius, -1, tolerance)
            if state[0] < goal["x_m"] <= following[0] and following[3] > 0:
                plane = locate(rhs, t, state, dt, 0, goal["x_m"], 1, tolerance)
            if plane and not ground:
                plane_t, plane_state = plane
                lookahead = min(tie, horizon - plane_t)
                ahead = advance(rhs, plane_t, plane_state, lookahead)
                if ahead[2] <= radius and ahead[5] < 0:
                    ground = locate(rhs, plane_t, plane_state, lookahead, 2, radius, -1, tolerance)
            if ground and (not plane or ground[0] <= plane[0] + tie):
                return frames, ("GROUND_FIRST", ground[0], "", "", "", "first_downward_turf")
            if plane:
                crossing_t, (_, y, z, _, _, _) = plane
                inside = goal["y_min_m"] < y < goal["y_max_m"] and goal["z_min_m"] < z < goal["z_max_m"]
                clear = (inside and goal["y_min_m"] + radius < y < goal["y_max_m"] - radius
                         and radius < z < goal["z_max_m"] - radius)
                event = "PLANE_GOAL" if inside else "PLANE_WIDE"
                return frames, (event, crossing_t, y, z, int(clear), "first_forward_plane")
            t, state = next_t, following
        if target != horizon:
            frames.append(state[:3])
    return frames, ("NO_REACH", "", "", "", "", "horizon")


def trial(case, protocol, stratum, index, rng):
    launch, stress = protocol["launch"], protocol["stress"]
    limits = dict(launch)
    if stratum == protocol["challenge_stratum"]:
        limits.update(protocol["challenge"][index % len(protocol["challenge"])])
    speed = rng.uniform(*limits["speed_m_s"])
    azimuth = math.radians(rng.uniform(*limits["azimuth_deg"]))
    elevation = math.radians(rng.uniform(*limits["elevation_deg"]))
    horizontal = speed * math.cos(elevation)
    velocity = horizontal * math.cos(azimuth), horizontal * math.sin(azimuth), speed * math.sin(elevation)
    drag, cy, cz = (rng.uniform(*launch[key]) for key in ("cd", "cy", "cz"))
    wx = wy = 0.0
    if stratum in ("wind", "combined"):
        wx = rng.uniform(*stress["wind_x_m_s"])
        wy = rng.choice((-1, 1)) * rng.uniform(*stress["crosswind_abs_m_s"])
    drag_stress = stratum in ("drag", "combined")
    lift_stress = stratum in ("lift", "combined")
    phase = rng.uniform(0, 2 * math.pi) if lift_stress else 0.0
    nominal = case["nominal_assumptions"]
    beta = nominal["air_density_kg_m3"] * math.pi * nominal["radius_m"] ** 2 / (2 * nominal["ball_mass_kg"])
    gravity = nominal["gravity_m_s2"]

    def rhs(t, state):
        vx, vy, vz = state[3:]
        ux, uy, uz = vx - wx, vy - wy, vz
        u = math.hypot(ux, uy, uz)
        cd = drag
        if drag_stress:
            cd += stress["drag_amplitude"] * math.tanh((stress["drag_transition_m_s"] - u)
                                                       / stress["drag_width_m_s"])
        lateral, vertical = cy, cz
        if lift_stress:
            angle = 2 * math.pi * t / stress["lift_period_s"] + phase
            lateral += stress["lift_amplitude"] * math.sin(angle)
            vertical += stress["lift_amplitude"] * math.cos(angle)
        factor = beta * u
        return (vx, vy, vz, factor * (-cd * ux - vertical * uz - lateral * uy),
                factor * (-cd * uy + lateral * ux), factor * (-cd * uz + vertical * ux) - gravity)

    return velocity, rhs


def check_convergence(coarse, refined, solver):
    coarse_frames, a = coarse
    fine_frames, b = refined
    if len(coarse_frames) != 2 or len(fine_frames) != 2:
        raise ValueError("A trial terminated before both observation frames")
    frame_error = max(math.dist(x, y) for x, y in zip(coarse_frames, fine_frames))
    if a[0] != b[0] or a[4] != b[4]:
        raise ValueError("Step halving changed the event or clearance label")
    time_error = abs(a[1] - b[1]) if a[1] != "" else 0.0
    plane_error = math.dist(a[2:4], b[2:4]) if a[2] != "" else 0.0
    position_error = max(frame_error, plane_error)
    if time_error > solver["convergence_time_s"] or position_error > solver["convergence_position_m"]:
        raise ValueError("Step halving exceeded the locked numerical tolerance")
    return time_error, position_error


def make_split(case, protocol, split, seeds):
    rng = random.Random(seeds["generation"])
    sensor = random.Random(seeds["observation_noise"])
    solver = protocol["solver"]
    max_time_error = max_position_error = 0.0
    records = []
    for stratum in (*protocol["core_strata"], protocol["challenge_stratum"]):
        count = protocol["counts"][split]["challenge" if stratum == protocol["challenge_stratum"] else "core"]
        stressed = stratum in ("sensor", "combined")
        sigma = protocol["stress"]["sensor_sigma_m"] if stressed else case["nominal_assumptions"]["gaussian_coordinate_sigma_m"]
        rho = protocol["stress"]["sensor_frame_correlation"] if stressed else 0.0
        for index in range(count):
            velocity, rhs = trial(case, protocol, stratum, index, rng)
            coarse = simulate(case, solver, rhs, velocity, solver["step_s"])
            fine = simulate(case, solver, rhs, velocity, solver["refined_step_s"])
            time_error, position_error = check_convergence(coarse, fine, solver)
            max_time_error = max(max_time_error, time_error)
            max_position_error = max(max_position_error, position_error)
            frames, truth = fine
            a = [sensor.gauss(0, 1) for _ in range(3)]
            b = [rho * x + math.sqrt(1 - rho ** 2) * sensor.gauss(0, 1) for x in a]
            row = {"split": split, "stratum": stratum, "scenario_id": protocol["scenario_id"]}
            for number, (frame, errors) in enumerate(zip(frames, (a, b)), 1):
                row[f"t{number}_s"] = case["observations"][number - 1]["t_s"]
                for axis, value, error in zip("xyz", frame, errors):
                    row[f"{axis}{number}_m"] = format(value + sigma * error, ".12g")
            records.append((row, truth))
    rng.shuffle(records)
    case_rows, truth_rows = [], []
    for number, (row, truth) in enumerate(records, 1):
        case_id = f"v1-{split}-{number:04d}"
        case_rows.append({"case_id": case_id, **row})
        truth_rows.append(dict(zip(TRUTH_FIELDS, (case_id, *truth))))
    checks = {"max_time_difference_s": max_time_error, "max_position_difference_m": max_position_error}
    return case_rows, truth_rows, checks


def freeze(public, private):
    repo = HERE.parent
    if private.is_relative_to(repo) or private == public or private.is_relative_to(public) or public.is_relative_to(private):
        raise ValueError("Private outputs require a separate directory outside the repository and public output")
    if public.exists() or private.exists():
        raise ValueError("Freeze requires two new output directories")
    case, protocol = read_json(CASE_PATH), read_json(PROTOCOL_PATH)
    seeds = {split: {key: secrets.randbits(128) for key in ("generation", "observation_noise")}
             for split in protocol["counts"]}
    batches = {split: make_split(case, protocol, split, seeds[split]) for split in seeds}
    private.mkdir(parents=True)
    public.mkdir(parents=True)
    write_json(private / "seeds.json", seeds)
    manifest = {"run_id": protocol["run_id"], "status": "inputs_frozen", "hash_algorithm": "sha256",
                "protocol_sha256": sha256(PROTOCOL_PATH, text_source=True), "generator_sha256": sha256(Path(__file__), text_source=True),
                "case_spec_sha256": sha256(CASE_PATH, text_source=True), "splits": {}}
    for split, (cases, truth, checks) in batches.items():
        folder = public / split
        folder.mkdir()
        write_csv(private / f"{split}-cases.csv", CASE_FIELDS, cases)
        write_csv(private / f"{split}-truth.csv", TRUTH_FIELDS, truth)
        observations = cases if split == "development" else [dict(row, stratum="withheld") for row in cases]
        write_csv(folder / "cases.csv", CASE_FIELDS, observations)
        if split == "development":
            write_csv(folder / "truth.csv", TRUTH_FIELDS, truth)
        manifest["splits"][split] = {
            "n_cases": len(cases), "public_cases_sha256": sha256(folder / "cases.csv"),
            "scoring_cases_sha256": sha256(private / f"{split}-cases.csv"),
            "truth_sha256": sha256(private / f"{split}-truth.csv"),
        }
        write_json(private / f"{split}-checks.json", checks)
    write_json(public / "freeze.json", manifest)
    print(f"{protocol['run_id']}: " + ", ".join(f"{split}={len(batch[0])}" for split, batch in batches.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    args = parser.parse_args()
    try:
        freeze(args.public.resolve(), args.private.resolve())
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
