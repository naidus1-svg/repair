"""Step 3: build the report site for one subject model against the others.

    python build_site.py --subject Grok
    python build_site.py --subject Grok --models Argon,Fable,Sol,Astra,Grok --live-url https://example.github.io/grok-companybench/

Writes out/<subject>/site/ (index.html plus data/traces/<T>.json and data/full/<T>.json, ready for GitHub Pages) and
out/<subject>/report.html (one file: traces inlined; full step detail is read from --live-url when given).
Models are looked up in work/models/<key> first (a fresh analysis), then in data/models/<key> (saved results).
"""

import argparse
import collections
import glob
import json
import os
import re
import shutil

from cbr import modes as MODES
from cbr import scrub as SC
from cbr import views
from cbr.common import DATA, HERE, OUT, WORK, jload, jsave

SITE = os.path.join(HERE, "site")
SKIP_META = ("api", "dataos_id", "source")


def model_css(D):
    light = ";".join("--c%d:%s" % (i, D["color"][m]) for i, m in enumerate(D["models"]))
    dark = ";".join(
        "--c%d:%s" % (i, D["color_dark"][m]) for i, m in enumerate(D["models"])
    )
    return (
        ":root{%s;--accent:var(--c0);--onaccent:#ffffff}\n"
        '@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){%s;--accent:var(--c0);--onaccent:#121719}}\n'
        ':root[data-theme="dark"]{%s;--accent:var(--c0);--onaccent:#121719}\n'
        % (light, dark, dark)
    )


def bundles(D):
    """Per-task bundles of step timelines and masked step detail, from every model's saved files."""
    from cbr.common import model_dir

    tr, fu = collections.defaultdict(dict), collections.defaultdict(dict)
    for m in D["models"]:
        d = model_dir(m)
        for k, v in jload(os.path.join(d, "traces.json.gz"), default={}).items():
            tr[k.split("-")[0]][k] = v
        for f in glob.glob(os.path.join(d, "full", "*.json.gz")):
            al = os.path.basename(f).split(".")[0]
            fu[al].update(jload(f))
    # Step detail of every model, saved ones included, is masked once more with the grader values of every run fetched
    # under work/ (all models, all runs of the task), so the published text agrees with what leakscan.py checks.
    vals = SC.alias_values(WORK)
    if not vals:
        print(
            "WARNING: no grader files under work/. Step detail was not masked again; fetch a model first (README step 3)."
        )
    else:
        n = 0
        for al, b in fu.items():
            if al not in vals:
                continue
            nums, strs = vals[al]
            for k, steps in b.items():
                for s in steps:
                    s[3] = SC.scrub(s[3], nums, strs)
                    s[4] = [[c[0], SC.scrub(c[1], nums, strs)] for c in s[4]]
                    s[5] = SC.scrub(s[5], nums, strs)
                    n += 1
        for al, b in tr.items():
            if al in vals:
                nums, strs = vals[al]
                for steps in b.values():
                    for s in steps:
                        s[8] = SC.scrub(s[8], nums, strs)
        ids = SC.known_ids(WORK)
        if ids:
            idre = re.compile(r"(?<![\d.])(%s)(?!\d)" % "|".join(sorted(ids)))
            for b in fu.values():
                for steps in b.values():
                    for s in steps:
                        s[3] = idre.sub("[id]", s[3])
                        s[4] = [[c[0], idre.sub("[id]", c[1])] for c in s[4]]
                        s[5] = idre.sub("[id]", s[5])
        print(
            "step detail masked again for %d steps with grader values of %d tasks"
            % (n, len(vals))
        )
    return tr, fu


def build(subject, keys, live_url=None, out=None):
    D = views.load(subject, keys)
    D["mode_defs"] = MODES.DEFS
    # full task prompts for the matrix dropdown (bank name, emails and person ids already masked)
    D["prompts"] = jload(os.path.join(DATA, "prompts.json"), default={})
    D["meta"] = {
        m: {k: v for k, v in mm.items() if k not in SKIP_META}
        for m, mm in D["meta"].items()
    }
    out = out or os.path.join(OUT, subject)
    shutil.rmtree(out, ignore_errors=True)
    site = os.path.join(out, "site")
    tr, fu = bundles(D)
    for al, b in tr.items():
        jsave(os.path.join(site, "data", "traces", al + ".json"), b)
    for al, b in fu.items():
        jsave(os.path.join(site, "data", "full", al + ".json"), b)
    css = (
        open(os.path.join(SITE, "style.css"), encoding="utf-8").read()
        + "\n"
        + model_css(D)
    )
    body = open(os.path.join(SITE, "body.html"), encoding="utf-8").read()
    js = open(os.path.join(SITE, "app.js"), encoding="utf-8").read()
    blob = json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    js = js.replace("/*__DATA__*/null", blob, 1)
    title = "%s on Turing CompanyBench" % D["label"][subject]
    head = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="robots" content="noindex,nofollow"><title>%s</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,650&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">'
        "<style>%s</style></head><body>" % (title, css)
    )
    html = head + body + "<script>" + js + "</script></body></html>"
    os.makedirs(site, exist_ok=True)
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    open(os.path.join(site, ".nojekyll"), "w").close()
    # single-file copy: traces inlined, full detail read from the live site when a URL is given
    allt = {}
    for al, b in tr.items():
        allt.update(b)
    inl = json.dumps(allt, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    old = "async function getJSON(u){try{const r=await fetch(u);return r.ok?await r.json():null}catch(e){return null}}"
    assert old in js
    new = (
        "async function getJSON(u){const m=u.match(/^data\\/traces\\/(.+)\\.json$/);if(m){const o={};for(const k in window.__TR)if(k.split('-')[0]===m[1])o[k]=window.__TR[k];return o}"
        + (
            "if(u.startsWith('data/'))u='%s'+u;" % live_url
            if live_url
            else "if(u.startsWith('data/'))return null;"
        )
        + "try{const r=await fetch(u);return r.ok?await r.json():null}catch(e){return null}}"
    )
    js1 = js.replace(old, new, 1).replace(
        "if(window.__OPEN_REPORT)setMode('report');", "setMode('report');", 1
    )
    one = (
        head
        + body
        + "<script>window.__TR="
        + inl
        + ";</script><script>"
        + js1
        + "</script></body></html>"
    )
    with open(os.path.join(out, "report.html"), "w", encoding="utf-8") as fh:
        fh.write(one)
    print(
        "site",
        len(html),
        "bytes;",
        "report.html",
        len(one),
        "bytes;",
        "traces for",
        len(tr),
        "tasks;",
        "step detail for",
        sum(len(b) for b in fu.values()),
        "runs",
    )
    v = D["V"]
    for m in D["models"]:
        print(
            "  %-8s 80 min: %d of %d full, mean %.3f | 5 hour (same tasks): %d of %d"
            % (
                m,
                v["80"][m]["full"],
                v["80"][m]["n"],
                v["80"][m]["mean"],
                v["same"][m]["full"],
                v["same"][m]["n"],
            )
        )
    return D, out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--subject", required=True)
    ap.add_argument(
        "--models",
        help="comma list of model keys to include (default: every model in data/models.json plus the subject)",
    )
    ap.add_argument(
        "--live-url",
        help="where the built site will be served; the single-file report reads step detail from here",
    )
    ap.add_argument("--out")
    a = ap.parse_args()
    build(a.subject, a.models.split(",") if a.models else None, a.live_url, a.out)


if __name__ == "__main__":
    main()
