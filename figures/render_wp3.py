"""Render WP3 F5 and F6 from verified blind forecasts, or make demo previews."""

import argparse
import csv
from math import hypot
from pathlib import Path
from random import Random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

from figures.evidence import DISPLAY_GROUPS, LEVELS, PLANE, Forecast, Shot, aggregate, load_shots
from validation.generate_cases import HERE, PROTOCOL_PATH, read_json, sha256, write_csv
from validation.locked_score import PUBLIC, check_hash, selection_record, verify_inputs, verify_lock

COLORS = ("#17628A", "#B24D2A")
MARKERS = ("o", "s")
LABELS = {"single_factor": "Single-factor stress"}
F5_CAPTION = (
    "Calibration of exact probabilities for centre entry and forward plane arrival on synthetic trials "
    "with resolved truth. Nominal decile bins include 1 in the final bin. Numbers below each panel "
    "are per-bin counts in model order. Bins below the locked minimum are omitted from the curves. "
    "Vertical bars are 95% Wilson intervals. The single-factor panels pool wind, drag, lift and sensor stress. "
    "Technical failures use all cases with resolved truth. Point abstentions use cases with a resolved forecast "
    "and a recorded point decision. The challenge sample is reported separately."
)
F6_CAPTION = (
    "Joint crossing-region coverage on synthetic trials whose true trajectory crossed the plane. "
    "The numerator counts true crossings contained in the highest-mass 0.10 m grid regions. "
    "Panel labels show supported forecasts over all true crossings for each model. "
    "Vertical bars are 95% Wilson intervals. Below, selected minus comparator crossing RMSE uses "
    "paired conditional-mean forecasts on their common valid cases. Horizontal bars are 95% percentile "
    "intervals from a paired bootstrap within each stratum. Rows below the locked overlap minimum are marked "
    "as insufficient."
)


def label(group):
    return LABELS.get(group, group.replace("_", " ").capitalize())


def percent(axis, which="y"):
    getattr(axis, f"{which}axis").set_major_formatter(PercentFormatter(1, decimals=0))


def model_handles(models):
    return [Line2D([], [], color=color, marker=marker, label=model, markersize=5)
            for model, color, marker in zip(models, COLORS, MARKERS)]


def reliability_figure(reliability, failures, models, strata, demo):
    fig = plt.figure(figsize=(12.2, 8.7))
    grid = fig.add_gridspec(3, 4, height_ratios=(1, 1, 0.8), hspace=0.77, wspace=0.35,
                           left=0.075, right=0.975, top=0.84, bottom=0.09)
    fig.suptitle("F5  |  Event reliability and forecast availability", x=0.075, y=0.971, ha="left")
    subtitle = "ILLUSTRATIVE DATA  /  layout preview" if demo else "LOCKED BLIND EVALUATION  /  synthetic trials"
    fig.text(0.075, 0.928, subtitle, color="#516170", fontsize=9)
    fig.legend(handles=model_handles(models), loc="upper right", bbox_to_anchor=(0.975, 0.958),
               ncol=2, frameon=False)

    for row_index, target in enumerate(("entry", "arrival")):
        for column, group in enumerate(DISPLAY_GROUPS):
            ax = fig.add_subplot(grid[row_index, column])
            ax.plot([0, 1], [0, 1], "--", color="#9BA8B3", linewidth=0.9, zorder=1)
            ax.set(xlim=(-0.035, 1.035), ylim=(-0.035, 1.035), xticks=[0, .5, 1], yticks=[0, .5, 1])
            percent(ax, "x")
            percent(ax)
            if row_index == 0:
                ax.set_title(label(group), loc="left", pad=7)
            if column == 0:
                ax.set_ylabel(f"{target.capitalize()} observed")
            for index, (model, color, marker) in enumerate(zip(models, COLORS, MARKERS)):
                rows = [r for r in reliability if (r["group"], r["model"], r["target"]) == (group, model, target)]
                visible = [r for r in rows if r["observed_rate"] is not None]
                if visible:
                    y = [r["observed_rate"] for r in visible]
                    error = [[max(0, r["observed_rate"] - r["lo"]) for r in visible],
                             [max(0, r["hi"] - r["observed_rate"]) for r in visible]]
                    ax.errorbar([r["mean_forecast"] for r in visible], y, yerr=error, color=color,
                                fmt=marker, markersize=4, capsize=2, linewidth=1)
                counts = " ".join(f"{r['n']:>2}" for r in rows)
                ax.text(0.5, -0.25 - index * 0.13, f"n {counts}", transform=ax.transAxes, ha="center",
                        color=color, fontsize=6.6, family="monospace")
    fig.text(0.53, 0.874, "Mean forecast probability on each horizontal axis", ha="center", fontsize=9)

    ax = fig.add_subplot(grid[2, :])
    ax.set_title("Technical failures and point abstentions", loc="left", pad=9)
    for index, (model, color) in enumerate(zip(models, COLORS)):
        for position, group in enumerate(strata):
            row = next(r for r in failures if r["group"] == group and r["model"] == model)
            x = position + (index - .5) * .36
            if row["n_truth"]:
                ax.bar(x - .08, row["n_technical"] / row["n_truth"], .15, color=color)
            if row["n_point_assessed"]:
                ax.bar(x + .08, row["n_abstained"] / row["n_point_assessed"], .15, facecolor="white",
                       edgecolor=color, hatch="///", linewidth=0.8)
    ax.set(xticks=list(range(len(strata))), xticklabels=[label(group) for group in strata],
           ylabel="Rate", ylim=(0, 1.06))
    percent(ax)
    ax.legend(handles=[Patch(facecolor="#536372", label="Technical failure"),
                       Patch(facecolor="white", edgecolor="#536372", hatch="///", label="Point abstention")],
              loc="upper right", ncol=2, frameon=False)
    return fig


