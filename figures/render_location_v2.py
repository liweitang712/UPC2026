"""Build the figures and supplied-kick evidence for the location release."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from random import Random
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np

from figures.render_public import f1
from inference.baseline import predict
from inference.m2 import normalize, sample
from inference.report import figure2, save, summarize
from physics import load_case, solve
from validation.generate_cases import CASE_PATH, read_json
from validation.location_v2 import RELEASE, rows


FIGURES = RELEASE / "figures"
QA = Path("inference/qa-v2")
COLORS = {"M2": "#14766c", "M1": "#2d6394", "B0": "#a6542a"}


def supplied_shot():
    case = load_case()
    audited = read_json(QA / "repeat/identifiability.json")
    plan = read_json(QA / "repeat/public-manifest.json")["plan"]
    seed = plan["public_seed"] + 1
    budget = plan["public_repeat_draws"]
    samples, _, _ = sample(case, .01, budget, seed, "M2", None, 0, .27, .22)
    weights = normalize(samples)
    predictions = []
    for (_, _, parameters), weight in zip(samples, weights):
        record = asdict(predict("M2", case, parameters))
        predictions.append(dict(weight=str(weight), **{
            key: "" if value is None else str(int(value)) if isinstance(value, bool) else str(value)
            for key, value in record.items()
        }))
    summary = summarize(predictions, case)
    previous = audited["first"]
    reproduced = audited["repeat"]
    for field in ("p_reach", "p_goal", "p_clearance_goal", "entry_mode_yz_m", "entry_mode_check_yz_m"):
        if not np.allclose(summary[field], reproduced[field], rtol=0, atol=1e-8):
            raise ValueError(f"Public refit disagrees with the WP2 audit for {field}")
    coarse_shift = float(np.linalg.norm(np.array(summary["entry_mode_check_yz_m"])
                                        - previous["entry_mode_check_yz_m"]))
    if coarse_shift > .10:
        raise ValueError("The coarser peak did not meet the repeat tolerance")
    summary["entry_mode_assessment"] = dict(
        recommended_mode_yz_m=summary["entry_mode_check_yz_m"], bandwidth_m=.10,
        repeat_shift_m=coarse_shift, fine_bandwidth_m=.05,
        fine_peaks_yz_m=[previous["entry_mode_yz_m"], summary["entry_mode_yz_m"]],
        fine_repeat_shift_m=audited["stability"]["mode_difference_m"],
        interpretation="Smoothed entry mode; finer 0.05 m KDE peak failed repeat criterion")
    summary.update(model="M2", scenario="gaussian-10mm", seed=seed, draw_budget=budget,
                   repeat_check=audited["stability"])
    figure2(FIGURES, case, predictions, summary)
    cumulative = np.cumsum(weights)
    positions = (np.arange(80) + Random(506).random()) / 80
    indices = np.unique(np.searchsorted(cumulative, positions))
    fan = []
    for index in indices:
        draw, _, parameters = samples[index]
        result = solve("M2", case, parameters, include_trace=True)
        event = predict("M2", case, parameters)
        if result.event != event or event.event == "NUMERICAL_FAILURE":
            raise ValueError("Trace replay differs from the scored event")
        fan.append(dict(draw_id=draw, weight=weights[index], event=asdict(event),
                        trace=[asdict(point) for point in result.trace]))
    baselines = []
    for model in ("B0", "B1", "B2"):
        result = solve(model, case, include_trace=True)
        baselines.append(dict(model_id=model, trace=[asdict(p) for p in result.trace]))
    traces = dict(model_id="M2", draw_budget=budget, forecast_seed=seed, trace_seed=506,
                  fan=fan, baselines=baselines)
    save(f1(read_json(CASE_PATH), traces), FIGURES, "F1")
    (FIGURES / "F1-traces.json").write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")
    scenarios = QA / "public-scenarios"
    shutil.copyfile(scenarios / "T2.json", RELEASE / "T2-sensitivity.json")
    for stem in ("F3", "F4"):
        for ext in ("pdf", "png"):
            shutil.copyfile(scenarios / f"{stem}.{ext}", FIGURES / f"{stem}.{ext}")
    (RELEASE / "T2.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def validation_figures():
    metrics = rows(RELEASE / "T3.csv")
    groups = ("matched", "wind", "drag", "lift", "sensor", "combined", "challenge")
    x = np.arange(len(groups))
    fig, axs = plt.subplots(2, 1, sharex=True, figsize=(8.8, 5.1), layout="constrained")
    fig.suptitle("F5  |  Secondary event scores and forecast failures", x=.02, ha="left")
    for model, color in COLORS.items():
        values = [next(r for r in metrics if r["group"] == group and r["model"] == model)
                  for group in groups]
        axs[0].plot(x, [float(r["entry_brier_failure_penalized"]) for r in values], "o-",
                    color=color, label=model)
        axs[1].plot(x, [int(r["n_technical"]) / int(r["n_eligible"]) for r in values],
                    "o-", color=color, label=model)
    axs[0].set_ylabel("Entry Brier loss")
    axs[0].legend(ncol=3)
    axs[1].set(ylabel="Technical failure rate", xticks=x, xticklabels=groups)
    axs[1].yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    save(fig, FIGURES, "F5")

    fig, (coverage, energy) = plt.subplots(1, 2, figsize=(9.2, 3.7), layout="constrained")
    fig.suptitle("F6  |  Joint crossing coverage and paired energy scores", x=.02, ha="left")
    levels = (.50, .80, .95)
    coverage.plot(levels, levels, ":", color="#7f8a91", label="Nominal")
    for model, color in COLORS.items():
        row = next(r for r in metrics if r["group"] == "core" and r["model"] == model)
        n = int(row["n_supported"])
        coverage.plot(levels, [int(row[f"n_hit_{round(level * 100)}"]) / n for level in levels],
                      "o-", color=color, label=f"{model} ({n}/{row['n_truth_plane']})")
    coverage.set(xticks=levels, ylim=(0, 1.03), xlabel="Nominal coverage",
                 ylabel="Observed coverage")
    coverage.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    coverage.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    coverage.legend(fontsize=8)
    energy.axvline(0, color="#7f8a91", ls=":")
    paired = [r for r in rows(RELEASE / "paired-energy.csv") if r["group"] == "core"]
    for i, row in enumerate(paired):
        if row["energy_difference_m"]:
            value, lo, hi = (float(row[k]) for k in ("energy_difference_m", "lo_m", "hi_m"))
            energy.errorbar(value, i, xerr=[[value - lo], [hi - value]], fmt="o", color=COLORS["M2"])
        else:
            energy.text(.02, i, "Insufficient overlap", transform=energy.get_yaxis_transform())
    energy.set(yticks=range(len(paired)), ylim=(-.5, len(paired)-.5),
               yticklabels=[f"M2 − {r['comparator']} ({r['n_paired']})" for r in paired],
               xlabel="Paired mean energy-score difference (m)")
    save(fig, FIGURES, "F6")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("public", "validation"))
    args = parser.parse_args()
    FIGURES.mkdir(exist_ok=True)
    (supplied_shot if args.part == "public" else validation_figures)()


if __name__ == "__main__":
    main()
