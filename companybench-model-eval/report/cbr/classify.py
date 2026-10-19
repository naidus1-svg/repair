"""Rule-based step classifier and command masker. No model reads anything: every label comes from the command text.

classify(keystrokes, scripts) labels one tool call. `scripts` is a dict the caller keeps per run, so a script the
model wrote in one turn is recognised when it runs in a later turn.
mask(keystrokes) returns the command with every literal removed (quoted strings, numbers of 3+ digits, emails, URLs,
heredoc bodies), keeping the tool names and the first SQL statement shape.
"""

import re

WRITE_NAMES = (
    r"create_reply_to_ticket|create_note_to_ticket|chat_post_message|send_message|create_issue|"
    r"conversations_create|pins_add|add_issue_comment|add_comment|create_comment|update_issue|"
    r"files_upload|create_draft"
)
MCP = re.compile(r"call_tool|mcp_client|streamablehttp_client|localhost:7000")
SMAP = {
    "zeta3-sql-gym": "SQL tables",
    "zeta3": "SQL tables",
    "sql": "SQL tables",
    "confluence-gym": "wiki",
    "confluence": "wiki",
    "slack": "Slack",
    "jira-gym": "Jira",
    "jira": "Jira",
    "email-gym": "email",
    "email": "email",
    "freshdesk-gym": "support tickets",
    "freshdesk": "support tickets",
    "google-drive-gym": "Drive",
}
WCALL = re.compile(
    r"""(?:call\w*\(\s*(?:["'][\w-]+["']\s*,\s*)?["']|await\s+[\w.]+\(\s*["'][\w-]+["']\s*,\s*["']|"name"\s*:\s*"|\bcall\s+[\w-]+\s+|\bcall\s+)(?:%s)\b"""
    % WRITE_NAMES
)
PRI = [
    "final answer",
    "send message",
    "query data",
    "write file",
    "run script",
    "read file",
    "list directory",
    "wait",
]


def tags(ks):
    """Company systems a command touches (from the tool-server names in the command)."""
    t = set()
    for m in re.findall(r"call_tool\(\s*[\"']([\w-]+)[\"']", ks):
        t.add(SMAP.get(m))
    for m in re.findall(r"mcp_client\.py\s+([\w-]+)", ks):
        t.add(SMAP.get(m))
    for m in re.findall(r"mcp/([\w-]+)", ks):
        t.add(SMAP.get(m))
    t.discard(None)
    return sorted(t)


def iswrite(s):
    return bool(WCALL.search(s))


def classify(ks, scripts):
    s = ks.strip()
    if not s:
        return "wait", []
    m = re.search(r"cat\s*<<\s*'?\"?(\w+)'?\"?\s*>>?\s*([\w./-]+)", s)
    wrote = None
    if m:
        wrote = m.group(2)
        scripts[wrote] = (iswrite(s), bool(MCP.search(s)), tags(s))
    run = re.findall(r"python3?\s+([\w./-]+\.py)", s)
    ran_known = [r for r in run if r in scripts]
    if iswrite(s) and (MCP.search(s) or ran_known) and not (wrote and not run):
        return "send message", tags(s)
    for r in ran_known:
        w, q, tg = scripts[r]
        if w:
            return "send message", tg
    if wrote and not run:
        return "write file", tags(s)
    if wrote and run and not ran_known:
        return "write file", tags(s)
    if MCP.search(s) and iswrite(s):
        return "send message", tags(s)
    for r in ran_known:
        w, q, tg = scripts[r]
        if q:
            return "query data", tg
    if MCP.search(s) and not re.search(r"cat\s*<<", s):
        return "query data", tags(s)
    if re.search(
        r"cat\s*<<|^\s*(tee|sed -i)|>\s*[\w./-]+\.(py|md|json|txt)\s*$", s, re.M
    ) and re.search(r"<<", s):
        return "write file", tags(s)
    if run or re.search(r"python3?\s+-", s):
        return "run script", []
    if re.match(r"\s*(ls|find|tree|pwd|cd)\b", s):
        return "list directory", []
    if (
        re.match(r"\s*(cat|head|tail|sed -n|grep|wc|jq|less|awk|sort|cut)\b", s)
        or "open(" in s
    ):
        return "read file", []
    return "run script", []


def mask(k):
    """Command text with every literal removed. Tool names and the first SQL statement are pulled out first."""
    raw = k
    tools = []
    for a, b in re.findall(
        r"""call_tool\(\s*["']([\w-]+)["']\s*,\s*["']([\w-]+)""", raw
    ) + re.findall(r"""mcp_client\.py\s+([\w-]+)\s+(?:call\s+)?([\w-]+)""", raw):
        t = "%s.%s" % (a.replace("-gym", ""), b)
        if t not in tools:
            tools.append(t)
    sql = re.findall(
        r"(?is)\b((?:select\b[^;\"`]{3,160}?\bfrom\b|update\b[^;\"`]{1,60}?\bset\b|insert\s+into\b|delete\s+from\b)[^;\"`]{0,140})",
        raw,
    )
    pre = ""
    if tools:
        pre += "tools: " + ", ".join(tools[:4]) + " ; "
    if sql:
        s0 = re.sub(r"'(?:[^'\\\n]|\\.)*'", "'...'", sql[0])
        s0 = re.sub(r"\d{3,}", "#", s0)
        pre += "SQL: " + re.sub(r"\s+", " ", s0).strip() + " ; "
    k = re.sub(r"<<\s*'?\"?(\w+)'?\"?.*?\n\1\b", "<<script>>", k, flags=re.S)
    k = re.sub(r"https?://\S+", "[url]", k)
    k = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", k)
    k = re.sub(r"'(?:[^'\\\n]|\\.)*'", "'...'", k)
    k = re.sub(r'"(?:[^"\\\n]|\\.)*"', '"..."', k)
    k = re.sub(r"\d{3,}", "#", k)
    k = re.sub(r"\s+", " ", k).strip()
    return (pre + k)[:300]