def coverage_figure(coverage, comparisons, models, demo):
    fig = plt.figure(figsize=(12.2, 6.9))
    grid = fig.add_gridspec(2, 4, height_ratios=(1, 1.25), hspace=0.48, wspace=0.35,
                           left=0.075, right=0.975, top=0.80, bottom=0.095)
    fig.suptitle("F6  |  Joint coverage and paired crossing error", x=0.075, y=0.970, ha="left")
    subtitle = "ILLUSTRATIVE DATA  /  layout preview" if demo else "LOCKED BLIND EVALUATION  /  true plane crossings"
    fig.text(0.075, 0.917, subtitle, color="#516170", fontsize=9)
    fig.legend(handles=model_handles(models), loc="upper right", bbox_to_anchor=(0.975, 0.956),
               ncol=2, frameon=False)

    for column, group in enumerate(DISPLAY_GROUPS):
        ax = fig.add_subplot(grid[0, column])
        ax.set_title(label(group), loc="left", pad=20)
        ax.plot([0, 1], [0, 1], "--", color="#9BA8B3", linewidth=0.9)
        ax.set(xlim=(0.43, 1.02), ylim=(-0.03, 1.05), xticks=LEVELS, yticks=[0, .5, 1],
               xlabel="Nominal coverage")
        if column == 0:
            ax.set_ylabel("Observed coverage")
        percent(ax, "x")
        percent(ax)
        for index, (model, color, marker) in enumerate(zip(models, COLORS, MARKERS)):
            rows = [r for r in coverage if r["group"] == group and r["model"] == model]
            n, total = rows[0]["n_available"], rows[0]["n_truth_plane"]
            ax.text(index * .5, 1.035, f"{n}/{total} supported", transform=ax.transAxes,
                    color=color, fontsize=8)
            if n:
                error = [[max(0, r["observed"] - r["lo"]) for r in rows],
                         [max(0, r["hi"] - r["observed"]) for r in rows]]
                ax.errorbar([r["nominal"] + (index - .5) * .02 for r in rows],
                            [r["observed"] for r in rows], yerr=error, color=color,
                            fmt=marker, markersize=4, capsize=2, linewidth=1)

    forest = grid[1, :].subgridspec(1, 2, width_ratios=(4, 1.25), wspace=0.12)
    ax = fig.add_subplot(forest[0, 0])
    counts = fig.add_subplot(forest[0, 1], sharey=ax)
    ax.set_title("Paired crossing RMSE by stratum", loc="left", pad=10)
    counts.set_title("Paired / true crossings", loc="left", pad=10, fontsize=10)
    ax.axvline(0, linestyle="--", color="#9BA8B3", linewidth=0.9)
    for index, row in enumerate(comparisons):
        if row["delta"] is not None:
            ax.hlines(index, row["lo"], row["hi"], color=COLORS[0], linewidth=1.4)
            ax.plot(row["delta"], index, "o", color=COLORS[0], markersize=5)
        suffix = "  (insufficient)" if row["delta"] is None else ""
        counts.text(0, index, f"{row['n_paired']} / {row['n_truth_plane']}{suffix}",
                    va="center", fontsize=9)
    ax.set(yticks=list(range(len(comparisons))), yticklabels=[label(r["group"]) for r in comparisons],
           ylim=(len(comparisons) - 0.5, -0.5), xlabel=f"RMSE difference (m)  |  {models[0]} minus {models[1]}")
    if not any(row["delta"] is not None for row in comparisons):
        ax.set_xlim(-1, 1)
    counts.set_axis_off()
    return fig


