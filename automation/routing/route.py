#!/usr/bin/env python3
"""Owner routing for QC findings, shared by step 1 (task_read.py) and step 3 (manager_read.py).

Every finding says who fixes it, at the moment the finding is written:

  FIX        our QC team or the author fixes it (verifier, schema, packaging, timeouts, formula faults,
             a check that lets an empty or wrong answer earn credit). The fix must not make the task easier.
  EXPERT     a domain expert decides (wrong or unsupported golden answer, missing or wrong source data,
             domain judgment, an unclear prompt, a convention an expert would know even if the prompt does not say it).
  KEEP_HARD  the only change on offer would make the task easier (relax a tolerance, drop or merge a criterion,
             add a hint, accept more answers). Do not make it. The finding stays on the list so nobody does.

Integration point: the "What to change" text that step 1 (RULE_TEXT, FIX_BY_TEST) and step 3 (the manager prompt)
hand to authors. Before this module those texts said "remove the check" and "loosen or delete the criterion".

Standard library only.
"""

import re

ROUTES = ("FIX", "EXPERT", "KEEP_HARD")

# Step 1 rule ids (automation/task-read/prompts/v2_reader.md) and verified-finding tests (a to d).
# Value: (default route, who/why in plain words)
STEP1_RULE_ROUTE = {
    "A1": (
        "EXPERT",
        "Wrong or contradicted answer key: a domain expert confirms the right value. A transcription slip against a source file may be fixed by QC; never edit the key to match a model's answer.",
    ),
    "A2": (
        "EXPERT",
        "A check asks for something neither the prompt nor the sources ask for: the expert decides whether the requirement belongs in the task. Do not delete the check to make the task easier.",
    ),
    "A3": (
        "FIX",
        "The judge is not given the files or values it needs: QC puts the values in the check text or gives the judge the files.",
    ),
    "A4": ("FIX", "The grading script can crash: QC fixes the script."),
    "A7": (
        "EXPERT",
        "A correct answer written differently fails: the expert confirms which alternatives are valid. Widening what passes without that confirmation makes the task easier.",
    ),
    "B1": (
        "FIX",
        "One check grades many facts: split it, keeping every clause, weight and tolerance.",
    ),
    "B2": (
        "FIX",
        "The same fact is graded twice: note which check owns it; do not drop either without the expert.",
    ),
    "B3": (
        "FIX",
        "Wording a judge could read two ways: QC tightens the wording without changing what is required.",
    ),
}
STEP1_TEST_ROUTE = {
    "a": (
        "EXPERT",
        "A prompt-following answer loses credit: the expert decides whether the check or the prompt is wrong.",
    ),
    "b": (
        "FIX",
        "A wrong or empty answer gains credit: QC tightens the check (this keeps or raises difficulty).",
    ),
    "c": (
        "EXPERT",
        "Two requirements contradict: the expert decides which one is right.",
    ),
    "d": (
        "FIX",
        "The check needs a file or fact the model is not given: QC checks the packaging first; if the fact does not exist anywhere, send it to the expert.",
    ),
}

# Step 3 item types (automation/manager-read/prompts/manager_prompt.md)
STEP3_TYPE_ROUTE = {
    "U": (
        "EXPERT",
        "The criterion demands something the instruction never asks for: the expert decides whether to add it to the instruction.",
    ),
    "A7": (
        "EXPERT",
        "One exact wording where the instruction allows others: the expert confirms which alternatives are valid.",
    ),
    "A1": ("EXPERT", "The golden answer has a factual error: the expert corrects it."),
    "O": (
        "FIX",
        "An empty, missing or wrong answer still passes: QC tightens the criterion.",
    ),
    "C": (
        "EXPERT",
        "Two requirements ask for opposite things: the expert decides which is right.",
    ),
    "D": (
        "FIX",
        "The criterion needs a fact or file the model was never given: QC checks the packaging; if the data is truly absent, send it to the expert.",
    ),
    "R": (
        "FIX",
        "A review major the reader confirmed: the reader should have set a route; QC reads the item and re-routes it.",
    ),
}

# Wording that eases a task. A suggested change that matches is flagged so it is not applied by default.
_EASING = re.compile(
    r"\b(loosen|relax|remove the (check|criterion|test)|delete the (check|criterion|test)|drop (the|a) (check|criterion|clause|test)|"
    r"merge (the )?(checks|criteria)|widen|accept the equivalent|accept more|add a hint|give the (answer|hint)|lower the (weight|tolerance|threshold)|"
    r"increase the tolerance|raise the tolerance)\b",
    re.I,
)


def easing_risk(text):
    """True when a proposed change reads like it makes the task easier. A clause that forbids the change
    ("Do not delete the check ...") is a warning, not a suggestion, so it is removed before the search."""
    kept = re.sub(r"[^.;:]*\b(?:do not|don't|never|must not)\b[^.;:]*[.;:]?", " ", text or "", flags=re.I)
    return bool(_EASING.search(kept))


def default_route(kind, key):
    """kind is 'step1_rule', 'step1_test' or 'step3_type'; returns (route, why). Unknown ids go to FIX with a note."""
    table = {
        "step1_rule": STEP1_RULE_ROUTE,
        "step1_test": STEP1_TEST_ROUTE,
        "step3_type": STEP3_TYPE_ROUTE,
    }[kind]
    k = str(key or "").strip()
    k = k.upper() if kind != "step1_test" else k.lower()
    if k in table:
        return table[k]
    return (
        "FIX",
        "Not in the routing table: a person reads the item and re-routes it.",
    )


def normalize_item(item, kind, key):
    """Make sure an item carries route, route_why, difficulty_effect and easing_risk. Keeps a valid route the reader set itself."""
    item = dict(item)
    route = str(item.get("route", "")).strip().upper().replace(" ", "_")
    why = str(item.get("route_why", "")).strip()
    if route not in ROUTES:
        route, default_why = default_route(kind, key)
        why = why or default_why
    change = str(item.get("fix") or item.get("what_to_change") or "")
    risk = easing_risk(change)
    effect = str(item.get("difficulty_effect", "")).strip().lower()
    if effect not in ("none", "easier", "harder"):
        effect = "easier" if risk else "none"
    # A change that would make the task easier never stays on the FIX list: it goes to the expert or is kept hard.
    if route == "FIX" and (risk or effect == "easier"):
        route = "KEEP_HARD"
        why = (
            (why + " " if why else "")
            + "The suggested change would make the task easier, so it is not applied by default."
        )
    item.update(
        {
            "route": route,
            "route_why": why,
            "difficulty_effect": effect,
            "easing_risk": risk,
        }
    )
    return item


def group_by_route(items):
    out = {r: [] for r in ROUTES}
    for it in items:
        out.setdefault(it.get("route", "FIX"), []).append(it)
    return out


HEADINGS = {
    "FIX": "Our QC team fixes these (the fix must not make the task easier)",
    "EXPERT": "Send these to the domain expert (do not fix them yourself)",
    "KEEP_HARD": "Keep hard: do not change these (the only fix on offer would make the task easier)",
}


def summary_line(items):
    g = group_by_route(items)
    return "Who acts: %d for our QC team, %d for the domain expert, %d keep hard." % (
        len(g["FIX"]),
        len(g["EXPERT"]),
        len(g["KEEP_HARD"]),
    )
