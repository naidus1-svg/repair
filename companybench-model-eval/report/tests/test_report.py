"""Unit tests: counting rule, masking, classifier, per-run measures, rule-based modes. Standard library only.

python -m unittest discover -s tests          (run from companybench-model-eval/report)
"""

import csv
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cbr import modes, runmetrics as RM, scrub, selection  # noqa: E402
from cbr.classify import classify, mask  # noqa: E402

FIELDS = [
    "model_id",
    "view",
    "alias",
    "task_id",
    "slot",
    "eval_id",
    "run_id",
    "status",
    "reward",
    "timed_out",
]


def write_csv(rows):
    fd, p = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in FIELDS})
    return p


def row(alias, slot, run_id, to=0, view="main"):
    return dict(
        model_id=1,
        view=view,
        alias=alias,
        task_id=100 + int(alias[1:]),
        slot=slot,
        eval_id=run_id + 5,
        run_id=run_id,
        status="FAILED" if to else "PASSED",
        reward=0,
        timed_out=to,
    )


class Selection(unittest.TestCase):
    def test_first_three_and_reruns_in_order(self):
        main = [row("T01", s, 10 + s, to=int(s in (1, 3))) for s in (1, 2, 3, 4)] + [
            row("T02", s, 20 + s) for s in (1, 2, 3)
        ]
        lng = [row("T01", 1, 91, view="long"), row("T01", 2, 92, view="long")]
        s = selection.select("Zed", write_csv(main), write_csv(lng))
        self.assertEqual(
            [r["key"] for r in s["runs"]],
            [
                "T01-zed-1",
                "T01-zed-2",
                "T01-zed-3",
                "T02-zed-1",
                "T02-zed-2",
                "T02-zed-3",
            ],
        )
        self.assertEqual(
            [(r["key"], r["replaces"], r["run_id"]) for r in s["long"]],
            [("T01-zed-1L", "T01-zed-1", 91), ("T01-zed-3L", "T01-zed-3", 92)],
        )
        self.assertEqual(s["pending"], [])

    def test_timeout_without_rerun_is_pending(self):
        main = [row("T01", s, 10 + s, to=int(s == 2)) for s in (1, 2, 3)]
        s = selection.select("Zed", write_csv(main), None)
        self.assertEqual(s["pending"], ["T01-zed-2"])

    def test_fewer_than_three_is_reported(self):
        s = selection.select(
            "Zed", write_csv([row("T01", 1, 11), row("T01", 2, 12)]), None
        )
        self.assertEqual(len(s["problems"]), 1)


class Masking(unittest.TestCase):
    G = json.dumps(
        {
            "content": "verifier 1/1 a [file_check] FAIL 0.1s\n"
            + json.dumps(
                {"rubric": {"items": [{"expected": "12345 accounts", "name": "x"}]}}
            )
        }
    )

    def test_values_found_after_check_lines(self):
        nums, strs = scrub.task_values([self.G])
        self.assertIn("12345", nums)

    def test_scrub_masks_value_email_url_name(self):
        nums, strs = scrub.task_values([self.G])
        out = scrub.scrub(
            "found 12345 and 777 for Jane Smith at a@b.com see http://x.y/z", nums, strs
        )
        self.assertNotIn("12345", out)
        self.assertIn("777", out)
        for tag in ("[name]", "[email]", "[url]"):
            self.assertIn(tag, out)

    def test_strict_masks_every_larger_number(self):
        out = scrub.scrub("rows 777 and 12 and 3.5", set(), [], strict=True)
        self.assertEqual(out, "rows [value] and 12 and [value]")


class Classifier(unittest.TestCase):
    def test_classes(self):
        sc = {}
        self.assertEqual(classify("", sc)[0], "wait")
        self.assertEqual(classify("ls -la /workspace", sc)[0], "list directory")
        self.assertEqual(classify("cat notes.txt", sc)[0], "read file")
        self.assertEqual(classify("python3 -c 'print(1)'", sc)[0], "run script")
        self.assertEqual(
            classify("python3 mcp_client.py slack call chat_post_message x", sc)[0],
            "send message",
        )

    def test_mask_removes_literals(self):
        m = mask("python3 x.py 'secret value' 123456 a@b.com https://u.v/w")
        for bad in ("secret value", "123456", "a@b.com", "https://u.v/w"):
            self.assertNotIn(bad, m)


