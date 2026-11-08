"""Generate WP3's shared LaTeX section and evidence index from a locked release."""

import argparse
import csv
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from validation.generate_cases import read_json, write_csv
from validation.locked_score import check_hash
from validation.score_entry import read_rows

CLAIM_FIELDS = ("claim_id", "run_id", "version", "source_artifact", "source_key_or_filter", "statistic",
                "population", "condition", "display_unit", "owner")


def tex(value):
    escapes = {"%": r"\%", "_": r"\_", "&": r"\&", "#": r"\#", "$": r"\$",
               "{": r"\{", "}": r"\}", "\\": r"\textbackslash{}"}
    return "".join(escapes.get(character, character) for character in str(value))


def score(value):
    return "--" if value is None or value == "" else f"{float(value):.4f}"


def percentage(value):
    return "--" if value is None or value == "" else f"{100 * float(value):.1f}" + r"\%"


def latex_table(blind, models, conditional):
    group_labels = {"matched": "Matched", "wind": "Wind", "drag": "Drag", "lift": "Lift",
                    "sensor": "Sensor", "combined": "Combined", "challenge": "Challenge"}
    rows = []
    for group, label in group_labels.items():
        for model in models:
            row = blind["models"][model]["strata"][group]
            extra = conditional.get((group, model), {})
            ordinary = score(row["entry_brier"])
            ordinary += f" ({row['entry_brier_n']})" if row["entry_brier_n"] else ""
            support = f"{row['n_region_supported']}/{row['n_truth_plane']}"
            failure = f"{row['n_failed']}/{row['n_entirely_invalid']}"
            energy = score(extra.get("energy_score_m"))
            if extra.get("n_energy"):
                energy += f" ({extra['n_energy']})"
            abstention = (f"{extra['n_point_abstained']}/{extra['n_resolved_forecast']}"
                          if extra else "--")
            values = (label, model, f"{row['n_eligible']}/{row['n_total']}",
                      score(row["entry_brier_failure_penalized"]), ordinary, failure, abstention, support,
                      percentage(row["coverage_95"]), energy)
            rows.append(" & ".join(str(value) for value in values) + r" \\")
    return "\n".join([
        r"\begin{table}[htbp]", r"\centering",
        r"\caption{T3. Locked blind evaluation by stratum. Eligible truth excludes truth-solver failures. "
        r"The penalized entry score uses all eligible cases. The ordinary score gives the exact-probability "
        r"denominator in parentheses. Forecast failures are shown as any unresolved or invalid forecast "
        r"versus entirely invalid. Abstentions are counted among resolved forecasts. "
        r"Coverage uses the supported regions among true plane crossings. "
        r"Energy scores condition on plane crossing, with the scored count in parentheses.}",
        r"\label{tab:T3}", r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{llrrrrrrrr}", r"\hline",
        r"Stratum & Model & Truth eligible/total & Penalized Brier & Ordinary Brier ($n$) & "
        r"Failures any/full & Abstentions/resolved & Regions/truth plane & 95\% coverage & Energy, m ($n$) \\",
        r"\hline", *rows, r"\hline", r"\end{tabular}}", r"\end{table}",
    ])


