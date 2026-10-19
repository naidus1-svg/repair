import unittest
from verdict_guard import guard_verdict


class T(unittest.TestCase):
    def test_pass_with_major_open(self):
        v, n = guard_verdict("PASS", [{"id": "F1", "severity": "major", "status": "open"}])
        self.assertEqual(v, "HOLD"); self.assertIn("F1", n)

    def test_pass_with_rejected_minor(self):
        v, n = guard_verdict("pass", [{"id": "F2", "severity": "minor", "status": "rejected"}])
        self.assertEqual(v, "HOLD"); self.assertIn("F2", n)

    def test_pass_with_only_minor_open_stays(self):
        self.assertEqual(guard_verdict("PASS", [{"severity": "minor", "status": "open"}]), ("PASS", ""))

    def test_accepted_minor_stays(self):
        self.assertEqual(guard_verdict("Passed", [{"severity": "minor", "status": "accepted"}])[0], "Passed")

    def test_ready_and_send_words(self):
        f = [{"id": "X", "severity": "Major", "status": "accepted"}]
        self.assertEqual(guard_verdict("READY", f)[0], "HOLD")
        self.assertEqual(guard_verdict(" send ", f)[0], "HOLD")
        self.assertEqual(guard_verdict("PASSED", f)[0], "HOLD")

    def test_non_pass_verdicts_untouched(self):
        f = [{"severity": "major", "status": "open"}]
        self.assertEqual(guard_verdict("FAIL", f), ("FAIL", ""))
        self.assertEqual(guard_verdict("HOLD", f), ("HOLD", ""))

    def test_no_findings(self):
        self.assertEqual(guard_verdict("PASS", []), ("PASS", ""))
        self.assertEqual(guard_verdict("PASS", None), ("PASS", ""))

    def test_note_names_every_blocker(self):
        fs = [{"id": "A", "severity": "major", "status": "open"}, {"id": "B", "severity": "minor", "status": "rejected"}]
        n = guard_verdict("PASS", fs)[1]
        self.assertIn("A", n); self.assertIn("B", n)


if __name__ == "__main__":
    unittest.main()
