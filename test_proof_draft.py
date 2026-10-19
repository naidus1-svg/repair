"""Tests for the drafted proof rows (qc.py proof init / proof check). Standard library only; no model, no network."""

import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qc  # noqa: E402
import qc_test  # noqa: E402

INS = (
    "Rebuild the deck as closely as the renders allow: every text with its formatting.\n"
    "- Formatting, per character: a **seventh** each for size (±1 pt), bold, italic.\n"
    "Keep it short.\n"
)
HEAD = qc.PROOF_COLS


def write_sheet(path, rows, status=False):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEAD + ([qc.STATUS_COL] if status else []))
        w.writerows(rows)


def check_text(path, ids, instruction=INS):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = qc.proof_check(path, [(i, "", 0.1, 0.1) for i in ids], instruction)
    return rc, buf.getvalue().strip().splitlines()


QUOTE_OK = "Rebuild the deck as closely as the renders allow: every text with its formatting."
WHERE = "solution/deck.pptx"
OTHER = "Any deck that stays inside the stated tolerances would also pass this test, so it is fair."


class QuoteTests(unittest.TestCase):
    def test_the_sentence_is_an_exact_substring_of_the_instruction(self):
        got = qc.instruction_sentence(INS, "rebuild the DECK as closely as the renders allow")
        self.assertEqual(got, QUOTE_OK)
        self.assertIn(got, INS)

    def test_markdown_marks_in_the_instruction_stay_in_the_sentence(self):
        got = qc.instruction_sentence(INS, "Formatting, per character: a seventh each for size")  # reader dropped the ** marks
        self.assertIn("**seventh**", got)
        self.assertIn(got, INS)

    def test_a_quote_that_is_not_in_the_instruction_gives_none(self):
        self.assertIsNone(qc.instruction_sentence(INS, "Rebuild the deck exactly pixel for pixel"))
        self.assertIsNone(qc.instruction_sentence(INS, ""))
        self.assertIsNone(qc.instruction_sentence(INS, "too short"))

    def test_a_short_sentence_is_widened_to_its_line(self):
        ins = "First line.\nKeep it short. Then say more words here about the deck and the slides.\n"
        got = qc.instruction_sentence(ins, "Keep it short")
        self.assertEqual(got, "Keep it short. Then say more words here about the deck and the slides.")


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "solution").mkdir()
        (self.d / "solution" / "deck.pptx").write_text("x")
        self.need = [("a", "text a", 0.2, 0.2), ("b", "text b", 0.2, 0.2), ("c", "text c", 0.2, 0.2), ("d", "text d", 0.2, 0.2), ("e", "text e", 0.2, 0.2)]
        self.verdicts = {
            "a": {"blame": "SOLVER", "reason": "The instruction asks for it.", "instruction_quote": "as closely as the renders allow", "grader_quote": ""},
            "b": {"blame": "CRITERION", "reason": "The test wants more than asked.", "instruction_quote": "Keep it short", "grader_quote": "score below 1.0"},
            "c": {"blame": "MIXED", "reason": "Some runs missed.", "instruction_quote": "every text with its formatting", "grader_quote": ""},
            "d": {"blame": "UNCLEAR", "reason": "cannot tell", "instruction_quote": "", "grader_quote": ""},
            "e": {"blame": "SOLVER", "reason": "ok", "instruction_quote": "", "grader_quote": ""},
        }
        self.drafts = qc.draft_rows(self.need, self.verdicts, INS, self.d)

    def test_every_drafted_row_is_marked_draft(self):
        self.assertEqual(sorted(self.drafts), ["a", "b", "c", "e"])  # UNCLEAR and unknown tests are not drafted
        self.assertEqual({v[3] for v in self.drafts.values()}, {qc.DRAFT})

    def test_solver_verdict_is_a_real_miss_with_the_exact_sentence(self):
        quote, where, other, _ = self.drafts["a"]
        self.assertEqual(quote, QUOTE_OK)
        self.assertIn(quote, INS)
        self.assertTrue(other.startswith("REAL MODEL MISS"))
        self.assertIn("deck.pptx", where)

    def test_test_at_fault_verdicts_say_test_is_wrong_and_propose_a_fix(self):
        for cid in ("b", "c"):
            other = self.drafts[cid][2]
            self.assertTrue(other.startswith("TEST IS WRONG"), other)
            self.assertIn(f"Proposed fix: change the check {cid}", other)
        self.assertIn("score below 1.0", self.drafts["b"][2])
        self.assertIn("Keep requiring only what the instruction states", self.drafts["c"][2])

    def test_no_sentence_found_writes_no_quote_found(self):
        self.assertEqual(self.drafts["e"][0], qc.NO_QUOTE)

    def test_drafted_rows_hold_enough_words_for_the_existing_row_check(self):
        want = qc.norm(INS)
        self.assertEqual(qc.proof_bad({"instruction_quote": self.drafts["a"][0], "golden_location": self.drafts["a"][1], "other_valid_answer": self.drafts["a"][2]}, want), [])
        bad = qc.proof_bad({"instruction_quote": self.drafts["e"][0], "golden_location": self.drafts["e"][1], "other_valid_answer": self.drafts["e"][2]}, want)
        self.assertTrue(bad and "QUOTE" in bad[0])  # NO QUOTE FOUND keeps the row open


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp()) / qc.PROOF_FILE

    def test_only_confirmed_rows_are_complete_and_the_counts_follow_the_proof_line(self):
        write_sheet(self.p, [
            ["a", "t", "0.1", QUOTE_OK, WHERE, OTHER, "CONFIRMED"],
            ["b", "t", "0.1", QUOTE_OK, WHERE, OTHER, "DRAFT"],
            ["c", "t", "0.1", qc.NO_QUOTE, WHERE, OTHER, "DRAFT"],
            ["d", "t", "0.1", "", "", "", ""],
        ], status=True)
        rc, lines = check_text(self.p, "abcd")
        self.assertEqual(rc, 1)
        self.assertEqual(lines[-2], "PROOF: HOLD (3 open)")
        self.assertEqual(lines[-1], "PROOF ROWS: 1 CONFIRMED, 1 DRAFT, 2 OPEN")
        self.assertTrue(lines[0].startswith("OK: a"))
        self.assertTrue(lines[1].startswith("DRAFT"))

    def test_all_confirmed_is_complete(self):
        write_sheet(self.p, [["a", "t", "0.1", QUOTE_OK, WHERE, OTHER, "confirmed"], ["b", "t", "0.1", QUOTE_OK, WHERE, OTHER, "CONFIRMED"]], status=True)
        rc, lines = check_text(self.p, "ab")
        self.assertEqual((rc, lines[-2], lines[-1]), (0, "PROOF: COMPLETE", "PROOF ROWS: 2 CONFIRMED, 0 DRAFT, 0 OPEN"))

    def test_an_old_hand_filled_sheet_with_no_status_column_still_passes(self):
        write_sheet(self.p, [["a", "t", "0.1", QUOTE_OK, WHERE, OTHER], ["b", "t", "0.1", QUOTE_OK, WHERE, OTHER]], status=False)
        rc, lines = check_text(self.p, "ab")
        self.assertEqual((rc, lines[-2], lines[-1]), (0, "PROOF: COMPLETE", "PROOF ROWS: 2 CONFIRMED, 0 DRAFT, 0 OPEN"))

    def test_a_hand_filled_row_with_an_empty_status_cell_counts_as_confirmed(self):
        write_sheet(self.p, [["a", "t", "0.1", QUOTE_OK, WHERE, OTHER, ""]], status=True)
        self.assertEqual(check_text(self.p, "a")[0], 0)

    def test_an_unknown_status_word_is_open(self):
        write_sheet(self.p, [["a", "t", "0.1", QUOTE_OK, WHERE, OTHER, "maybe"]], status=True)
        rc, lines = check_text(self.p, "a")
        self.assertEqual((rc, lines[-1]), (1, "PROOF ROWS: 0 CONFIRMED, 0 DRAFT, 1 OPEN"))
        self.assertIn("UNKNOWN STATUS", lines[0])

    def test_a_confirmed_row_with_a_bad_quote_is_still_open(self):
        write_sheet(self.p, [["a", "t", "0.1", "words that the instruction never says at all, no", WHERE, OTHER, "CONFIRMED"]], status=True)
        self.assertEqual(check_text(self.p, "a")[1][-1], "PROOF ROWS: 0 CONFIRMED, 0 DRAFT, 1 OPEN")

    def test_the_proof_line_keeps_its_two_forms(self):
        write_sheet(self.p, [["a", "t", "0.1", QUOTE_OK, WHERE, OTHER]])
        self.assertRegex(check_text(self.p, "a")[1][-2], r"^PROOF: COMPLETE$")
        write_sheet(self.p, [["a", "t", "0.1", "", "", ""]])
        self.assertRegex(check_text(self.p, "a")[1][-2], r"^PROOF: HOLD \(\d+ open\)$")


