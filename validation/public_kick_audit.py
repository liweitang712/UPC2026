"""Replay the supplied M2 kick and partition center misses by goal boundary."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import atan2, degrees, fsum, hypot
from pathlib import Path

import numpy as np

from inference.baseline import predict
from inference.m2 import normalize, sample
from inference.report import quantile
from physics import load_case, solve


def run(drag_mean, seed, budget):
    t2 = Path("releases/upc2026-location-v2/T2.json").read_bytes().replace(b"\r\n", b"\n")
    frozen = json.loads(t2)
    case = load_case()
    draws, _, _ = sample(case, .01, budget, seed, "M2", None, 0, drag_mean, .22)
    weights = normalize(draws)
    events = [predict("M2", case, parameters) for _, _, parameters in draws]
    buckets = {"entry": [], "above_only": [], "wide_only": [], "above_and_wide": [],
               "low_or_boundary": [], "ground_first": [], "no_reach": [], "numerical_failure": []}
    plane, timed = [], []
    for event, weight in zip(events, weights, strict=True):
        if event.event.startswith("PLANE_"):
            plane.append(weight)
            timed.append((event.t_s, weight))
            above = event.z_m >= case.z_max
            wide = event.y_m <= case.y_min or event.y_m >= case.y_max
            if event.event == "PLANE_GOAL":
                assert not above and not wide and event.z_m > case.z_min
                key = "entry"
            else:
                key = ("above_and_wide" if above and wide else "above_only" if above
                       else "wide_only" if wide else "low_or_boundary")
        else:
            key = event.event.lower()
        buckets[key].append(weight)
    outcome = {key: fsum(values) for key, values in buckets.items()}
    assert abs(fsum(outcome.values()) - 1) < 1e-10
    t, w = map(np.array, zip(*timed))
    times = quantile(t, w / w.sum(), [.025, .5, .975]).tolist()
    arrival = fsum(plane)
    if drag_mean == .27 and seed == frozen["seed"] and budget == frozen["draw_budget"]:
        assert abs(outcome["entry"] - frozen["p_goal"]) < 1e-9
        assert abs(arrival - frozen["p_reach"]) < 1e-9
        assert np.allclose(times, frozen["plane_intervals"]["t_s"], rtol=0, atol=1e-9)
    launch = solve("B0", case, include_trace=True).trace[0]
    vx, vy, vz = launch.vx_m_s, launch.vy_m_s, launch.vz_m_s
    speed = hypot(vx, vy, vz)
    reynolds_scale = case.density * 2 * case.radius / 1.81e-5
    upper = 495800 / reynolds_scale
    return dict(
        run_id="upc2026-public-audit-v1", t2_sha256=sha256(t2).hexdigest(),
        model="M2", gaussian_sd_m=.01, drag_mean=drag_mean, seed=seed, proposals=budget,
        accepted=len(draws), ess=1 / fsum(w**2 for w in weights), arrival=arrival, outcomes=outcome,
        t_given_plane_s=times, time_after_last_frame_s=[t - case.times[-1] for t in times],
        b0_launch=dict(speed_m_s=speed, reynolds=reynolds_scale*speed,
                       azimuth_deg=degrees(atan2(vy,vx)), elevation_deg=degrees(atan2(vz,hypot(vx,vy))),
                       curve_upper_speed_m_s=upper, fractional_gap=(upper-speed)/upper,
                       anchor_reynolds=30*reynolds_scale),
    )


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("drag_mean", type=float)
    parser.add_argument("seed", type=int)
    parser.add_argument("budget", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run(args.drag_mean, args.seed, args.budget)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(args.output.name, result["outcomes"], result["t_given_plane_s"], result["ess"])
