import unittest
from random import Random

from figures.evidence import Forecast, Shot, paired_rmse, reliability_rows, summarize_draws


class FigureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.decision = {"joint_region_grid_m": 0.1, "minimum_conditional_effective_draws": 2}

    def test_grid_ties_are_included_and_missing_cells_are_excluded(self):
        rows = [{"draw_id": str(i), "event": "PLANE_GOAL", "weight": "0.5", "y_m": str(y), "z_m": "1"}
                for i, y in enumerate((0.02, 0.22))]
        self.assertEqual(summarize_draws(rows, (0.22, 1), self.decision).hits, (True, True, True))
        self.assertEqual(summarize_draws(rows, (-0.01, 1), self.decision).hits, (False, False, False))
        self.decision["minimum_conditional_effective_draws"] = 3
        self.assertIsNone(summarize_draws(rows, (0.22, 1), self.decision).hits)

    def test_unresolved_weight_is_not_an_exact_probability(self):
        rows = [
            {"draw_id": "1", "event": "PLANE_GOAL", "weight": "0.25", "y_m": "0", "z_m": "1"},
            {"draw_id": "2", "event": "PLANE_WIDE", "weight": "0.25", "y_m": "2", "z_m": "1"},
            {"draw_id": "3", "event": "NUMERICAL_FAILURE", "weight": "0.5", "y_m": "", "z_m": ""},
        ]
        forecast = summarize_draws(rows, (0, 1), self.decision)
        self.assertIsNone(forecast.entry)
        self.assertTrue(forecast.technical)
        self.assertTrue(forecast.resolved)
        self.assertEqual(forecast.squared_error, 1)

    def test_one_belongs_to_last_bin_and_sparse_counts_are_retained(self):
        shots = [Shot("matched", "PLANE_GOAL", {"B0": Forecast(False, True, 1, 1)}, {"B0": "available"})]
        rows = list(reliability_rows(shots, "matched", "B0", 10, 2))
        self.assertEqual(rows[9]["n"], 1)
        self.assertIsNone(rows[9]["observed_rate"])

    def test_paired_rmse_uses_only_common_supported_truth(self):
        a = Forecast(squared_error=1)
        b = Forecast(squared_error=4)
        shots = [
            Shot("matched", "PLANE_GOAL", {"B0": a, "B1": b}, {}),
            Shot("matched", "PLANE_WIDE", {"B0": a, "B1": Forecast()}, {}),
        ]
        decision = {"minimum_paired_truth_plane_cases": 1, "bootstrap_replicates": 40}
        row = paired_rmse(shots, "matched", ("B0", "B1"), decision, Random(1))
        self.assertEqual((row["n_truth_plane"], row["n_selected"], row["n_comparator"], row["n_paired"]),
                         (2, 2, 1, 1))
        self.assertEqual((row["delta"], row["lo"], row["hi"]), (-1, -1, -1))
