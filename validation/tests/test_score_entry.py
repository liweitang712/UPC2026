import tempfile
import unittest
from pathlib import Path

from validation.score_entry import entry_loss, score_entry


def draw(draw_id, event, weight):
    return {"draw_id": draw_id, "event": event, "weight": str(weight)}


class EntryScoreTests(unittest.TestCase):
    def test_unresolved_draws_use_worse_endpoint(self):
        draws = [draw("a", "PLANE_GOAL", 0.2), draw("b", "PLANE_WIDE", 0.5),
                 draw("c", "NUMERICAL_FAILURE", 0.3)]
        for outcome, expected in ((True, 0.64), (False, 0.25)):
            with self.subTest(outcome=outcome):
                loss, exact, failed = entry_loss(draws, outcome)
                self.assertAlmostEqual(loss, expected)
                self.assertIsNone(exact)
                self.assertTrue(failed)

    def test_missing_and_invalid_bundles_receive_maximum_loss(self):
        goal = draw("a", "PLANE_GOAL", 0.5)
        for draws in ([], [goal], [goal, goal], [draw("a", "PLANE_GOAL", "nan")],
                      [draw("a", "unknown", 1)], [draw("a", "NUMERICAL_FAILURE", 1)]):
            with self.subTest(draws=draws):
                self.assertEqual(entry_loss(draws, False), (1.0, None, True))

    def test_case_and_forecast_denominators(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            cases, truth, predictions = (path / name for name in ("cases", "truth", "predictions"))
            cases.write_text(
                "case_id,split,stratum,scenario_id\n"
                "a,blind,matched,nominal\nb,blind,matched,nominal\n"
                "c,blind,matched,nominal\nd,selection,matched,nominal\n",
                encoding="utf-8",
            )
            truth.write_text(
                "case_id,event\na,PLANE_GOAL\nb,GROUND_FIRST\nc,NUMERICAL_FAILURE\n",
                encoding="utf-8",
            )
            predictions.write_text(
                "case_id,model_id,scenario_id,draw_id,weight,event\n"
                "a,B0,nominal,1,0.75,PLANE_GOAL\na,B0,nominal,2,0.25,NO_REACH\n",
                encoding="utf-8",
            )
            rows = list(score_entry(cases, truth, predictions, run_id="fixture", split="blind",
                                    models=("B0", "B1")))
            penalized, exact, missing_model, missing_exact = rows
            self.assertEqual((penalized["n_total"], penalized["n_eligible"]), (3, 2))
            self.assertEqual((penalized["n_scored"], penalized["n_failed"]), (2, 1))
            self.assertEqual(penalized["value"], (0.0625 + 1.0) / 2)
            self.assertEqual((exact["value"], exact["n_scored"]), (0.0625, 1))
            self.assertEqual((missing_model["value"], missing_model["n_failed"]), (1.0, 2))
            self.assertEqual((missing_exact["value"], missing_exact["n_scored"]), ("", 0))

    def test_frozen_split_requires_truth_and_expected_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            cases, truth, predictions = (path / name for name in ("cases", "truth", "predictions"))
            cases.write_text("case_id,split,stratum,scenario_id\na,blind,matched,nominal\n",
                             encoding="utf-8")
            truth.write_text("case_id,event\n", encoding="utf-8")
            predictions.write_text(
                "case_id,model_id,scenario_id,draw_id,weight,event\n"
                "a,B0,other,1,1,PLANE_GOAL\n", encoding="utf-8",
            )
            options = {"run_id": "fixture", "split": "blind", "models": ("B0",)}
            with self.assertRaisesRegex(ValueError, "cover the selected split"):
                list(score_entry(cases, truth, predictions, **options))
            truth.write_text("case_id,event\na,PLANE_GOAL\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected model or scenario"):
                list(score_entry(cases, truth, predictions, **options))
