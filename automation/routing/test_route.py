#!/usr/bin/env python3
"""Tests for route.py and its use in step 1 and step 3. No model calls.

Run: python3 automation/routing/test_route.py
"""

import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import route  # noqa: E402


def load(name, rel):
    path = os.path.join(AUTO, rel)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mr = load("manager_read", os.path.join("manager-read", "manager_read.py"))
tr = load("task_read", os.path.join("task-read", "task_read.py"))


class Table(unittest.TestCase):
    def test_every_step1_rule_has_a_route(self):
        for rule in tr.RULE_TEXT:
            self.assertIn(rule, route.STEP1_RULE_ROUTE, rule)

    def test_every_step1_test_has_a_route(self):
        for t in tr.TESTN:
            self.assertIn(t, route.STEP1_TEST_ROUTE, t)

    def test_every_step3_type_has_a_route(self):
        for t in mr.TYPE_TEXT:
            self.assertIn(t, route.STEP3_TYPE_ROUTE, t)

    def test_only_valid_routes_in_tables(self):
        for table in (
            route.STEP1_RULE_ROUTE,
            route.STEP1_TEST_ROUTE,
            route.STEP3_TYPE_ROUTE,
        ):
            for key, (r, why) in table.items():
                self.assertIn(r, route.ROUTES, key)
                self.assertTrue(why.strip(), key)

    def test_unknown_id_goes_to_fix_with_a_note(self):
        r, why = route.default_route("step3_type", "ZZ")
        self.assertEqual(r, "FIX")
        self.assertIn("re-routes", why)


class Easing(unittest.TestCase):
    def test_easing_phrases_are_caught(self):
        for text in (
            "loosen or delete the criterion",
            "Remove the check, or add the requirement to the instruction.",
            "accept equivalent wording and widen the band",
            "drop the criterion",
            "add a hint to the instruction",
            "increase the tolerance",
        ):
            self.assertTrue(route.easing_risk(text), text)

    def test_tightening_is_not_flagged(self):
        for text in (
            "Tighten the criterion so an empty answer cannot earn it.",
            "Put the values in the check text.",
            "",
        ):
            self.assertFalse(route.easing_risk(text), text)

    def test_the_texts_authors_read_no_longer_tell_them_to_ease_the_task(self):
        for rule, (what, fix) in tr.RULE_TEXT.items():
            self.assertFalse(route.easing_risk(fix), "RULE_TEXT %s: %s" % (rule, fix))
        for t, fix in tr.FIX_BY_TEST.items():
            self.assertFalse(route.easing_risk(fix), "FIX_BY_TEST %s: %s" % (t, fix))


class Normalize(unittest.TestCase):
    def test_free_pass_goes_to_qc(self):
        it = route.normalize_item(
            {"type": "O", "fix": "Tighten the criterion so an empty answer fails."},
            "step3_type",
            "O",
        )
        self.assertEqual(it["route"], "FIX")
        self.assertEqual(it["difficulty_effect"], "none")

    def test_a_fix_that_eases_the_task_is_kept_hard(self):
        it = route.normalize_item(
            {"type": "O", "fix": "loosen the criterion"}, "step3_type", "O"
        )
        self.assertEqual(it["route"], "KEEP_HARD")
        self.assertTrue(it["easing_risk"])
        self.assertIn("easier", it["route_why"])

    def test_domain_items_go_to_the_expert(self):
        for t in ("A1", "U", "A7", "C"):
            it = route.normalize_item({"type": t, "fix": "ask"}, "step3_type", t)
            self.assertEqual(it["route"], "EXPERT", t)

    def test_a_valid_route_set_by_the_reader_is_kept(self):
        it = route.normalize_item(
            {"type": "O", "route": "expert", "fix": "x"}, "step3_type", "O"
        )
        self.assertEqual(it["route"], "EXPERT")

    def test_a_bad_route_is_replaced_by_the_table(self):
        it = route.normalize_item(
            {"type": "D", "route": "maybe", "fix": "x"}, "step3_type", "D"
        )
        self.assertEqual(it["route"], "FIX")

    def test_summary_counts(self):
        items = [
            {"route": "FIX"},
            {"route": "EXPERT"},
            {"route": "EXPERT"},
            {"route": "KEEP_HARD"},
        ]
        self.assertEqual(
            route.summary_line(items),
            "Who acts: 1 for our QC team, 2 for the domain expert, 1 keep hard.",
        )


def manager_result(items):
    return dict(
        task="t1",
        tab="EKW",
        n_criteria=3,
        n_reviews_read=0,
        verdict="SEND_BACK",
        reason="r",
        items=items,
        rejected_review_majors=[],
        advisory=[],
        coverage={},
        prompt_sha256="0" * 64,
        calls=1,
        seconds=1.0,
    )


class Step3Report(unittest.TestCase):
    def render(self, items):
        items = [route.normalize_item(x, "step3_type", x.get("type")) for x in items]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.md")
            mr.write_report(manager_result(items), p)
            return open(p, encoding="utf-8").read()

    def test_report_groups_by_who_acts(self):
        text = self.render(
            [
                {
                    "type": "O",
                    "criterion_id": "c1",
                    "fix": "Tighten c1.",
                    "problem": "p1",
                },
                {
                    "type": "A1",
                    "criterion_id": "c2",
                    "fix": "Correct the golden value.",
                    "problem": "p2",
                    "expert_question": "Is 4.2 the right rate?",
                },
                {
                    "type": "O",
                    "criterion_id": "c3",
                    "fix": "loosen the criterion",
                    "problem": "p3",
                },
            ]
        )
        self.assertIn(
            "Who acts: 1 for our QC team, 1 for the domain expert, 1 keep hard.", text
        )
        self.assertIn("Our QC team fixes these", text)
        self.assertIn("Send these to the domain expert", text)
        self.assertIn("Keep hard: do not change these", text)
        self.assertIn("Question for the domain expert: Is 4.2 the right rate?", text)
        self.assertIn(
            "NOT applied by default because it would make the task easier: loosen the criterion",
            text,
        )
        self.assertNotIn("What to change: loosen the criterion", text)

    def test_report_without_items_still_renders(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.md")
            res = manager_result([])
            res["verdict"] = "APPROVE"
            mr.write_report(res, p)
            self.assertIn("No items", open(p, encoding="utf-8").read())


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=1)
    n = r.result.testsRun
    bad = len(r.result.failures) + len(r.result.errors)
    print("TESTS %d/%d passed" % (n - bad, n))
    sys.exit(1 if bad else 0)