def wp3_section(release, selection, blind, protocol, conditional, captions):
    models = release["selected_model"], release["comparator_model"]
    selected, comparator = models
    comparison = next(row for row in blind["comparisons"] if (row["candidate"], row["comparator"]) == models)
    split = release["input_freeze"]["splits"]
    count = {key: row["n_cases"] for key, row in split.items()}
    loss = {model: blind["models"][model]["core"]["entry_brier_failure_penalized"] for model in models}
    selection_loss = {model: selection["models"][model]["core"]["entry_brier_failure_penalized"] for model in models}
    settings = protocol["decision"]
    adopted = selection["upgrade_adopted"]
    gate_result = ("An aerodynamic upgrade passed the selection gates." if adopted else
                   "No aerodynamic candidate passed the registered selection gates. The blind comparison is therefore descriptive.")
    blind_gate = ("The selected candidate met the registered blind improvement gates." if blind["confirmed"] else
                  "The blind comparison does not support a confirmed aerodynamic upgrade.")
    coverage = []
    for model in models:
        row = blind["models"][model]["core"]
        coverage.append(f"{percentage(row['coverage_95'])} for {model} "
                        f"({row['n_region_hits']}/{row['n_region_supported']} supported regions "
                        f"among {row['n_truth_plane']} true plane crossings)")
    return "\n\n".join([
        f"% Run {release['run_id']}; selection-results.json; blind-results.json; metrics.csv; "
        f"blind-conditional.csv; models {selected}/{comparator}; scenario {release['scenario_id']}.",
        r"\section{Synthetic validation and model comparison}",
        r"\subsection{Design and sealing}",
        f"The development, selection, and blind sets contained {count['development']}, {count['selection']}, "
        f"and {count['blind']} distinct synthetic shots, respectively. The nominal forecast used the two "
        r"noisy frame centres with independent 10\,mm Gaussian errors in each coordinate. The generation "
        r"model used an independent third-order Runge--Kutta implementation with step halving. An event "
        r"search refined first plane and turf crossings under the same geometric and time-tie rules as the "
        r"forecast. We retained separate strata for matched trajectories, wind, speed-dependent drag, "
        r"time-varying transverse force, sensor error, and combined stress. The enriched challenge set "
        r"probed lateral misses, shallow launches, and nearly vertical launches. It was excluded from "
        r"the equal-weight mean across the six core strata. The supplied kick was outside the benchmark.",
        r"We locked each prediction CSV before revealing the corresponding labels. The selection lock "
        r"contained all six model families. The blind lock used the chosen pair with the same per-model "
        r"settings. A forecast received only the two observed frame centres, their times, and the nominal "
        r"scenario. The scorer joined the predictions to the held-out truth and scoring strata by case ID.",
        r"\subsection{Scoring and selection}",
        r"The primary outcome was centre entry. The Brier loss was $(p-I)^2$, where $I$ is the truth "
        r"indicator. A forecast with resolved event mass $p$ and failed mass $f$ received the worse loss "
        r"at the endpoints $p$ and $p+f$. Entirely invalid or missing forecasts received unit loss. "
        r"We also report ordinary Brier loss for exact probabilities and score plane arrival, radius "
        r"clearance, and first turf contact separately. A point abstention does not remove a valid "
        r"event probability. In conditional crossing scores, the location uses resolved plane draws and "
        r"truth that reached the plane.",
        f"An aerodynamic model needed a reduction of at least {settings['minimum_brier_gain']:.2f} in "
        r"the equal-core-stratum penalized entry loss and a gain greater than one paired bootstrap "
        f"standard error. It could lose at most {settings['maximum_core_brier_degradation']:.2f} in each "
        f"core stratum, produce at most {percentage(settings['maximum_entirely_invalid_fraction'])} entirely "
        f"invalid forecasts, and fall no more than {100 * settings['maximum_undercoverage']:.0f} percentage "
        r"points below nominal 95\% coverage. Region coverage uses highest-mass square cells of side "
        f"{settings['joint_region_grid_m']:.2f}\\,m with all ties at the cutoff included. A conditional region "
        f"requires at least {settings['minimum_conditional_effective_draws']} effective draws. The paired "
        f"bootstrap draws {settings['bootstrap_replicates']:,} resamples of physical shots within strata.",
        r"\subsection{Locked results}",
        f"Selection retained {selected}, with {comparator} as the locked comparator. Their selection "
        f"penalized entry losses were {score(selection_loss[selected])} and {score(selection_loss[comparator])}. "
        f"{gate_result} The blind equal-core-stratum losses were {score(loss[selected])} and "
        f"{score(loss[comparator])}. The gain, defined as comparator loss minus selected loss, was "
        f"{score(comparison['gain'])}, with paired 95\\% interval {score(comparison['interval_lo'])} to "
        f"{score(comparison['interval_hi'])}. {blind_gate}",
        r"The empirical coverage of nominal 95\% core regions was " + " and ".join(coverage) + ". "
        r"The nominal locations substantially undercovered in this benchmark. The selected model's "
        r"lower entry loss supports its use as a reference event forecast under the tested assumptions. "
        r"Its nominal location regions have much weaker calibration.",
        latex_table(blind, models, conditional),
        r"Figure~\ref{fig:F5} shows event reliability and the frequency of numerical failures and point "
        r"abstentions. Matched, pooled single-factor stress, combined stress, and challenge are shown "
        r"separately. Figure~\ref{fig:F6} reports joint coverage at nominal 50\%, 80\%, and 95\%, "
        r"with crossing error on the common valid cases. Sparse reliability bins and unsupported "
        r"comparisons are marked in the figure evidence.",
        "\n".join([r"\begin{figure}[htbp]", r"\centering",
                   r"\includegraphics[width=\linewidth]{figures/F5.pdf}",
                   r"\caption{F5. " + tex(captions["F5"]) + "}",
                   r"\label{fig:F5}", r"\end{figure}"]),
        "\n".join([r"\begin{figure}[htbp]", r"\centering",
                   r"\includegraphics[width=\linewidth]{figures/F6.pdf}",
                   r"\caption{F6. " + tex(captions["F6"]) + "}",
                   r"\label{fig:F6}", r"\end{figure}"]),
    ]) + "\n"