class EndToEnd(unittest.TestCase):
    """proof init and proof check through qc.main, with the blame reader stubbed as in qc_test."""

    class H(qc_test.BlameTests):
        def runTest(self):
            pass

    def setUp(self):
        self.h = self.H()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)

    def sheet(self, rev):
        with open(rev / qc.PROOF_FILE, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_init_drafts_the_rows_and_marks_them_and_a_person_confirms(self):
        h = self.h
        rev = h.make(qc_test.SMALL)
        rc, out = h.go(rev)
        self.assertEqual(rc, 0, out)
        rows = {r["criterion_id"]: r for r in self.sheet(rev)}
        self.assertEqual({r[qc.STATUS_COL] for r in rows.values()}, {qc.DRAFT})
        big, small = rows["d1/t_big"], rows["d1/t_small"]
        self.assertTrue(big["other_valid_answer"].startswith("REAL MODEL MISS"))
        self.assertIn(big["instruction_quote"], qc_test.INSTRUCTION)  # exact substring
        self.assertTrue(small["other_valid_answer"].startswith("TEST IS WRONG"))
        self.assertIn("Proposed fix", small["other_valid_answer"])
        rc, out = h.go(rev, action="check")
        self.assertEqual((rc, qc_test.pline(out)), (1, "PROOF: HOLD (2 open)"))
        self.assertIn("PROOF ROWS: 0 CONFIRMED, 2 DRAFT, 0 OPEN", out)
        text = (rev / qc.PROOF_FILE).read_text(encoding="utf-8-sig").replace(",DRAFT", ",CONFIRMED")
        (rev / qc.PROOF_FILE).write_text(text, encoding="utf-8-sig")
        rc, out = h.go(rev, action="check")
        self.assertEqual((rc, qc_test.pline(out)), (0, "PROOF: COMPLETE"))
        self.assertIn("PROOF ROWS: 2 CONFIRMED, 0 DRAFT, 0 OPEN", out)

    def test_no_quote_found_leaves_the_row_open(self):
        h = self.h
        h.replies = {**h.replies, "t_big": {**qc_test.BLAME_REPLY["t_big"], "instruction_quote": ""}}
        rev = h.make({"t_big": qc_test.SMALL["t_big"]})
        h.go(rev)
        row = self.sheet(rev)[0]
        self.assertEqual(row["instruction_quote"], qc.NO_QUOTE)
        rc, out = h.go(rev, action="check")
        self.assertEqual(rc, 1)
        self.assertIn("PROOF ROWS: 0 CONFIRMED, 0 DRAFT, 1 OPEN", out)

    def test_no_blame_writes_the_old_blank_six_column_sheet(self):
        h = self.h
        rev = h.make(qc_test.SMALL)
        h.go(rev, "--no-blame")
        rows = list(csv.reader(io.StringIO((rev / qc.PROOF_FILE).read_text(encoding="utf-8-sig"))))
        self.assertEqual(rows[0], qc.PROOF_COLS)
        self.assertEqual([r[3:] for r in rows[1:]], [["", "", ""]] * (len(rows) - 1))

    def test_an_empty_row_in_an_existing_sheet_is_drafted_and_a_filled_row_is_not_touched(self):
        h = self.h
        rev = h.make(qc_test.SMALL)
        h.go(rev, "--no-blame")  # the blank sheet an older run left
        rows = list(csv.reader(io.StringIO((rev / qc.PROOF_FILE).read_text(encoding="utf-8-sig"))))
        rows[1][3:6] = ["my own quote", "my place", "my own answer"]  # a person already filled the first row
        with open(rev / qc.PROOF_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        first = rows[1][0]
        rc, out = h.go(rev)  # now with the blame reader
        self.assertEqual(rc, 0, out)
        by = {r["criterion_id"]: r for r in self.sheet(rev)}
        self.assertEqual(by[first]["instruction_quote"], "my own quote")
        self.assertEqual(by[first][qc.STATUS_COL], "")  # untouched, so it counts as confirmed
        other = next(k for k in by if k != first)
        self.assertEqual(by[other][qc.STATUS_COL], qc.DRAFT)

    def test_manage_prints_waived_for_a_python_verifier_task_and_does_not_fail(self):
        from unittest import mock

        h = self.h
        h.make(qc_test.SMALL, "dl/task-a")
        out_dir, buf = h.d / "out", io.StringIO()
        with mock.patch.object(qc, "run", lambda cmd, cwd=None: 3), redirect_stdout(buf):
            rc = qc.main(["--no-update", "manage", str(h.d / "dl"), "--out", str(out_dir), "--no-blame"])
        self.assertEqual(rc, 0)  # a waiver is reported, not a block
        self.assertIn("WAIVED: python verifier not parsable", (out_dir / "manager_summary.csv").read_text())
        self.assertIn("waived on 1", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
