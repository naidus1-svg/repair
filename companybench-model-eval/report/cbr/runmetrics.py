"""Per-run measures from one run record (the JSON of /api/evaluations/runs/<id>/), and their roll-ups per model.

Everything is a word-pattern or arithmetic measure; no model reads a trace. Definitions:
  error_out    the command's output contains an error (Traceback, Error:, exception, command not found, No such file ...)
  retry        the step comes right after an error step
  repeat       exact same command text as an earlier step in the run
  poll         empty command (waiting for output)
  recheck      the model's message opens with a re-check phrase (wait, hold on, actually, let me double-check ...)
  parse_warn   the harness reports it could not parse the model's reply (format problem)
  explore      reads, lists and queries before the first deliverable write or send
  long turn    8,000 or more output tokens in one turn
  cycle        a stretch of consecutive turns that opens with a re-check phrase and keeps re-examining (another re-check,
               or a query or read) without writing the deliverable
"""

import collections
import json
import re
import statistics as st

from .classify import PRI, classify, mask
from .common import ts

ERR = re.compile(
    r"Traceback|\bError\b|error:|Exception|command not found|No such file|SyntaxError|NameError|KeyError|TypeError|ValueError|ModuleNotFoundError|syntax error",
    re.I,
)
RECHECK_W = re.compile(
    r"^(analysis:\s*)?(wait|hold on|hmm|actually|let me (double|re)-?check|let me verify|re-?check|double-?check|one more check|let me make sure|but wait)",
    re.I,
)
RECHECK_L = re.compile(
    r"^(analysis:\s*)?(wait|hold on|hmm|actually|let me (double|re)-?check|let me verify|re-?check|double-?check|one more check|let me make sure|but wait|look at)",
    re.I,
)
PARSE = re.compile(
    r"(could not|failed to|unable to) parse|invalid json|parsing error|WARNINGS?:.*(json|format)|Previous response had (parsing )?(errors|warnings)",
    re.I,
)
WRITE_W = re.compile(
    r"chat_post_message|send_message|create_issue|conversations_create|pins_add|add_comment|create_comment|update_issue|files_upload|reply_to|create_draft|create_reply_to_ticket|create_note_to_ticket|> */?workspace/.*\.(md|xlsx|csv|json)|to_excel|\.save\("
)
EXPLORE = re.compile(
    r"\b(ls|cat|head|tail|grep|find|sed -n|wc)\b|SELECT|select |get_pages|search|list_|get_|conversations_history|enhanced_search",
    re.I,
)
WRITE_L = re.compile(
    r"chat_post_message|send_message|create_issue|conversations_create|pins_add|add_comment|create_comment|update_issue|files_upload|create_draft|create_reply_to_ticket|create_note_to_ticket|to_excel|\.save\(|> */?workspace/[\w./-]+\.(md|xlsx|csv)"
)
TOPIC = [
    (
        "schema or table layout",
        r"column|schema|table|field|rows|join|foreign key|primary key",
    ),
    (
        "documentation or policy",
        r"wiki|confluence|page|policy|procedure|spec|documentation|definition|rule",
    ),
    ("messages and tickets", r"slack|message|thread|ticket|jira|email|comment"),
    (
        "re-checking a result",
        r"wait|hold on|actually|double-check|re-check|verify|mismatch|discrepan|again|instead|but ",
    ),
    (
        "writing code or a script",
        r"script|python|function|code|import|def |bug|error|traceback|fix",
    ),
    ("planning the deliverable", r"report|memo|deliverable|post|write|summary|final"),
]
CYC_CONT = ("query data", "read company system", "run script", "read file", "wait")
LONG = 8000


def agent_steps(run):
    return [
        s
        for s in ((run.get("trajectory") or {}).get("steps") or [])
        if s.get("source") == "agent"
    ]


def keystrokes(step):
    return " ".join(
        ((tc.get("arguments") or {}).get("keystrokes") or "")
        for tc in step.get("tool_calls") or []
    ).strip()


