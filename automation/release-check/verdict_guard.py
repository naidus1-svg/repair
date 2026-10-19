"""A verdict can never say pass while a finding is a major or has status rejected."""

PASS_WORDS = {"pass", "passed", "ready", "send"}


def _is_pass(verdict):
    return str(verdict or "").strip().lower() in PASS_WORDS


def guard_verdict(verdict, findings):
    """verdict: str. findings: iterable of dicts with severity (major/minor), status
    (open/rejected/accepted), optional id/title. Returns (verdict, note)."""
    if not _is_pass(verdict):
        return verdict, ""
    blockers = []
    for i, f in enumerate(findings or []):
        sev = str(f.get("severity") or "").strip().lower()
        st = str(f.get("status") or "").strip().lower()
        if sev == "major" or st == "rejected":
            name = f.get("id") or f.get("title") or f.get("name") or "finding %d" % (i + 1)
            blockers.append("%s (severity %s, status %s)" % (name, sev or "unset", st or "unset"))
    if not blockers:
        return verdict, ""
    return "HOLD", "verdict %s changed to HOLD: %s" % (verdict, "; ".join(blockers))
