import json, os, tempfile, unittest
from headroom_check import headroom_warning


def make_task(runs, details_only=False):
    """runs: list of (model, reward, checks[(name, score, weight)])"""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "runs"))
    for i, (model, reward, checks) in enumerate(runs):
        run = {"_kind": "solver", "_model": model, "status": "PASSED" if reward >= 1 else "FAILED",
               "aggregate_reward": reward,
               "test_results": {"tests": [] if details_only else
                                [{"name": n, "score": s, "weight": w} for n, s, w in checks]}}
        with open(os.path.join(d, "runs", "%d.json" % (100 + i)), "w") as f:
            json.dump(run, f)
        if details_only:
            det = {"cat": {"criteria": [{"name": n, "value": s, "weight": w} for n, s, w in checks]}}
            with open(os.path.join(d, "runs", "%d.reward-details.json" % (100 + i)), "w") as f:
                json.dump(det, f)
    return d


def four(scores):
    return [("c%d" % i, s, 0.25) for i, s in enumerate(scores)]


class T(unittest.TestCase):
    def test_mean_095(self):
        runs = [("a", 0.95, four([1, 1, 1, 0.8])), ("b", 0.95, four([1, 1, 1, 0.8]))] * 4
        r = headroom_warning(make_task(runs))
        self.assertTrue(r["warning"]); self.assertIn("0.95", r["reason"])
        self.assertTrue(r["line"].startswith("HEADROOM WARNING: "))

    def test_five_runs_two_models(self):
        runs = [("a", 0.5, four([1, 0, 1, 0])), ("b", 0.4, four([0, 1, 0, 1]))] * 2 + [("a", 0.5, four([1, 0, 1, 0]))]
        r = headroom_warning(make_task(runs))
        self.assertEqual((r["runs"], r["models"]), (5, 2))
        self.assertIn("only 5 run(s)", r["reason"])

    def test_single_check_90_percent(self):
        # c0 loses 0.9 of the failing weight, c1 loses 0.1
        runs = []
        for i in range(8):
            m = "a" if i % 2 else "b"
            runs.append((m, 0.5, [("c0", 0.0, 0.45), ("c1", 0.9 if i == 0 else 1.0, 0.05), ("c2", 1.0, 0.5)]))
        r = headroom_warning(make_task(runs))
        self.assertGreater(r["top_check_share"], 0.8)
        self.assertIn("one check carries", r["reason"])

    def test_clean_mid_range(self):
        runs = []
        for i in range(8):
            m = "a" if i % 2 else "b"
            s = [(1, 0, 1, 0), (0, 1, 0, 1)][i % 2] if False else None
            checks = four([i % 2, (i + 1) % 2, 1 if i % 4 < 2 else 0, 0 if i % 4 < 2 else 1])
            runs.append((m, 0.5, checks))
        r = headroom_warning(make_task(runs))
        self.assertFalse(r["warning"]); self.assertEqual(r["line"], "training signal: ok")
        self.assertAlmostEqual(r["mean"], 0.5)

    def test_missing_run_files(self):
        d = tempfile.mkdtemp()  # no runs/ directory at all
        r = headroom_warning(d)
        self.assertEqual(r["runs"], 0); self.assertTrue(r["warning"])
        self.assertIn("no usable solver runs", r["reason"])

    def test_one_model_only(self):
        runs = [("a", 0.5, four([1, 0, 1, 0])), ("a", 0.4, four([0, 1, 0, 1]))] * 4
        r = headroom_warning(make_task(runs))
        self.assertEqual(r["models"], 1); self.assertIn("1 model(s)", r["reason"])

    def test_zero_failing_weight(self):
        runs = [("a" if i % 2 else "b", 1.0, four([1, 1, 1, 1])) for i in range(8)]
        r = headroom_warning(make_task(runs))
        self.assertIsNone(r["top_check_share"])
        self.assertEqual(r["always_pass_weight_share"], 1.0)
        self.assertTrue(r["warning"])  # mean 1.0

    def test_no_runs(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "runs"))
        r = headroom_warning(d)
        self.assertEqual((r["runs"], r["models"]), (0, 0)); self.assertTrue(r["warning"])

    def test_oracle_and_nop_ignored(self):
        d = make_task([("a", 0.5, four([1, 0, 1, 0]))])
        for kind, i in (("oracle", 900), ("nop", 901)):
            with open(os.path.join(d, "runs", "%d.json" % i), "w") as f:
                json.dump({"_kind": kind, "_model": "", "status": "PASSED", "aggregate_reward": 1.0}, f)
        self.assertEqual(headroom_warning(d)["runs"], 1)

    def test_exception_run_skipped_and_details_fallback(self):
        runs = [("a" if i % 2 else "b", 0.5, four([1, 0, 1, 0])) for i in range(6)]
        d = make_task(runs, details_only=True)
        with open(os.path.join(d, "runs", "950.json"), "w") as f:
            json.dump({"_kind": "solver", "_model": "a", "status": "EXCEPTION", "aggregate_reward": 0.0}, f)
        r = headroom_warning(d)
        self.assertEqual(r["runs"], 6)
        self.assertIsNotNone(r["always_pass_weight_share"])

    def test_spread_between_repeats(self):
        runs = [("a", 0.2, four([1, 0, 0, 0])), ("a", 0.6, four([1, 1, 1, 0])), ("b", 0.4, four([1, 1, 0, 0]))] * 2
        r = headroom_warning(make_task(runs))
        self.assertAlmostEqual(r["spread"], (0.4 + 0.0) / 2)

    def test_corrupt_run_file(self):
        d = make_task([("a", 0.5, four([1, 0, 1, 0]))])
        with open(os.path.join(d, "runs", "777.json"), "w") as f:
            f.write("{not json")
        self.assertEqual(headroom_warning(d)["runs"], 1)


if __name__ == "__main__":
    unittest.main()