def obs_text(step):
    return "".join(
        (
            x.get("content")
            if isinstance(x.get("content"), str)
            else json.dumps(x.get("content"))
        )
        or ""
        for x in ((step.get("observation") or {}).get("results") or [])
    )


def _mins(a, b):
    try:
        return round((ts(b) - ts(a)) / 60, 1)
    except Exception:
        return None


def meta(run):
    """Headline numbers of one run, from the platform's own fields."""
    ep = run.get("execution_profile") or {}
    ae = ep.get("agent_execution") or {}
    mu = run.get("model_token_usage") or {}
    return dict(
        reward=float(run.get("aggregate_reward") or 0.0),
        status=run.get("status"),
        minutes=_mins(ep.get("started_at"), ep.get("finished_at")),
        agent_min=_mins(ae.get("started_at"), ae.get("finished_at")),
        tool_calls=run.get("total_tool_calls"),
        in_tok=mu.get("input_tokens"),
        out_tok=mu.get("output_tokens"),
        cache_tok=mu.get("cache_tokens"),
        cost=round(mu.get("cost_usd") or 0, 3),
        env_cost=round(run.get("environment_cost_usd") or 0, 3),
    )


def trace(run):
    """Step timeline: [turn, minute, class, systems, output tokens, seconds since previous step, calls, wait s, masked command]."""
    steps = agent_steps(run)
    allsteps = (run.get("trajectory") or {}).get("steps") or []
    ae = (run.get("execution_profile") or {}).get("agent_execution") or {}
    t0 = ts(ae["started_at"]) if ae.get("started_at") else ts(allsteps[0]["timestamp"])
    scripts = {}
    seq = []
    prev = t0
    nturn = 0
    for s in steps:
        nturn += 1
        mt = s.get("metrics") or {}
        t = ts(s["timestamp"]) if s.get("timestamp") else prev
        cl, tg, wait = [], [], 0.0
        cmds = [
            mask((tc.get("arguments") or {}).get("keystrokes") or "")
            for tc in s.get("tool_calls") or []
            if tc["function_name"] != "mark_task_complete"
        ]
        cmd = " | ".join(x for x in cmds if x)[:260]
        for tc in s.get("tool_calls") or []:
            if tc["function_name"] == "mark_task_complete":
                c, g = "final answer", []
            else:
                a = tc.get("arguments") or {}
                c, g = classify(a.get("keystrokes") or "", scripts)
                try:
                    wait += float(a.get("duration") or 0)
                except Exception:
                    pass
            cl.append(c)
            tg += g
        if not cl:
            cl = ["wait"]
        c = sorted(cl, key=PRI.index)[0]
        seq.append(
            [
                nturn,
                round((t - t0) / 60, 1),
                c,
                sorted(set(tg)),
                mt.get("completion_tokens") or 0,
                round(t - prev),
                len(cl),
                round(wait),
                cmd,
            ]
        )
        prev = t
    return seq


