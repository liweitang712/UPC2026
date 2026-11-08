"""Reformat frozen v1 evidence for letter-size print; never edit the release."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--location-v2-f4", action="store_true",
                        help="Render only the F4 derivative from the frozen location-v2 sensitivity data")
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))

    from figures.render_wp3 import coverage_figure, plt, reliability_figure

    if args.location_v2_f4:
        release = args.repo / "releases/upc2026-location-v2"
        manifest = {
            "run_id": "upc2026-location-v2",
            "artifact_sha256": {
                "T2-sensitivity.json": "29504df5073eb677bbf404f25dc86399d6e4146668d7e9618322207c639f307a",
            },
        }
    else:
        release = args.repo / "releases/upc2026-wp3-v1"
        manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    used = {}

    def locked(name):
        path = release / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != manifest["artifact_sha256"][name]:
            raise ValueError(f"Frozen hash mismatch: {name}")
        used[name] = digest
        return path

    def rows(name, integers=(), floats=()):
        with locked(f"figures/{name}.csv").open(newline="", encoding="utf-8") as f:
            result = list(csv.DictReader(f))
        for row in result:
            if row["run_id"] != manifest["run_id"]:
                raise ValueError(f"Wrong run ID in {name}")
            for key in integers:
                row[key] = int(row[key])
            for key in floats:
                row[key] = float(row[key]) if row[key] else None
        return result

    plt.rcParams.update({
        "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
        "figure.titlesize": 11, "pdf.fonttype": 42, "pdf.compression": 9,
    })
    args.output.mkdir(parents=True, exist_ok=True)

    def save(fig, name):
        fig.savefig(args.output / f"{name}.pdf", metadata={"CreationDate": None})
        fig.savefig(args.output / f"{name}.png", dpi=200)
        plt.close(fig)

    def save_manifest():
        (args.output / "presentation-manifest.json").write_text(json.dumps({
            "run_id": manifest["run_id"],
            "kind": "presentation derivatives",
            "inputs_sha256": used,
        }, indent=2) + "\n", encoding="utf-8")

    sensitivity = "T2-sensitivity.json" if args.location_v2_f4 else "T2-candidates.json"
    candidates = json.loads(locked(sensitivity).read_text(encoding="utf-8"))
    fig = plt.figure(figsize=(6.5, 4.1), layout="constrained")
    spec = fig.add_gridspec(2, 2, height_ratios=(1.2, 1))
    measured = fig.add_subplot(spec[0, :])
    gaussian = ("sigma5", "m2", "sigma20")
    measured.plot([5, 10, 20], [100*candidates[k]["p_goal"] for k in gaussian],
                  "o-", color="#17628A", label="Gaussian")
    measured.plot(10, 100*candidates["rounded"]["p_goal"], "D", color="#B24D2A",
                  label="Gaussian + rounding")
    rounding = candidates["rounding"]
    measured.plot(0, 100*rounding["p_goal"], "s", markerfacecolor="none",
                  color="#6B4381", label=f"Rounding only (ESS ≈ {rounding['diagnostics']['ess']:.0f})")
    measured.set(xlim=(-1, 21), ylim=(69, 105), xticks=[0, 5, 10, 20],
                 xlabel="Gaussian coordinate SD (mm)", ylabel="Entry probability (%)")
    measured.legend(loc="lower left", ncol=2, frameon=False)
    variants = ("m2", "trionda", "jabulani", "wind", "transverse-prior")
    labels = ("M2 nominal", "Trionda", "Jabulani", "Wind +3 m/s in Y", "Transverse SD 0.12")
    axes = [fig.add_subplot(spec[1, i]) for i in range(2)]
    for ax, coordinate, axis in zip(axes, ("z_m", "y_m"), ("Z", "Y")):
        for i, key in enumerate(variants):
            lo, median, hi = candidates[key]["plane_intervals"][coordinate]
            ax.errorbar(median, i, xerr=[[median-lo], [hi-median]], fmt="o",
                        color="#17628A", markersize=4)
        ax.set(yticks=range(len(variants)), yticklabels=labels if axis == "Z" else [],
               ylim=(-.45, len(variants)-.55), xlabel=f"Crossing {axis} (m) given plane arrival")
        ax.invert_yaxis()
    axes[0].axvline(2.44, color="#6C7379", linestyle=":")
    save(fig, "F4")
    if args.location_v2_f4:
        save_manifest()
        return

    rel = rows("F5_reliability", ("n", "n_exact", "n_truth"),
               ("bin_lo", "bin_hi", "mean_forecast", "observed_rate", "lo", "hi"))
    fail = rows("F5_failures", ("n_truth", "n_technical", "n_point_assessed", "n_abstained"))
    models = (manifest["selected_model"], manifest["comparator_model"])
    strata = list(dict.fromkeys(r["group"] for r in fail if r["group"] != "single_factor"))
    fig = reliability_figure(rel, fail, models, strata, False)
    fig.set_size_inches(6.5, 3.7)
    fig.axes[0].get_gridspec().update(left=.115, hspace=.78, wspace=.4)
    for axis in fig.axes[:8]:
        for annotation in tuple(axis.texts):
            if annotation.get_text().startswith("n "):
                annotation.remove()
        axis.set(xticklabels=["0", "50", "100"], yticklabels=["0", "50", "100"])
    fig.axes[-1].set_xticklabels(["Match", "Wind", "Drag", "Lift", "Sensor", "Combined", "Challenge"])
    fig.axes[0].set_ylabel("Entry (%)")
    fig.axes[4].set_ylabel("Arrival (%)")
    fig.axes[-1].set_title("Forecast availability", pad=12, loc="left")
    fig.axes[-1].get_legend().set_bbox_to_anchor((1, 1.43))
    fig.texts[0].set_text("F5  |  Event reliability and forecast availability")
    fig.texts[1].set_visible(False)
    fig.texts[2].set_text("Mean forecast probability (%)")
    fig.texts[2].set_y(.9)
    save(fig, "F5")

    coverage = rows("F6_coverage", ("n_available", "n_truth_plane"),
                    ("nominal", "observed", "lo", "hi"))
    paired = rows("F6_paired_rmse", ("n_paired", "n_truth_plane"), ("delta", "lo", "hi"))
    fig = coverage_figure(coverage, paired, models, False)
    fig.set_size_inches(6.5, 3.6)
    outer = fig.axes[0].get_gridspec()
    outer.update(left=.125, right=.965, top=.74, bottom=.155, hspace=.72, wspace=.4)
    outer.set_height_ratios((1, 1.55))
    fig.texts[1].set_visible(False)
    fig.legends[0].set_bbox_to_anchor((.965, .955))
    for ax in fig.axes[:4]:
        ax.set(xlabel="", xticklabels=["50", "80", "95"], yticklabels=["0", "50", "100"])
    fig.axes[0].set_ylabel("Observed (%)")
    fig.text(.56, .451, "Nominal coverage (%)", ha="center")
    fig.axes[-1].set_title("Paired / true", loc="left", pad=10, fontsize=9)
    for ax in fig.axes:
        for label in ax.texts:
            label.set_fontsize(max(9, label.get_fontsize()))
    save(fig, "F6")

    counts = {}
    for row in rel:
        key = row["target"], row["group"], row["model"]
        counts.setdefault(key, []).append(row["n"])
    with (args.output / "F5-bin-counts.tex").open("w", encoding="utf-8") as f:
        f.write(r"\begin{table}[htbp]" "\n" r"\centering\small" "\n")
        f.write(r"\caption{Decile-bin counts for Figure~\ref{fig:F5}. Counts include bins below the display threshold. The last bin includes a forecast probability of one.}" "\n")
        f.write(r"\label{tab:f5-bin-counts}\begin{tabular}{lll*{10}{r}}" "\n")
        f.write(r"\toprule Event & Stratum & Model & " + " & ".join(f"{i}0" if i else "0" for i in range(10)) + r" \\ \midrule" "\n")
        for (target, group, model), values in counts.items():
            group = group.replace("single_factor", "single factor")
            f.write(" & ".join([target.capitalize(), group.capitalize(), model, *map(str, values)]) + r" \\" "\n")
        f.write(r"\bottomrule\end{tabular}\end{table}" "\n")
    save_manifest()


if __name__ == "__main__":
    main()
