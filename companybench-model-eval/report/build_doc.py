"""Step 4: build the Doc (Word file, Markdown copy and two charts) for one subject model against the others.

    python build_doc.py --subject Grok --site-url https://example.github.io/grok-companybench/

Needs python-docx and matplotlib (pip install -r requirements.txt). Every number comes from the same data as the site.
Writes out/<subject>/<subject>-companybench-report.docx, .md, chart-80min.png and chart-5hour.png.
The text states measures and ranks only. Anything that needs a reader's judgement (why a figure was wrong, which
behaviours are better or worse) appears only when a reader pass exists for the subject (README step 9).
"""

import argparse
import datetime
import os
import re
import statistics as st

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt

from cbr import views
from cbr.common import FULL, OUT


def ordn(n):
    return (
        [
            "",
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
        ][n]
        if n <= 10
        else "%dth" % n
    )


def rank(D, V, m, f, hi=True):
    return 1 + sum(
        1 for x in D["models"] if (f(V[x]) > f(V[m]) if hi else f(V[x]) < f(V[m]))
    )


def chart(D, V, n, title, path):
    M, L = D["models"], D["label"]
    fig, ax = plt.subplots(1, 2, figsize=(9, 0.9 + 0.5 * len(M)), dpi=150)
    names = [L[m] for m in M][::-1]
    cols = [D["color"][m] for m in M][::-1]
    for a, vals, lab, top, f in (
        (
            ax[0],
            [100.0 * V[m]["full"] / n for m in M][::-1],
            "Full marks, %% of %d runs" % n,
            100,
            lambda v: "%.0f%%" % v,
        ),
        (
            ax[1],
            [V[m]["mean"] for m in M][::-1],
            "Mean score, 0 to 1",
            1,
            lambda v: "%.2f" % v,
        ),
    ):
        b = a.barh(names, vals, color=cols)
        a.set_xlim(0, top)
        a.set_title(lab, fontsize=9)
        for rect, v in zip(b, vals):
            a.text(
                rect.get_width() + top * 0.01,
                rect.get_y() + rect.get_height() / 2,
                f(v),
                va="center",
                fontsize=8,
            )
        a.spines[["top", "right"]].set_visible(False)
        a.tick_params(labelsize=8)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--subject", required=True)
    ap.add_argument("--models")
    ap.add_argument("--site-url", default="")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--out")
    a = ap.parse_args()
    D = views.load(a.subject, a.models.split(",") if a.models else None)
    S, M, L = D["subject"], D["models"], D["label"]
    OT = [m for m in M if m != S]
    out = a.out or os.path.join(OUT, S)
    os.makedirs(out, exist_ok=True)
    V8, VS, S0 = D["V"]["80"], D["V"]["same"], D["V"]["sens0"]
    NT, NK = len(D["tasks"]), len(D["keep"])
    n80 = V8[S]["n"]
    RER, SUBRER = D["rerun_models"], S in D["rerun_models"]
    WY, LT, RD = D["why"], D["lt"], D["reader"] or {}
    runs = D["runs"]
    sub80 = [r for r in runs if r["model"] == S and r["view"] == "80"]
    miss = [r for r in sub80 if r["reward"] < FULL]
    to80 = [r for r in sub80 if r["timeout"]]

    def rng(f, d=0, scale=1.0):
        v = [f(m) * scale for m in OT if f(m) is not None]
        if not v:
            return "n/a"
        lo, hi = min(v), max(v)
        fm = "%%.%df" % d
        return fm % lo if fm % lo == fm % hi else (fm % lo) + " to " + (fm % hi)

    oto, on = sum(V8[m]["timeouts"] for m in OT), sum(V8[m]["n"] for m in OT)
    w, l = WY.get(S, {}), LT.get(S, {})
    wt = WY.get(S + "_timeout")

    img80 = os.path.join(out, "chart-80min.png")
    chart(D, V8, n80, "Same 80 minute limit, %d tasks" % NT, img80)
    img5 = None
    if RER:
        img5 = os.path.join(out, "chart-5hour.png")
        chart(
            D,
            VS,
            VS[S]["n"],
            "Up to 5 hours for timed-out runs, %d of %d tasks (favours the rerun models)"
            % (NK, NT),
            img5,
        )

    B = []
    H1 = lambda t: B.append(("h1", t))
    H2 = lambda t: B.append(("h2", t))
    P = lambda t: B.append(("p", t))
    UL = lambda xs: B.append(("ul", xs))
    TB = lambda h, r: B.append(("table", h, r))
    IMG = lambda p, c: B.append(("img", p, c))

    H1("%s on realistic company tasks" % L[S])
    P("Turing CompanyBench, %s. Preliminary." % a.date)
    H2("Talking points: 5 minutes")
    tp = [
        "We ran %s on %d realistic company jobs built from real operational data of a fintech and personal finance company (redacted and consented): the agent has to find evidence across a database, wiki, chat, tickets and email with tools, then deliver figures. It is a tool-use test, not a knowledge quiz."
        % (", ".join(L[m] for m in M), NT),
        "At the same 80 minute limit %s reaches full marks in %d of %d runs (%s), with a mean score of %.2f, %s of %d. %d of its %d runs ran out of time; across the other models %d of %d did."
        % (
            L[S],
            V8[S]["full"],
            n80,
            ", ".join("%d for %s" % (V8[m]["full"], L[m]) for m in OT),
            V8[S]["mean"],
            ordn(rank(D, V8, S, lambda v: v["mean"])),
            len(M),
            len(to80),
            n80,
            oto,
            on,
        ),
    ]
    if SUBRER and VS[S]["n"]:
        tp.append(
            "Given up to 5 hours for the runs that timed out, on the %d of %d tasks where every rerun finished, %s reaches full marks in %d of %d runs (%s). Counting all %d tasks with unfinished reruns as zero it is %d of %d."
            % (
                NK,
                NT,
                L[S],
                VS[S]["full"],
                VS[S]["n"],
                ", ".join("%d for %s" % (VS[m]["full"], L[m]) for m in OT),
                NT,
                S0[S]["full"],
                S0[S]["n"],
            )
        )
    tp.append(
        "Effort per run: %.0f steps (%.0f tool calls) against %s steps (%s tool calls) for the others; %.0fk output tokens against %sk; %.0f minutes against %s."
        % (
            V8[S]["turns"],
            V8[S]["tool_calls"],
            rng(lambda m: V8[m]["turns"]),
            rng(lambda m: V8[m]["tool_calls"]),
            V8[S]["out_tok"] / 1000.0,
            rng(lambda m: V8[m]["out_tok"], scale=0.001),
            V8[S]["minutes"],
            rng(lambda m: V8[m]["minutes"]),
        )
    )
    if w and l:
        tp.append(
            "Where the steps go: about %.0f steps of reading and querying before the first deliverable (others %s), %.2f re-check cycles per run (others %s), and %.0f%% of the clock in turns of 8,000 or more output tokens (others %s%%)."
            % (
                w["explore_before_delivery_per_run"],
                rng(lambda m: WY[m]["explore_before_delivery_per_run"]),
                l["cycles_per_run"],
                rng(lambda m: LT[m]["cycles_per_run"], 2),
                100 * w["time_share_in_8k_turns"],
                rng(lambda m: WY[m]["time_share_in_8k_turns"], 0, 100),
            )
        )
    UL(tp)
    H2("Talking points: 10 minutes (add these)")
    UL(
        [
            "The checks we ran so this is the model and not our setup (section A).",
            "The why, step by step from the traces (section B).",
            "Where the model loses points, by failure mode (section 6).",
        ]
    )
    H2("A. Is it the model, or our harness, prompt or setup?")
    tps = lambda m: st.median(
        [
            r["out_tok"] / (r["agent_min"] * 60)
            for r in runs
            if r["model"] == m
            and r["view"] == "80"
            and r.get("agent_min")
            and r.get("out_tok")
        ]
        or [0]
    )
    waitsh = (
        100.0
        * sum(r.get("wait_s", 0) for r in (to80 or sub80))
        / max(1.0, sum(r["agent_min"] * 60 for r in (to80 or sub80)))
    )
    A = [
        "Same harness, prompt, tools, sandbox and limits for all %d models (Terminus 2, described below). %s: %d of %d runs hit the limit; the others: %d of %d."
        % (len(M), L[S], len(to80), n80, oto, on),
        "Tool time: the model asked the terminal to wait for about %.0f%% of the agent time%s; the rest is the model generating."
        % (waitsh, " in the runs that hit the limit" if to80 else ""),
        "Speed: %.1f output tokens per second of agent time (median run) against %s for the others; %.0fk output tokens per run against %sk."
        % (
            tps(S),
            rng(tps, 1),
            V8[S]["out_tok"] / 1000.0,
            rng(lambda m: V8[m]["out_tok"], scale=0.001),
        ),
    ]
    cap = D["meta"][S].get("caps")
    if cap and cap.get("turns"):
        A.append(
            "Output cap: %d of %s turns reached 60,000 output tokens; %d of those returned no text and no command."
            % (cap.get("t60k", 0), format(cap["turns"], ","), cap.get("t60k_empty", 0))
        )
    if w:
        A.append(
            "Reply format: %.1f replies per run could not be read by the harness (others %s). Each costs a turn."
            % (w["parse_warn_per_run"], rng(lambda m: WY[m]["parse_warn_per_run"], 1))
        )
    st_ = D["meta"][S].get("attempts")
    A.append(
        "Provider stalls (the API sending nothing for 30 minutes) were retried and are not counted as failures"
        + (
            ": %d at 80 minutes%s."
            % (st_["stall80"], ", %d in the reruns" % st_["stall_long"] if RER else "")
            if st_
            else "."
        )
    )
    A.append("All models ran at high reasoning effort.")
    note = D["meta"][S].get("setup_note")
    if note:
        A.append(note)
    UL(A)
    H2("B. Why: steps, loops and long runs")
    if w and l:
        wo = [WY[m] for m in OT if m in WY]
        UL(
            [
                "Steps: %.0f steps per run against %s. Before its first deliverable the model takes about %.0f steps of reading and querying (others %s)."
                % (
                    w["steps_per_run"],
                    rng(lambda m: WY[m]["steps_per_run"]),
                    w["explore_before_delivery_per_run"],
                    rng(lambda m: WY[m]["explore_before_delivery_per_run"]),
                ),
                "Errors: %.0f%% of commands return an error (others %s%%); %.0f steps per run come right after an error (others %s). About %.0f steps per run are polls for output (others %s)."
                % (
                    100 * w["error_share"],
                    rng(lambda m: WY[m]["error_share"], 0, 100),
                    w["retries_per_run"],
                    rng(lambda m: WY[m]["retries_per_run"]),
                    w["polls_per_run"],
                    rng(lambda m: WY[m]["polls_per_run"], 1),
                ),
                'Re-checks: %.1f%% of turns open with a re-check phrase such as "wait" or "hold on" (a word-pattern count; others %s%%). %.2f re-check cycles per run (others %s)%s.'
                % (
                    100 * w["recheck_share"],
                    rng(lambda m: WY[m]["recheck_share"], 1, 100),
                    l["cycles_per_run"],
                    rng(lambda m: LT[m]["cycles_per_run"], 2),
                    (
                        "; median %d turns and %.0f minutes each, longest %d turns over %.0f minutes"
                        % (
                            l["cycle_turns_median"],
                            l["cycle_minutes_median"],
                            l["cycle_turns_max"],
                            l["cycle_minutes_max"],
                        )
                        if l["cycles"]
                        else ""
                    ),
                ),
                "Long turns: %d turns of 8,000 or more output tokens in %d runs (%.2f per run; others %s). They take %.0f%% of the clock%s."
                % (
                    l["long_turns"],
                    n80,
                    l["long_turns_per_run"],
                    rng(lambda m: LT[m]["long_turns_per_run"], 2),
                    100 * w["time_share_in_8k_turns"],
                    (
                        " (%.0f%% in runs that hit the limit)"
                        % (100 * wt["time_share_in_8k_turns"])
                        if wt
                        else ""
                    ),
                ),
                "Steps from the first data query to the first deliverable (median): %s against %s."
                % (
                    l["steps_query_to_delivery_median"],
                    rng(lambda m: LT[m]["steps_query_to_delivery_median"]),
                ),
            ]
        )
    else:
        P(
            "The step analysis (why.json, longturns.json) is not available for this model."
        )
    H2("1. The dataset")
    P(
        "%d long-horizon tasks, each a job an operations, risk or support analyst does inside the data of a consumer fintech company: audit a fee, reconcile transfers, trace a failed payment, check a fraud report against tickets. The agent works in a terminal and has to find evidence across the company's database, wiki, team chat, issue tracker, email and support desk, then post or write a result with specific figures. The prompt does not say where the answer is. Checks compare each result to figures an expert computed, some judged against a written rubric. All %d models ran three times per task in the same agent harness, Terminus 2 (version 2.0.0), each in its own sandbox container, at high reasoning effort, internet on and web search off."
        % (NT, len(M))
    )
    H2("The harness")
    UL(
        [
            "An agent loop, not a single API call. The model gets the task prompt and a live Linux terminal. Each turn it replies in a fixed JSON format (analysis, plan, keystrokes); the harness types them, waits the time the model asked for, and returns the screen output.",
            "Two tools only: type keystrokes and wait, and mark the task complete. The company systems are tool servers the model reaches by writing and running scripts in that terminal.",
            "What in the harness could affect results: the fixed JSON reply format, screen text as the only observation, and model response time counting against the 80 minute clock.",
        ]
    )
    P("Grading runs after the agent stops and does not count against the clock.")
    H2("2. Results at the same 80 minute limit")
    IMG(img80, "%d runs per model." % n80)
    TB(
        [
            "Model",
            "Full marks",
            "Mean score",
            "Runs scoring zero",
            "Minutes per run",
            "Turns per run",
            "Runs that hit the limit",
            "Cost per run",
            "Cost per full-marks run",
        ],
        [
            [
                L[m],
                "%d of %d" % (V8[m]["full"], n80),
                "%.2f" % V8[m]["mean"],
                "%d" % V8[m]["zero"],
                "%.1f" % V8[m]["minutes"],
                "%.0f" % V8[m]["turns"],
                "%d" % V8[m]["timeouts"],
                "$%.2f" % V8[m]["cost"],
                ("$%.2f" % V8[m]["cost_per_full"]) if V8[m]["cost_per_full"] else "n/a",
            ]
            for m in M
        ],
    )
    P(
        "Cost is the model usage cost the evaluation platform records per run; sandbox cost is excluded."
    )
    if RER:
        H2("3. Results with up to 5 hours")
        ls = D["lsum"]
        P(
            "Runs that hit the 80 minute limit were rerun with a 5 hour limit (%s). %s; tasks with a rerun still going are left out for every model, leaving %d of %d tasks. Models that were not rerun keep their 80 minute runs."
            % (
                ", ".join(L[m] for m in RER),
                "; ".join(
                    "%s: %d of %d reruns had finished by the cutoff"
                    % (L[m], ls[m]["n"], ls[m]["slots"])
                    for m in RER
                ),
                NK,
                NT,
            )
        )
        IMG(
            img5,
            "%d runs per model. The left-out tasks are the slowest reruns, so this view favours the rerun models. Counting all %d tasks with the unfinished reruns as zero, %s has %d of %d full marks."
            % (VS[S]["n"], NT, L[S], S0[S]["full"], S0[S]["n"]),
        )
        TB(
            ["Model", "Full marks", "Mean score", "Minutes per run", "Turns per run"],
            [
                [
                    L[m],
                    "%d of %d" % (VS[m]["full"], VS[m]["n"]),
                    "%.2f" % VS[m]["mean"],
                    "%.1f" % VS[m]["minutes"],
                    "%.0f" % VS[m]["turns"],
                ]
                for m in M
            ],
        )
    H2("4. How the model runs out of time")
    if to80:
        UL(
            [
                "%d of %d runs hit the 80 minute limit, on %d tasks; they average %.2f. The other %d runs average %.2f."
                % (
                    len(to80),
                    n80,
                    len({r["alias"] for r in to80}),
                    st.mean(r["reward"] for r in to80),
                    n80 - len(to80),
                    st.mean([r["reward"] for r in sub80 if not r["timeout"]] or [0]),
                ),
                "Tool waits are about %.0f%% of those runs; per output second the model is at %.1f tokens against %s for the others. Provider speed cannot be separated from model behaviour."
                % (waitsh, tps(S), rng(tps, 1)),
            ]
        )
    else:
        P("No run hit the 80 minute limit.")
    H2("5. Side by side")
    sb = RD.get("sbs") if RD else None
    if sb and sb.get("summary"):
        P(
            "Each row comes from reading a run of %s against a run of another model on the same task, at the step where they part ways. One reader's judgement per pair; every pair and both traces are on the site."
            % L[S]
        )
        rows = []
        for b in sb["summary"]:
            tl = b.get("tasks") or []
            rows.append(
                [
                    "Better" if b["argon"] == "better" else "Worse",
                    b["behaviour"],
                    "%d (%s)"
                    % (
                        len(tl),
                        D["tasks"].get(tl[0], {}).get("title", "") if tl else "",
                    ),
                ]
            )
        TB([L[S], "Behaviour", "Tasks seen (example)"], rows)
    else:
        P(
            "For each task, %s is set against the other model with the highest mean score on that task. The ten tasks with the widest gap in either direction:"
            % L[S]
        )
        tm = lambda row, m: sum(c[1] for c in row["cells"][m]) / max(
            1, len(row["cells"][m])
        )
        gaps = []
        for row in D["matrix"]:
            bm = max(OT, key=lambda m: tm(row, m))
            gaps.append((abs(tm(row, S) - tm(row, bm)), row, bm))
        gaps.sort(key=lambda x: -x[0])
        TB(
            ["Task", "%s mean" % S, "Best other", "Its mean"],
            [
                [g[1]["title"], "%.2f" % tm(g[1], S), L[g[2]], "%.2f" % tm(g[1], g[2])]
                for g in gaps[:10]
            ],
        )
    H2("6. Failure modes")
    P(
        "%d of %s's %d runs at 80 minutes scored below full marks. Each has one primary mode:"
        % (len(miss), L[S], n80)
    )
    cards = (RD.get("cards") or {}) if RD else {}
    modes = {}
    for r in miss:
        m = (cards.get(r["key"]) or {}).get("mode") or D["modes"].get(
            r["key"], "not labelled"
        )
        modes[m] = modes.get(m, 0) + 1
    X = {m["mode"]: m for m in ((RD.get("mx") or {}).get("modes", []) if RD else [])}
    from cbr.modes import DEFS

    def first(k, n=220):
        e = (X.get(k) or {}).get("explain") or DEFS.get(k, "")
        out = ""
        for s in re.split(r"(?<=[.])\s+", e):
            if out and len(out) + len(s) > n:
                break
            out = (out + " " + s).strip()
        return out

    TB(
        ["Mode", "Runs", "What happens"],
        [[k, str(v), first(k)] for k, v in sorted(modes.items(), key=lambda x: -x[1])],
    )
    if not X:
        P("These modes come from run measures; no reader has labelled the runs yet.")
    H2("7. Tasks the other models solve that %s does not at 80 minutes" % S)
    sol = []
    fc = lambda row, m: sum(1 for x in row["cells"][m] if x[1] >= FULL)
    for row in D["matrix"]:
        if fc(row, S) < 2 and all(fc(row, m) >= 2 for m in OT):
            sol.append(
                "%s: full marks in %d of 3 runs for %s, %s."
                % (
                    row["title"],
                    fc(row, S),
                    L[S],
                    ", ".join("%d for %s" % (fc(row, m), L[m]) for m in OT),
                )
            )
    UL(
        sol
        or [
            "None: on every task at least one other model also fails to reach full marks in 2 of 3 runs."
        ]
    )
    H2("What this does not establish")
    UL(
        [
            "Three runs per task is not a stable rate for one task.",
            "Only high reasoning effort was run; provider speed cannot be separated from model behaviour.",
            "Failure modes "
            + (
                "and side-by-side rows are one reader's judgement per run."
                if RD
                else "here are rule-based labels from run measures, not a reader's judgement."
            ),
        ]
    )
    if a.site_url:
        P("Every run, trace and failure, step by step: " + a.site_url)

    md = []
    for b in B:
        k = b[0]
        if k in ("h1", "h2"):
            md.append(("# " if k == "h1" else "## ") + b[1])
        elif k == "p":
            md.append(b[1])
        elif k == "ul":
            md.append("\n".join("- " + x for x in b[1]))
        elif k == "img":
            md.append("![%s](%s)" % (b[2], os.path.basename(b[1])))
        elif k == "table":
            md.append(
                "| "
                + " | ".join(b[1])
                + " |\n|"
                + "---|" * len(b[1])
                + "\n"
                + "\n".join("| " + " | ".join(r) + " |" for r in b[2])
            )
    text = "\n\n".join(md) + "\n"
    base = os.path.join(out, "%s-companybench-report" % S)
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(text)
    doc = Document()
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(10.5)
    for b in B:
        k = b[0]
        if k == "h1":
            doc.add_heading(b[1], 0)
        elif k == "h2":
            doc.add_heading(b[1], 1)
        elif k == "p":
            doc.add_paragraph(b[1])
        elif k == "ul":
            for x in b[1]:
                doc.add_paragraph(x, style="List Bullet")
        elif k == "img":
            doc.add_picture(b[1], width=Inches(6.5))
            doc.add_paragraph(b[2]).runs[0].italic = True
        elif k == "table":
            t = doc.add_table(rows=1, cols=len(b[1]))
            t.style = "Light Grid Accent 1"
            for i, h in enumerate(b[1]):
                t.rows[0].cells[i].text = h
            for r in b[2]:
                cs = t.add_row().cells
                for i, v in enumerate(r):
                    cs[i].text = v
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    doc.save(base + ".docx")
    print("doc", len(text.split()), "words ->", base + ".docx")


if __name__ == "__main__":
    main()