def demonstration(protocol, models):
    """Simulate display-only data independently of all contest observations."""
    rng = Random(8307)
    shots = []
    for stratum in (*protocol["core_strata"], protocol["challenge_stratum"]):
        for index in range(120):
            arrival = 0.05 + 0.9 * (index + .5) / 120
            entry = arrival * (0.35 + 0.55 * rng.random())
            u = rng.random()
            event = "PLANE_GOAL" if u < entry else "PLANE_WIDE" if u < arrival else "GROUND_FIRST"
            forecasts, status = {}, {}
            for j, model in enumerate(models):
                technical = rng.random() < .06 + j * .04
                resolved = not technical or rng.random() < .7
                support = event in PLANE and resolved and rng.random() > .09 + j * .09
                rank = rng.random()
                squared_error = hypot(rng.gauss(0, .27 + .1 * j), rng.gauss(0, .24 + .1 * j)) ** 2
                shift = .08 * j
                forecasts[model] = Forecast(technical, resolved, None if technical else min(1, entry + shift),
                                            None if technical else min(1, arrival + shift),
                                            tuple(rank < level - shift for level in LEVELS) if support else None,
                                            squared_error if support else None)
                status[model] = ("abstained" if rng.random() < .2 + .15 * j else "available") if resolved else None
            shots.append(Shot(stratum, event, forecasts, status))
    return shots


def export(output, evidence, models, protocol, run_id, demo, source_hashes):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 11,
                         "figure.titlesize": 19, "figure.titleweight": "bold", "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#84919C", "pdf.fonttype": 42,
                         "axes.labelcolor": "#22323F", "text.color": "#192D3C"})
    reliability, failures, coverage, paired = evidence
    strata = (*protocol["core_strata"], protocol["challenge_stratum"])
    output.mkdir(parents=True)
    assets = (
        ("F5", reliability_figure(reliability, failures, models, strata, demo), F5_CAPTION,
         ("F5_reliability.csv", reliability), ("F5_failures.csv", failures),
         "resolved truth; exact probability or known point status as applicable"),
        ("F6", coverage_figure(coverage, paired, models, demo), F6_CAPTION,
         ("F6_coverage.csv", coverage), ("F6_paired_rmse.csv", paired),
         "true plane crossing; supported forecast or shared valid pair as applicable"),
    )
    manifest = []
    for asset, fig, caption, table1, table2, condition in assets:
        fig.savefig(output / f"{asset}.pdf", metadata={"CreationDate": None, "ModDate": None})
        fig.savefig(output / f"{asset}.png", dpi=180)
        plt.close(fig)
        for filename, rows in (table1, table2):
            tagged = [dict(run_id=run_id, scenario_id=protocol["scenario_id"], **row) for row in rows]
            write_csv(output / filename, tuple(tagged[0]), tagged)
        prefix = "Illustrative preview using constructed data. " if demo else ""
        (output / f"{asset}_caption.md").write_text(prefix + caption + "\n", encoding="utf-8")
        manifest.append(dict(asset_id=asset, run_id=run_id, version="v1", owner="WP3",
                             population="constructed preview" if demo else "frozen blind synthetic trials",
                             scenario_id=protocol["scenario_id"], condition=condition,
                             statistic="reliability and forecast availability" if asset == "F5" else "joint coverage and paired crossing RMSE",
                             units="%" if asset == "F5" else "%; m", source_artifact=f"{table1[0]}; {table2[0]}",
                             row_filters="core strata and challenge; figures also pool single-factor stress",
                             pdf=f"{asset}.pdf", png=f"{asset}.png", caption=f"{asset}_caption.md",
                             source_hashes=source_hashes))
    write_csv(output / "figures_manifest.csv", tuple(manifest[0]), manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--private", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        protocol = read_json(PROTOCOL_PATH)
        if args.output.exists():
            raise ValueError("Use a new output directory")
        if args.demo:
            run_id, models, source_hashes = "demo-figure-layout", ("Demo A", "Demo B"), "demo_seed=8307"
            shots = demonstration(protocol, models)
        else:
            private = args.private.resolve()
            if private.is_relative_to(HERE.parent):
                raise ValueError("Use an external WP3 custody directory")
            manifest = verify_inputs(PUBLIC, "blind")
            lock = private / "blind-predictions"
            metadata, forecast = verify_lock(lock, "blind", manifest)
            decision, models = selection_record(private, manifest)
            check_hash(decision, metadata["selection_decision_sha256"])
            if set(forecast["models"]) != set(models):
                raise ValueError("Blind model pair differs from the selection record")
            entry = manifest["splits"]["blind"]
            cases, truth = private / "blind-cases.csv", private / "blind-truth.csv"
            check_hash(cases, entry["scoring_cases_sha256"])
            check_hash(truth, entry["truth_sha256"])
            status = lock / "point-status.csv"
            check_hash(status, metadata["point_status_sha256"])
            run_id = manifest["run_id"]
            source_hashes = "; ".join(f"{key}={value}" for key, value in (
                ("cases", entry["scoring_cases_sha256"]), ("truth", entry["truth_sha256"]),
                ("predictions", metadata["predictions_sha256"]), ("point_status", metadata["point_status_sha256"]),
                ("protocol", sha256(PROTOCOL_PATH, text_source=True)),
            ))
            shots = load_shots(cases, truth, lock / "predictions.csv", status, models, protocol)
        export(args.output, aggregate(shots, models, protocol), models, protocol, run_id, args.demo, source_hashes)
    except (OSError, ValueError, KeyError, csv.Error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
