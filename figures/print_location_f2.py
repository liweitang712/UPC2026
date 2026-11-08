"""Replay the frozen location-v2 supplied kick and render a print-size F2."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.text import Text
import numpy as np

from figures import render_location_v2 as location
from inference import report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    if output.is_relative_to(location.RELEASE.parent.resolve()):
        parser.error("choose an output directory outside the releases tree")
    output.mkdir(parents=True, exist_ok=True)
    source = location.RELEASE / "T2.json"
    frozen = location.read_json(source)
    original_save = location.save


    def save(fig, folder, name):
        if name != "F2":
            return original_save(fig, folder, name)
        fig.set_size_inches(6.5, 3.9)
        fig.subplots_adjust(left=.10, right=.86, bottom=.23, top=.89)
        ax, bar = fig.axes
        ax.set_title("Crossing density given plane arrival")
        legend = ax.get_legend()
        replacements = {"Joint 95% grid region | plane": "Joint 95% region",
                        "Mode | goal": "Mode given entry"}
        for text in legend.get_texts():
            text.set_text(replacements.get(text.get_text(), text.get_text()))
        bar._colorbar.solids.set_rasterized(False)
        for text in fig.findobj(Text):
            text.set_fontsize(max(text.get_fontsize(), 10))
        fig.texts[0].set_position((.1, .055))
        for ext in ("pdf", "png"):
            fig.savefig(output / f"F2.{ext}", dpi=170,
                        metadata={"CreationDate": None} if ext == "pdf" else None)
        plt.close(fig)


    report.save = save
    location.RELEASE = output
    location.FIGURES = output
    with plt.rc_context({"font.size": 10, "pdf.fonttype": 42}):
        location.supplied_shot()
    new = location.read_json(output / "T2.json")
    for key in ("p_reach", "p_goal", "p_clearance_goal", "p_failure", "entry_mode_yz_m",
                "entry_mode_check_yz_m", "f2_off_panel_weight"):
        if not np.allclose(new[key], frozen[key], rtol=0, atol=1e-9):
            raise ValueError(f"F2 replay does not match frozen {key}")
    if new["plane_intervals"]["joint_region"] != frozen["plane_intervals"]["joint_region"]:
        raise ValueError("F2 replay does not match the frozen joint region")
    print(json.dumps({"T2.json": sha256(source.read_bytes()).hexdigest(),
                      "F2.pdf": sha256((output / "F2.pdf").read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
