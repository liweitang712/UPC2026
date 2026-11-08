import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validation.locked_score import freeze_predictions, verify_lock


class FigureStatusLockTests(unittest.TestCase):
    def test_blind_lock_requires_point_status_and_detects_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            private = Path(folder)
            selection = private / "selection-predictions"
            selection.mkdir()
            forecast = private / "forecast.json"
            config = {"source_commit": "a" * 40, "models": {"B0": {"draws": 100}, "B1": {"draws": 100}}}
            forecast.write_text(json.dumps(config), encoding="utf-8")
            (selection / "forecast.json").write_bytes(forecast.read_bytes())
            decision = private / "selection-decision.json"
            decision.write_text("{}", encoding="utf-8")
            predictions, status = private / "incoming.csv", private / "status.csv"
            predictions.write_text("prediction fixture", encoding="utf-8")
            status.write_text("case_id,model_id,scenario_id,point_status\n", encoding="utf-8")
            manifest = {"run_id": "test", "splits": {"blind": {"public_cases_sha256": "case-hash"}}}
            with patch("validation.locked_score.verify_inputs", return_value=manifest), patch(
                "validation.locked_score.selection_record", return_value=(decision, ("B0", "B1"))
            ):
                with self.assertRaisesRegex(ValueError, "requires point status"):
                    freeze_predictions(private, private, "blind", predictions, forecast)
                freeze_predictions(private, private, "blind", predictions, forecast, status)
            lock = private / "blind-predictions"
            verify_lock(lock, "blind", manifest)
            (lock / "point-status.csv").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "point-status.csv"):
                verify_lock(lock, "blind", manifest)
