"""Training-signal ("too easy") check. Stdlib only. Report only, never rejects a task.

Reads <task_dir>/runs/<id>.json (solver runs: _kind == "solver", status PASSED or FAILED,
aggregate_reward set). Oracle and no-op runs are ignored. Per-check data comes from
test_results.tests (name, score, weight); if a run has none, from <id>.reward-details.json.
"""
import json
import os
import sys

MEAN_LIMIT = 0.9
MIN_RUNS = 6
MIN_MODELS = 2
TOP_CHECK_LIMIT = 0.8
ALWAYS_PASS_RATE = 0.95


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _checks(run, details_path):
    """Return list of (name, score 0..1, weight) for a run; [] if not available."""
    tr = run.get("test_results")
    tests = tr.get("tests") if isinstance(tr, dict) else None
    out = []
    for t in tests or []:
        try:
            out.append((str(t["name"]), float(t.get("score") or 0.0), float(t.get("weight") or 0.0)))
        except (KeyError, TypeError, ValueError):
            pass
    if out:
        return out
    d = _load(details_path)
    if isinstance(d, dict):
        for cat in d.values():
            if not isinstance(cat, dict):
                continue
            for c in cat.get("criteria") or []:
                try:
                    out.append((str(c["name"]), float(c.get("value") or 0.0), float(c.get("weight") or 0.0)))
                except (KeyError, TypeError, ValueError):
                    pass
    return out


def solver_runs(task_dir):
    rdir = os.path.join(task_dir, "runs")
    runs = []
    if not os.path.isdir(rdir):
        return runs
    for fn in sorted(os.listdir(rdir)):
        if not fn.endswith(".json") or fn.endswith(".reward-details.json"):
            continue
        j = _load(os.path.join(rdir, fn))
        if not isinstance(j, dict) or j.get("_kind") != "solver":
            continue
        if j.get("status") not in ("PASSED", "FAILED"):
            continue
        r = j.get("aggregate_reward")
        if not isinstance(r, (int, float)) or isinstance(r, bool):
            continue
        details = os.path.join(rdir, fn[:-5] + ".reward-details.json")
        runs.append({"model": str(j.get("_model") or ""), "reward": float(r),
                     "checks": _checks(j, details)})
    return runs


def headroom_warning(task_dir):
    """Stored-task layout (<task_dir>/runs/*.json)."""
    return headroom_from_runs(solver_runs(task_dir), os.path.basename(os.path.normpath(task_dir)))


def headroom_from_runs(runs, task=""):
    """runs: list of dicts {model, reward, checks=[(name, score, weight)]}, solver runs only.
    Layout-free core, so a tool with another run layout can build the list itself."""
    n = len(runs)
    models = sorted({r["model"] for r in runs})
    res = {"task": task, "runs": n, "models": len(models),
           "mean": None, "spread": None, "top_check_share": None, "always_pass_weight_share": None,
           "warning": False, "reason": "", "line": ""}
    if n:
        res["mean"] = sum(r["reward"] for r in runs) / n
    by_model = {}
    for r in runs:
        by_model.setdefault(r["model"], []).append(r["reward"])
    spreads = [max(v) - min(v) for v in by_model.values() if len(v) >= 2]
    if spreads:
        res["spread"] = sum(spreads) / len(spreads)  # mean max-min over models with 2+ runs

    # per-check: failing weight and pass rate, over runs that have check data
    fail_w, passed, seen, weight = {}, {}, {}, {}
    for r in runs:
        for name, score, w in r["checks"]:
            fail_w[name] = fail_w.get(name, 0.0) + w * max(0.0, 1.0 - score)
            seen[name] = seen.get(name, 0) + 1
            passed[name] = passed.get(name, 0) + (1 if score >= 0.999 else 0)
            weight[name] = max(weight.get(name, 0.0), w)
    total_fail = sum(fail_w.values())
    if total_fail > 0:
        res["top_check_share"] = max(fail_w.values()) / total_fail
    tw = sum(weight.values())
    if tw > 0:
        easy = sum(weight[k] for k in weight if passed[k] / seen[k] >= ALWAYS_PASS_RATE)
        res["always_pass_weight_share"] = easy / tw

    reasons = []
    if n == 0:
        reasons.append("no usable solver runs")
    else:
        if res["mean"] >= MEAN_LIMIT:
            reasons.append("pooled mean reward is %.2f (0.90 or higher), little room to improve" % res["mean"])
        if n < MIN_RUNS or len(models) < MIN_MODELS:
            reasons.append("only %d run(s) over %d model(s); need at least %d runs over %d models"
                           % (n, len(models), MIN_RUNS, MIN_MODELS))
        if res["top_check_share"] is not None and res["top_check_share"] > TOP_CHECK_LIMIT:
            reasons.append("one check carries %.0f%% of the failing weight (over 80%%)"
                           % (100 * res["top_check_share"]))
    res["warning"] = bool(reasons)
    res["reason"] = "; ".join(reasons)
    res["line"] = ("HEADROOM WARNING: " + res["reason"]) if reasons else "training signal: ok"
    return res


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(d, headroom_warning(d)["line"])
