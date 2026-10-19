"""Read-only Data OS client. The access token is read again from a file (or DATAOS_TOKEN) on every request, so a
fresh token pasted into the file while a download runs is picked up. Nothing here launches, cancels or deletes anything.

Get a token: in the signed-in Data OS tab, DevTools Console: copy(sessionStorage.getItem('data-os.access-token'))
A token lives 15 minutes. When it expires the script waits for a new one (in a terminal) or stops with exit code 3;
every finished download is kept, so running the same command again carries on.
"""

import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.data-os.turing.com"
GAP = 0.45  # seconds between calls; the API rate-limits bursts


class TokenExpired(Exception):
    pass


class Client:
    def __init__(self, token_file):
        self.token_file = token_file
        self.last = 0.0

    def token(self):
        t = os.environ.get("DATAOS_TOKEN", "").strip()
        if not t and os.path.exists(self.token_file):
            with open(self.token_file, encoding="utf-8") as fh:
                t = fh.read().strip()
        return t.replace("Bearer ", "").strip().strip('"')

    def _wait_for_new_token(self, old):
        if not sys.stdin.isatty():
            raise TokenExpired(
                "The Data OS token expired. Paste a fresh one into %s and run the same command again; "
                "finished downloads are kept." % self.token_file
            )
        print("\nThe Data OS token expired (they last 15 minutes).")
        print(
            "Copy a new one (README step 3) and save it in %s, then press Enter."
            % self.token_file
        )
        input()
        os.environ.pop("DATAOS_TOKEN", None)
        if self.token() == old:
            print("The token file did not change; trying once more anyway.")

    def get(self, path, retries=6):
        url = path if path.startswith("http") else API + path
        for i in range(retries):
            t = self.token()
            if not t:
                self._wait_for_new_token("")
                continue
            w = GAP - (time.time() - self.last)
            if w > 0:
                time.sleep(w)
            self.last = time.time()
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": "Bearer " + t,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as x:
                    raw = x.read()
                    if x.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    self._wait_for_new_token(t)
                    continue
                if e.code in (429, 502, 503, 504):
                    time.sleep(4 * (i + 1))
                    continue
                if e.code == 404:
                    return None
                raise RuntimeError(
                    "GET %s -> HTTP %d %s"
                    % (path, e.code, e.read(200).decode("utf-8", "replace"))
                )
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(4 * (i + 1))
        raise RuntimeError("GET %s kept failing (rate limit or network)" % path)

    # --- the four calls the report needs -------------------------------------------------------------------
    def run(self, run_id):
        return self.get("/api/evaluations/runs/%d/" % run_id)

    def grader(self, run_id):
        return self.get(
            "/api/evaluations/runs/%d/output-file/?path=verifier/test-stdout.txt"
            % run_id
        )

    def evaluations(self, task_id):
        """All evaluations of one task, every model, every page."""
        out, path = [], "/api/evaluations/?task=%d&page_size=100" % task_id
        while path:
            d = self.get(path)
            if not d:
                break
            out += d.get("results", []) if isinstance(d, dict) else d
            path = d.get("next") if isinstance(d, dict) else None
        return out

    def models(self):
        d = self.get("/api/llm-engine/models/?page_size=200")
        return d.get("results", d) if isinstance(d, dict) else d