def step(i, ts, msg="", keys="", tokens=100, obs=""):
    return {
        "source": "agent",
        "timestamp": "2026-01-01T00:%02d:00Z" % ts,
        "message": msg,
        "metrics": {"completion_tokens": tokens},
        "tool_calls": (
            [{"function_name": "bash_command", "arguments": {"keystrokes": keys}}]
            if keys is not None
            else []
        ),
        "observation": {"results": [{"content": obs}]},
    }


class Measures(unittest.TestCase):
    def run_of(self, steps):
        return {
            "trajectory": {"steps": steps},
            "execution_profile": {
                "agent_execution": {"started_at": "2026-01-01T00:00:00Z"}
            },
        }

    def test_why_counts_error_retry_recheck(self):
        r = self.run_of(
            [
                step(1, 1, keys="ls", obs="Traceback (most recent call last)"),
                step(2, 2, msg="Wait, let me check", keys="ls /x"),
                step(3, 3, keys="ls /x"),
            ]
        )
        c = RM.why_counters(r)
        self.assertEqual(
            (c["steps"], c["error_out"], c["retry"], c["recheck"], c["repeat"]),
            (3, 1, 1, 1, 1),
        )

    def test_long_turn_and_lead(self):
        r = self.run_of(
            [
                step(
                    1,
                    1,
                    keys="cat <<EOF > a.py\nSELECT 1\nEOF\npython3 a.py",
                    tokens=9000,
                ),
                step(2, 2, keys="python3 mcp_client.py slack call chat_post_message x"),
            ]
        )
        lt = RM.longturn_run(r)
        self.assertEqual(len(lt["longs"]), 1)
        self.assertIsNotNone(lt["lead"])

    def test_checks_counts_without_names(self):
        g = {
            "content": "verifier 1/3 aaa [file_check] PASS 0.1s\nverifier 2/3 bbb [file_check] FAIL 0.1s\nverifier 3/3 ccc [file_check] ERROR 0.1s"
        }
        self.assertEqual(RM.checks(g), [1, 3])


class Modes(unittest.TestCase):
    def test_timeout_modes(self):
        run = {"timeout": True}
        self.assertEqual(
            modes.mode_of(
                run,
                {
                    "steps": 10,
                    "tok8_share_time_x1000": 400,
                    "recheck": 0,
                    "after_first_delivery": 0,
                },
                {"cycles": []},
                [],
            ),
            modes.M_LONG,
        )
        self.assertEqual(
            modes.mode_of(
                run,
                {
                    "steps": 10,
                    "tok8_share_time_x1000": 0,
                    "recheck": 3,
                    "after_first_delivery": 0,
                },
                {"cycles": []},
                [],
            ),
            modes.M_RECHECK,
        )
        self.assertEqual(
            modes.mode_of(
                run,
                {
                    "steps": 10,
                    "tok8_share_time_x1000": 0,
                    "recheck": 0,
                    "after_first_delivery": 0,
                },
                {"cycles": []},
                [],
            ),
            modes.M_ORDINARY,
        )

    def test_finished_modes(self):
        run = {"timeout": False}
        w0 = {
            "steps": 10,
            "tok8_share_time_x1000": 0,
            "recheck": 0,
            "after_first_delivery": 0,
        }
        self.assertEqual(modes.mode_of(run, w0, {"cycles": []}, []), modes.M_NODELIVER)
        w1 = dict(w0, after_first_delivery=2)
        steps = [
            [1, 1, "send message", [], 1, 1, 1, 0, "cmd a"],
            [2, 2, "send message", [], 1, 1, 1, 0, "cmd a"],
        ]
        self.assertEqual(modes.mode_of(run, w1, {"cycles": []}, steps), modes.M_REPEAT)
        self.assertEqual(
            modes.mode_of(run, w1, {"cycles": []}, steps[:1]), modes.M_WRONG
        )


if __name__ == "__main__":
    unittest.main()
