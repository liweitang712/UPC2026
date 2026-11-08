import csv
import json
import tempfile
import unittest
from pathlib import Path

from validation.generate_cases import CASE_PATH, HERE, PROTOCOL_PATH, read_json, sha256
from validation.locked_score import freeze_predictions, score_locked


class PredictionLockTests(unittest.TestCase):
    def test_scoring_checks_lock_and_truth_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            public = root / "public"
            private = root / "private"
            private.mkdir()
            (public / "selection").mkdir(parents=True)
            cases = "case_id,split,stratum,scenario_id\nfixture,selection,matched,nominal\n"
            public_cases = public / "selection" / "cases.csv"
            scoring_cases = private / "selection-cases.csv"
            truth = private / "selection-truth.csv"
            for path in (public_cases, scoring_cases):
                path.write_text(cases, encoding="utf-8")
            truth.write_text("case_id,event\nfixture,PLANE_GOAL\n", encoding="utf-8")
            manifest = {
                "run_id": "test-fixture",
                "protocol_sha256": sha256(PROTOCOL_PATH, text_source=True),
                "case_spec_sha256": sha256(CASE_PATH, text_source=True),
                "generator_sha256": sha256(HERE / "generate_cases.py", text_source=True),
                "splits": {"selection": {
                    "public_cases_sha256": sha256(public_cases),
                    "scoring_cases_sha256": sha256(scoring_cases),
                    "truth_sha256": sha256(truth),
                }},
            }
            (public / "freeze.json").write_text(json.dumps(manifest), encoding="utf-8")
            forecast, predictions = root / "config.json", root / "predictions.csv"
            models = read_json(PROTOCOL_PATH)["models"]
            forecast.write_text(json.dumps({"source_commit": "a" * 40,
                                            "models": {model: {"draws": 100} for model in models}}),
                                encoding="utf-8")
            predictions.write_text(
                "case_id,model_id,scenario_id,draw_id,weight,event\n"
                "fixture,B0,nominal,1,1,PLANE_GOAL\n", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                score_locked(private, public, "selection")
            freeze_predictions(private, public, "selection", predictions, forecast)
            locked_csv = private / "selection-predictions" / "predictions.csv"
            original = locked_csv.read_bytes()
            locked_csv.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "Freeze hash mismatch: predictions.csv"):
                score_locked(private, public, "selection")
            locked_csv.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "already has a prediction lock"):
                freeze_predictions(private, public, "selection", predictions, forecast)
            truth_original = truth.read_bytes()
            truth.write_bytes(truth_original + b"\n")
            with self.assertRaisesRegex(ValueError, "Freeze hash mismatch: selection-truth.csv"):
                score_locked(private, public, "selection")
            truth.write_bytes(truth_original)
            score_locked(private, public, "selection")
            with (private / "selection-entry-metrics.csv").open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), len(models) * 2)
            self.assertEqual(rows[0]["value"], "0.0")
