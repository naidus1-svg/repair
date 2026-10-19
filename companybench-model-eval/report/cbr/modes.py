"""Rule-based failure mode for a run that scored below full marks. Used when no reader pass has labelled the run.

The label comes from measures, not from reading the trace, and it says so on the site. A reader pass (README step 9)
replaces these labels with sentences that name the actual mistake.
"""

M_LONG = "Ran out of the 80 minute limit in a few very long turns"
M_RECHECK = "Ran out of the 80 minute limit re-checking results it already had"
M_ORDINARY = "Ran out of the 80 minute limit at an ordinary pace"
M_NODELIVER = "Finished without sending or writing a result"
M_REPEAT = "Re-ran its delivery step, so a result was sent or written twice"
M_WRONG = "Delivered a result that the grader scored below full marks"
CLOCK = (M_LONG, M_RECHECK, M_ORDINARY)
DEFS = {
    M_LONG: "The run hit the 80 minute limit and at least a quarter of its clock went to turns of 8,000 or more output tokens. Only a few turns fit, so the deliverable was not written or sent.",
    M_RECHECK: "The run hit the 80 minute limit and either 1 turn in 10 opened with a re-check phrase (such as wait or hold on) or a quarter of its turns sat inside re-check cycles.",
    M_ORDINARY: "The run hit the 80 minute limit without a long-turn or re-check pattern: the turns were ordinary in size and there were too many to fit.",
    M_NODELIVER: "The run stopped before a first deliverable write or send was detected in its commands.",
    M_REPEAT: "The run issued the same delivery command more than once, so a message or file was sent or written twice.",
    M_WRONG: "The run delivered a result and the grader scored it below full marks. The measures cannot tell which figure was wrong; a reader pass (README step 9) names it.",
}
ORDER = (M_LONG, M_RECHECK, M_ORDINARY, M_NODELIVER, M_REPEAT, M_WRONG)


def mode_of(run, why, lt, steps):
    """run: the run's meta dict; why: why_counters; lt: longturn_run; steps: the run's trace."""
    n = max(1, why["steps"])
    if run["timeout"]:
        if why["tok8_share_time_x1000"] >= 250:
            return M_LONG
        cyc_turns = sum(lt["cycles"])
        if why["recheck"] / n >= 0.10 or cyc_turns / n >= 0.25:
            return M_RECHECK
        return M_ORDINARY
    if why["after_first_delivery"] == 0:
        return M_NODELIVER
    sends = [s[8] for s in steps if s[2] == "send message" and s[8]]
    if len(sends) != len(set(sends)):
        return M_REPEAT
    return M_WRONG
