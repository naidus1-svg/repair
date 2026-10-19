"""Publish a built site to GitHub Pages through the GitHub API (no local clone). Optional.

    python publish_pages.py --subject Grok --owner YOUR-ORG-OR-USER --repo grok-companybench --dry-run
    python publish_pages.py --subject Grok --owner YOUR-ORG-OR-USER --repo grok-companybench

Needs the gh CLI, signed in with a token that can create repositories. Creates a public repo on the first run and turns on
Pages; afterwards it updates only the files whose content changed. A published page is public, so run leakscan.py first
and get the owner's go-ahead before the real run. --dry-run lists what would be uploaded and changes nothing.
"""

import argparse
import base64
import glob
import hashlib
import json
import os
import subprocess
import sys

from cbr.common import OUT


def gh(*args, data=None):
    p = subprocess.run(
        ["gh", "api", *args] + (["--input", "-"] if data is not None else []),
        input=json.dumps(data) if data is not None else None,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout, p.stderr


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--subject", required=True)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument(
        "--description", default="CompanyBench results, failure modes and traces"
    )
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    src = os.path.join(OUT, a.subject, "site")
    files = sorted(
        p for p in glob.glob(src + "/**/*", recursive=True) if os.path.isfile(p)
    ) + [os.path.join(src, ".nojekyll")]
    files = list(dict.fromkeys(files))
    if a.dry_run:
        print(
            "would publish %d files from %s to %s/%s"
            % (len(files), src, a.owner, a.repo)
        )
        return
    rc, out, _ = gh("repos/%s/%s" % (a.owner, a.repo))
    if rc != 0:
        r = subprocess.run(
            [
                "gh",
                "repo",
                "create",
                "%s/%s" % (a.owner, a.repo),
                "--public",
                "--description",
                a.description,
            ],
            capture_output=True,
            text=True,
        )
        print("create", r.returncode, r.stdout.strip(), r.stderr.strip()[:200])
        if r.returncode != 0:
            sys.exit(1)
    changed = 0
    for p in files:
        rel = os.path.relpath(p, src).replace(os.sep, "/")
        b = open(p, "rb").read()
        sha_local = hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()
        rc, out, _ = gh("repos/%s/%s/contents/%s" % (a.owner, a.repo, rel))
        remote = json.loads(out).get("sha") if rc == 0 else None
        if remote == sha_local:
            continue
        body = {"message": "Update " + rel, "content": base64.b64encode(b).decode()}
        if remote:
            body["sha"] = remote
        rc, out, err = gh(
            "-X", "PUT", "repos/%s/%s/contents/%s" % (a.owner, a.repo, rel), data=body
        )
        changed += 1
        if rc != 0:
            print("FAIL", rel, err[:200])
    print("files", len(files), "changed", changed)
    rc, out, err = gh("repos/%s/%s/pages" % (a.owner, a.repo))
    if rc != 0:
        rc, out, err = gh(
            "-X",
            "POST",
            "repos/%s/%s/pages" % (a.owner, a.repo),
            data={"source": {"branch": "main", "path": "/"}},
        )
        print("pages enable", rc, err[:200])
    rc, out, err = gh("repos/%s/%s/pages" % (a.owner, a.repo))
    print("pages", json.loads(out).get("html_url") if rc == 0 else err[:200])


if __name__ == "__main__":
    main()