def paper_outputs(release, root, output, team_number):
    if not re.fullmatch(r"\d+", str(team_number)):
        raise ValueError("The registered team number must contain only digits")
    run_id = release["run_id"]
    selection, blind = (read_json(root / f"{split}-results.json") for split in ("selection", "blind"))
    protocol = read_json(root / "protocol.json")
    models = release["selected_model"], release["comparator_model"]
    if any(report["run_id"] != run_id or (report["selected_model"], report["comparator_model"]) != models
           for report in (selection, blind)):
        raise ValueError("Paper inputs differ from the release ID or locked model pair")
    selected, comparator = models
    captions = {}
    manifest_fields = ("asset_id", "run_id", "population", "condition", "units", "caption")
    for row in read_rows(root / "figures" / "figures_manifest.csv", manifest_fields):
        if row["run_id"] != run_id:
            raise ValueError("Paper figure does not belong to the release")
        if row["asset_id"] in ("F5", "F6"):
            captions[row["asset_id"]] = (root / "figures" / row["caption"]).read_text(encoding="utf-8").strip()
    conditional = {}
    if (root / "blind-conditional.csv").is_file():
        for row in read_rows(root / "blind-conditional.csv", ("run_id", "stratum", "model_id")):
            if row["run_id"] != run_id:
                raise ValueError("Conditional table has a foreign run ID")
            conditional[row["stratum"], row["model_id"]] = row
    section = wp3_section(release, selection, blind, protocol, conditional, captions)
    scores = [blind["models"][model]["core"]["entry_brier_failure_penalized"] for model in models]
    abstract = (
        f"% Team {team_number}; run {run_id}; blind-results.json models.{selected}.core and models.{comparator}.core\n"
        f"Across six equally weighted core strata of a locked synthetic blind benchmark, the failure-penalized "
        f"centre-entry Brier losses were {score(scores[0])} for {selected} and {score(scores[1])} for {comparator}."
    )
    if not selection["upgrade_adopted"]:
        abstract += " No aerodynamic candidate passed the preregistered selection gates."
    core = [blind["models"][model]["core"] for model in models]
    if all(row["coverage_95"] is not None and row["coverage_95"] < 0.90 for row in core):
        abstract += " Both models substantially undercovered with their nominal 95\\% crossing regions."
    discussion = (
        f"% Run {run_id}; protocol.json counts, launch, and stress; blind-results.json model denominators\n"
        "The synthetic validation measures performance for the frozen launch and stress distributions. "
        "The enriched challenge trials describe a separate population. Field calibration would require "
        "observed trajectories and measured tracking errors. The conditional region and crossing scores "
        "cover only cases whose true trajectory crosses the goal plane and whose forecasts support the "
        "corresponding statistic. Reported support counts are therefore part of the interpretation."
    )
    ai = (
        "% Contribution for sections/07-ai-report.tex. Team to merge with its verbatim records.\n"
        "OpenAI Codex assisted with the WP3 validation generator, locked scoring, verification, figure code, "
        "and the English validation section. The team verifies the numerical methods, released outputs and "
        "claims. Insert the original prompts and complete outputs retained for AI-assisted writing before submission."
    )
    output.mkdir()
    sections = output / "sections"
    sections.mkdir()
    (sections / "04-wp3-validation.tex").write_text(section, encoding="utf-8", newline="\n")
    for name, value in (("abstract", abstract), ("discussion", discussion), ("ai-note", ai)):
        (output / f"wp3-{name}.tex").write_text(value + "\n", encoding="utf-8", newline="\n")
    claims = []

    def cite(claim, artifact, selector, statistic, population, condition, unit):
        claims.append(dict(zip(CLAIM_FIELDS, (claim, run_id, "v1", "../" + artifact, selector, statistic,
                                               population, condition, unit, "WP3"))))

    cite("C-WP3-design", "protocol.json", "counts, solver, decision", "design and preregistration",
         "synthetic benchmark", "frozen design", "cases and SI units")
    cite("C-WP3-selection", "selection-results.json", "models, comparisons, selected_model, comparator_model",
         "selection scores and gates", "selection split", "equal core strata", "Brier loss")
    cite("C-WP3-blind-difference", "blind-results.json",
         f"comparisons[candidate={selected},comparator={comparator}]", "paired Brier gain and 95% interval",
         "blind core strata", "paired eligible truth", "Brier loss")
    for model in models:
        cite(f"C-WP3-blind-{model}", "blind-results.json", f"models.{model}.core, models.{model}.strata",
             "entry loss, truth counts, failure counts and region denominators", "blind split",
             "resolved truth or supported region as applicable", "Brier loss and cases")
    if conditional:
        cite("C-WP3-conditional", "blind-conditional.csv", "all blind strata for locked pair",
             "conditional location and time errors and availability", "blind split", "truth crossed plane", "m and s")
    for figure in ("F5", "F6"):
        cite(f"C-WP3-{figure}", "figures/figures_manifest.csv", f"asset_id={figure}", "figure evidence",
             "blind split", "see figure-specific conditions", "percentage and SI units")
    write_csv(output / "claims.csv", CLAIM_FIELDS, claims)
    if conditional:
        table_rows = []
        for (stratum, model), row in conditional.items():
            if model not in models:
                raise ValueError("T3 contains a model outside the blind lock")
            group = "core" if stratum == "core" else "strata"
            validation = blind["models"][model][group]
            evidence = validation if group == "core" else validation[stratum]
            table_rows.append(dict(row, entry_brier=evidence["entry_brier"], entry_brier_n=evidence["entry_brier_n"],
                                   penalized_entry_brier=evidence["entry_brier_failure_penalized"],
                                   n_entirely_invalid=evidence["n_entirely_invalid"],
                                   n_region_supported=evidence["n_region_supported"],
                                   n_region_hits=evidence["n_region_hits"], coverage_95=evidence["coverage_95"]))
        write_csv(output / "T3.csv", tuple(table_rows[0]), table_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--team-number", required=True)
    args = parser.parse_args()
    try:
        root = args.release
        release = read_json(root / "release.json")
        for name, expected in release["artifact_sha256"].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError(f"Unsafe release artifact path {name}")
            check_hash(path, expected)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.output.parent) as directory:
            stage = Path(directory) / "paper"
            paper_outputs(release, root, stage, args.team_number)
            stage.rename(args.output)
    except (OSError, ValueError, KeyError, csv.Error, StopIteration) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