def why_counters(run):
    """Counters for the 'why more steps' measures of one run."""
    steps = agent_steps(run)
    ep = (run.get("execution_profile") or {}).get("agent_execution") or {}
    try:
        t0 = ts(ep["started_at"])
    except Exception:
        t0 = ts(steps[0]["timestamp"]) if steps else 0
    seen, prev_err, delivered, prev_t = set(), False, False, t0
    c = collections.Counter()
    tok8_time = tot_time = 0.0
    toks = []
    for s in steps:
        msg = (s.get("message") or "").strip()
        calls = s.get("tool_calls") or []
        ks = keystrokes(s)
        obs = obs_text(s)
        t = ts(s["timestamp"]) if s.get("timestamp") else prev_t
        dt = max(0.0, t - prev_t)
        prev_t = t
        tot_time += dt
        ct = (s.get("metrics") or {}).get("completion_tokens") or 0
        toks.append(ct)
        if ct >= LONG:
            tok8_time += dt
        c["steps"] += 1
        c["calls"] += max(1, len(calls))
        if (
            not ks
            and calls
            and all(tc.get("function_name") != "mark_task_complete" for tc in calls)
        ):
            c["poll"] += 1
        if prev_err:
            c["retry"] += 1
        if ks and ks in seen:
            c["repeat"] += 1
        if ks:
            seen.add(ks)
        if RECHECK_W.search(msg[:160]):
            c["recheck"] += 1
        if PARSE.search(obs[:600]) or PARSE.search(msg[:200]):
            c["parse_warn"] += 1
        e = bool(ERR.search(obs[-1500:]))
        c["error_out"] += int(e)
        prev_err = e
        if WRITE_W.search(ks):
            delivered = True
        if delivered:
            c["after_first_delivery"] += 1
        elif EXPLORE.search(ks):
            c["explore_before_delivery"] += 1
    c["tok8_share_time_x1000"] = int(1000 * tok8_time / tot_time) if tot_time else 0
    c["median_tokens_x1"] = int(st.median(toks)) if toks else 0
    c["wait_requested_s"] = 0  # filled by the caller from the trace
    return c


def roll_why(counters):
    """Per-run counters of one set of runs to the published 'why' row."""
    cs = counters
    n = len(cs)
    S = lambda k: sum(c[k] for c in cs)
    steps = S("steps") or 1
    return dict(
        runs=n,
        steps_per_run=round(steps / n, 1),
        error_outputs_per_run=round(S("error_out") / n, 1),
        error_share=round(S("error_out") / steps, 3),
        retries_per_run=round(S("retry") / n, 1),
        repeats_per_run=round(S("repeat") / n, 1),
        repeat_share=round(S("repeat") / steps, 3),
        polls_per_run=round(S("poll") / n, 1),
        poll_share=round(S("poll") / steps, 3),
        recheck_per_run=round(S("recheck") / n, 1),
        recheck_share=round(S("recheck") / steps, 3),
        parse_warn_per_run=round(S("parse_warn") / n, 2),
        explore_before_delivery_per_run=round(S("explore_before_delivery") / n, 1),
        after_first_delivery_per_run=round(S("after_first_delivery") / n, 1),
        time_share_in_8k_turns=round(
            sum(c["tok8_share_time_x1000"] for c in cs) / n / 1000, 3
        ),
        median_tokens_per_turn=round(st.median(c["median_tokens_x1"] for c in cs)),
    )


def _lt_class(ks):
    if not ks.strip():
        return "wait"
    if WRITE_L.search(ks):
        return "deliver"
    if re.search(r"SELECT|select |execute_sql|query", ks):
        return "query data"
    if re.search(
        r"mcp_client|call_tool|get_pages|search|conversations_|enhanced_search", ks
    ):
        return "read company system"
    if re.search(r"cat <<|> \S+\.py|tee ", ks):
        return "write script"
    if re.search(r"python3? ", ks):
        return "run script"
    return "read file"


