"""Render letter-size derivatives from the frozen location release."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.text import Text
import numpy as np

from figures import render_location_v2 as location
from figures.render_public import f1
from inference import report
from physics import load_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    release = location.RELEASE
    case_file = release / "../upc2026-wp3-v1/case.json"
    trace_file = release / "figures/F1-traces.json"
    f3_source = location.QA / "public-scenarios/F3-data.json"

    heights = {"F1": 4.8, "F3": 3.3, "F5": 3.7, "F6": 3.15}

    def save(fig, unused, name):
        fig.set_size_inches(6.5, heights[name])
        fig.set_layout_engine("constrained")
        if name == "F1":
            legend = fig.axes[0].get_legend()
            legend.get_texts()[0].set_text("Launch and observations")
        if name == "F3":
            left, right = fig.axes
            left.get_legend().get_texts()[1].set_text("Aero, velocity removed")
            for text in right.get_legend().get_texts():
                text.set_text(text.get_text().replace(": PLANE_", " / ").replace("_", " ").lower().capitalize())
        if name == "F6":
            fig.axes[1].set_xlabel("Paired energy difference (m)")
        for text in fig.findobj(Text):
            text.set_fontsize(max(text.get_fontsize(), 10))
        for ext in ("pdf", "png"):
            fig.savefig(args.output / f"{name}.{ext}", dpi=170,
                        metadata={"CreationDate": None} if ext == "pdf" else None)
        plt.close(fig)

    with plt.rc_context({"font.size": 10, "pdf.fonttype": 42}):
        save(f1(location.read_json(case_file), location.read_json(trace_file)), args.output, "F1")
        report.save = save
        replayed = report.figure3(args.output, load_case())
        original = location.read_json(f3_source)
        for key in ("singular_values", "projected_aero_singular_values"):
            if not np.allclose(replayed[key], original[key], rtol=0, atol=1e-10):
                raise ValueError(f"F3 diagnostic differs from released {key}")
        for new, prior in zip(replayed["pair"], original["pair"], strict=True):
            if any(not np.isclose(new["event"][axis], prior["event"][axis], rtol=0, atol=1e-10)
                   for axis in ("y_m", "z_m")):
                raise ValueError("F3 trajectory differs from release")
        location.save = save
        location.validation_figures()
    inputs = (case_file, trace_file, f3_source, release / "T3.csv", release / "paired-energy.csv")
    manifest = {
        "run_id": "upc2026-location-v2",
        "inputs_sha256": {
            path.resolve().relative_to(Path.cwd()).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in inputs
        },
        "pdf_sha256": {
            name: sha256((args.output / f"{name}.pdf").read_bytes()).hexdigest() for name in heights
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