def longturn_run(run):
    """Long turns, re-check cycles and steps from first data query to first deliverable, for one run."""
    steps = agent_steps(run)
    longs, cyc, cyc_min = [], [], []
    prev_t = None
    cur, cur_t0, first_q, first_d = 0, None, None, None
    for i, s in enumerate(steps, 1):
        msg = (s.get("message") or "").strip()
        ks = keystrokes(s)
        t = ts(s["timestamp"]) if s.get("timestamp") else prev_t
        dt = (t - prev_t) if (t and prev_t) else 0
        prev_t = t
        ct = (s.get("metrics") or {}).get("completion_tokens") or 0
        c = _lt_class(ks)
        if first_q is None and c in ("query data", "read company system"):
            first_q = i
        if first_d is None and c == "deliver":
            first_d = i
        rc = bool(RECHECK_L.search(msg[:160]))
        if ct >= LONG:
            low = msg.lower()[:600]
            topics = [name for name, pat in TOPIC if re.search(pat, low)]
            longs.append(
                dict(
                    tokens=ct,
                    secs=dt,
                    next=c,
                    topic=topics[0] if topics else "other",
                    recheck=rc,
                    turn=i,
                )
            )
        if rc or (cur and c in CYC_CONT):
            if cur == 0 and rc:
                cur_t0 = t - dt if t else None
                cur = 1
            elif cur:
                cur += 1
        if cur and (c == "deliver" or (not rc and c not in CYC_CONT)):
            if cur >= 2:
                cyc.append(cur)
                cyc_min.append(((t or 0) - (cur_t0 or 0)) / 60 if cur_t0 else 0)
            cur = 0
    if cur >= 2:
        cyc.append(cur)
        cyc_min.append(((prev_t or 0) - (cur_t0 or 0)) / 60 if cur_t0 else 0)
    if first_q and first_d:
        lead = first_d - first_q
    elif first_q:
        lead = len(steps) - first_q
    else:
        lead = None
    return dict(longs=longs, cycles=cyc, cycle_min=cyc_min, lead=lead)


def roll_longturns(per_run):
    """Roll-up of longturn_run() results for one model's 80 minute runs."""
    lt = [x for r in per_run for x in r["longs"]]
    cyc = [x for r in per_run for x in r["cycles"]]
    cmin = [x for r in per_run for x in r["cycle_min"]]
    lead = [r["lead"] for r in per_run if r["lead"] is not None]
    n = len(per_run)
    return dict(
        long_turns=len(lt),
        long_turns_per_run=round(len(lt) / n, 2),
        long_turn_minutes_total=round(sum(x["secs"] for x in lt) / 60, 1),
        long_turn_topic=dict(collections.Counter(x["topic"] for x in lt).most_common()),
        long_turn_next_action=dict(
            collections.Counter(x["next"] for x in lt).most_common()
        ),
        long_turn_recheck_share=(
            round(sum(x["recheck"] for x in lt) / len(lt), 3) if lt else 0
        ),
        cycles=len(cyc),
        cycles_per_run=round(len(cyc) / n, 2),
        cycle_turns_median=st.median(cyc) if cyc else 0,
        cycle_turns_p90=sorted(cyc)[max(0, int(0.9 * len(cyc)) - 1)] if cyc else 0,
        cycle_turns_max=max(cyc) if cyc else 0,
        cycle_minutes_median=round(st.median(cmin), 1) if cmin else 0,
        cycle_minutes_max=round(max(cmin), 1) if cmin else 0,
        steps_query_to_delivery_median=st.median(lead) if lead else None,
    )


def cap_counts(run):
    """Turn-size counts: all turns, 8k+, 60k+, 65k+, and 60k+ turns that were empty (no text, no call)."""
    c = collections.Counter()
    for s in agent_steps(run):
        ct = (s.get("metrics") or {}).get("completion_tokens") or 0
        c["turns"] += 1
        c["t8k"] += ct >= LONG
        c["t60k"] += ct >= 60000
        c["t65k"] += ct >= 65000
        if ct >= 60000:
            calls = s.get("tool_calls") or []
            c["t60k_empty"] += int(
                len((s.get("message") or "").strip()) < 20 and not calls
            )
    return c


def checks(grader_json):
    """(passed, failed_or_errored, total) from the verifier's own summary lines. Check names are never kept."""
    try:
        txt = (
            grader_json["content"]
            if isinstance(grader_json, dict)
            else str(grader_json)
        )
    except Exception:
        return None
    seen = {}
    for m in re.finditer(
        r"verifier\s+(\d+)/(\d+)\s+\S+\s+\[[^\]]*\]\s+(PASS|FAIL|ERROR)", txt
    ):
        seen[int(m.group(1))] = (m.group(3), int(m.group(2)))
    if not seen:
        return None
    total = max(v[1] for v in seen.values())
    passed = sum(1 for v in seen.values() if v[0] == "PASS")
    return [passed, total]
