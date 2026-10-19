"""Build one evals.zip per task from GCS, to the delivery format in docs/PACKAGING-SOP.md section 6.

Format, which is Shyam's and taken from the EKW extended samples

  A single `evals/` root, then `<model_slug>/trial_N/job/<timestamp>/<run>/...`. That is the
  GCS tree with `evals/<task>/<revision>/<execution_N>/` stripped off the front. Nothing
  below the execution level changes.

The collisions, which must be told apart

  Dropping the execution segment makes `execution_1/<model>/trial_1` and
  `execution_2/<model>/trial_1` the same archive name. The rule for deciding which trials
  count lives in `packaging/eval_counting.py` and is pinned by `packaging/test_eval_counting.py`,
  because four scripts each carried their own copy and each copy was wrong in a different
  way. Pass `--k` matching the k the run asked for, since k is what separates a duplicate
  re-fire from a top-up.

  Only SCORED trials are archived. A trial that ran and produced no reward would make the
  zip carry more than k trial folders and hand the customer a folder with no verdict in
  it, so it is excluded and named in the notes.

  Dropping the revision segment makes `v2/<model>/trial_1` and `v4/<model>/trial_1` collide
  too, and there the later revision exists to run trials the earlier one never started, so
  BOTH are real and both are kept, with the model's trials renumbered trial_1..trial_N.

  A `<task>.provenance.json` sidecar records which original object became which archive
  entry, so the renumbering is auditable. It stays out of the zip.

Two things are refused rather than shipped

  A trial holding `trial_status/lease.json` with no reward is still running, so the task
  is not built at all. `lease.json` is also excluded from the archive: harbor deletes it
  the instant a trial finishes, so it races the recursive copy and fails checks 1 and 3
  on an otherwise sound zip.

  With `--agent`, an execution whose `config.json` names a different harness is dropped
  whole. The slug `xai__grok-4.6` does not encode the agent, so opencode and grok-build
  are indistinguishable by path and only config.json tells them apart.

Six checks. A zip failing any one is deleted rather than handed to the uploader.

  1. entry count equals the resolved object count
  2. no duplicate entry names
  3. entry names match the resolved set exactly
  4. every entry sits under `evals/`
  5. model folders equal the models actually present in GCS for that task
  6. no `solution` path segment, no `golden_output`, no `answer_key` anywhere

  Check 6 matches `solution` as a path SEGMENT. As a substring it hits
  `Board_Resolutions_2021.pdf` and produced 37 false positives on 2026-08-31.

    python packaging/build_eval_zips.py --tasks ekw0909-task_3,ekw0909-task_53 --k 10
    python packaging/build_eval_zips.py --tasks SVC-PC-1-5-0 --bucket long-horizon-evals-beta \
        --agent grok-build --zip-name eval_grok_4.6_grok_build.zip --k 4
"""

import argparse
import collections
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eval_counting import choose_executions, describe

BUCKET = "long-horizon-evals-qa"
ENV = {
    **os.environ,
    "CLOUDSDK_CORE_DISABLE_PROMPTS": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
}

# evals/<task>/<revision>/<execution_N>/<model_slug>/<trial_N>/<rest...>
OBJ_RE = re.compile(
    r"/evals/(?P<task>[^/]+)/(?P<rev>v\d+)/execution_(?P<ex>\d+)/"
    r"(?P<model>[a-z0-9]+__[^/]+)/trial_(?P<trial>\d+)/(?P<rest>.+)$"
)

BAD_SEGMENTS = {"solution", "golden_outputs", "answer_key"}
BAD_SUBSTRINGS = ("golden_output", "answer_key")

# A runtime lock, not a result. Harbor deletes it the moment a trial finishes, so it
# races the recursive copy: on SVC-PC-1-5-0 it was listed and then gone by download
# time, which failed checks 1 and 3 on an otherwise sound archive.
TRANSIENT = ("trial_status/lease.json",)


def gcloud(args, timeout=3600):
    return subprocess.run(
        ["gcloud.cmd", "storage"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
        timeout=timeout,
    )


def agent_of(paths):
    """Harness name and version out of a job config.json, or (None, None).

    The GCS path `xai__grok-4.6` does NOT encode the agent, so opencode and grok-build
    results are indistinguishable by path. config.json is the only discriminator, and it
    records the harness as `agent: {"name": "grok-build", "kwargs": {"version": "..."}}`.
    Shipping an opencode trial inside a file named eval_grok_4.6_grok_build.zip would
    misattribute the harness to the customer.
    """
    for p in paths:
        r = gcloud(["cat", p], timeout=180)
        if r.returncode != 0:
            continue
        try:
            d = json.loads(r.stdout)
        except Exception:
            continue
        stack = [d]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                a = o.get("agent")
                if isinstance(a, dict) and a.get("name"):
                    return a["name"], (a.get("kwargs") or {}).get("version")
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return None, None


def listing(task):
    r = gcloud(["ls", "-r", "gs://{}/evals/{}/**".format(BUCKET, task)])
    lines = [
        l.strip()
        for l in (r.stdout or "").splitlines()
        if l.strip().startswith("gs://")
    ]
    if r.returncode != 0 and not lines:
        sys.exit("listing failed for %s: %s" % (task, (r.stderr or "")[-300:]))
    return lines


def resolve(task, lines, agent=None, k=10, model=None):
    """Map each kept GCS object to its archive entry name.

    Returns (mapping, models, notes, prov) where mapping is {gcs_path: archive_name}.
    When `agent` is set, a (model, rev, execution) whose config.json names a different
    harness is dropped whole rather than mixed in.
    """
    # index objects by (model, rev, ex, trial)
    groups = collections.defaultdict(list)
    configs = collections.defaultdict(list)
    scored, leased = set(), set()
    for l in lines:
        m = OBJ_RE.search(l)
        if not m or m.group("task") != task:
            continue
        if "/retry_archive/" in l:
            continue
        key = (
            m.group("model"),
            m.group("rev"),
            int(m.group("ex")),
            int(m.group("trial")),
        )
        if model and m.group("model") != model:
            continue
        rest = m.group("rest")
        if l.endswith("/config.json"):
            configs[key[:3]].append(l)
        if rest.endswith("verifier/reward.json"):
            scored.add(key)
        if rest in TRANSIENT:
            leased.add(key)
            continue
        groups[key].append((l, rest))

    notes = []

    live = sorted(leased - scored)

    if agent:
        wrong = {}
        for exkey in sorted({key[:3] for key in groups}):
            name, ver = agent_of(configs.get(exkey, [])[:2])
            if name != agent:
                wrong[exkey] = name or "no config readable"
            else:
                notes.append(
                    "harness confirmed: %s %s execution_%d is %s %s"
                    % (exkey[0], exkey[1], exkey[2], name, ver or "(no version)")
                )
        for exkey, name in wrong.items():
            notes.append(
                "dropped %s %s execution_%d: harness is %s, not %s"
                % (exkey[0], exkey[1], exkey[2], name, agent)
            )
        groups = {key: v for key, v in groups.items() if key[:3] not in wrong}
        if not groups:
            return {}, [], notes, []

    # Executions collide on trial numbers once the execution segment is stripped, and
    # three different things produce that collision. k is what tells them apart, so it
    # is decided per (model, revision) rather than per trial.
    #
    #   DUPLICATE  an execution that scored a full k on its own is a complete
    #              independent set, and a second full-k execution is the wasted
    #              re-fire, not extra evidence. Keep the highest-numbered full set and
    #              drop the rest. Google task_3 is this case: two full k=10 executions
    #              from the 8 accidental re-fires on 2026-09-10.
    #   TOP-UP     no execution reaches k alone, so the later partial exists to add
    #              trials the first never got to. Keep every scored trial across
    #              executions and renumber. SVC-PC-1-5-0 is this case: execution_2 ran
    #              the pilot trial and execution_3 added three more, and taking only
    #              the later one reports the task a trial short of k=4.
    #   RETRY      a single trial number scored in one execution and dead in another.
    #              The scored one wins, which falls out of the two rules above.
    # The rule itself lives in packaging/eval_counting.py with packaging/test_eval_counting.py
    # pinning it, because four scripts each had their own copy and each copy was wrong
    # in a different way. Selection is per (model, revision) and per TRIAL, so a trial
    # that ran and produced no reward is not shipped: it would make the archive carry
    # more than k trial folders and hand the customer a folder with no verdict in it.
    # Revision and execution are ONE dimension, not two. A (revision, execution) pair is
    # a slot, slots are ordered oldest first, and the same rule decides between them: a
    # slot holding a full k is the task's set, otherwise slots combine.
    #
    # Treating revisions separately was the remaining bug. SVC-PC-14-2-0 has 3 scored
    # trials at v6 execution_2 and a complete 4 at v7 execution_1 after the restage.
    # "Both revisions are kept and renumbered" put 7 trial folders in a k=4 archive and
    # blocked the build on a v6 trial that cannot matter. Runbook 14's revision rule was
    # written for a later revision adding trials the earlier never started, which is the
    # combine case here and still behaves the same way.
    slots_of = {}  # model -> {slot index: (rev, ex)}
    trials_by_slot = collections.defaultdict(dict)
    for model in {m for m, _, _, _ in scored}:
        pairs = sorted({(int(r[1:]), e, r) for m, r, e, _ in scored if m == model})
        slots_of[model] = {i: (rev, ex) for i, (_, ex, rev) in enumerate(pairs, 1)}
        for i, (rev, ex) in slots_of[model].items():
            trials_by_slot[model][i] = sorted(
                t for m, r, e, t in scored if m == model and r == rev and e == ex
            )

    kept = {}  # (model, rev, ex, trial) -> objs
    short = set()
    for model, byslot in sorted(trials_by_slot.items()):
        take, mode, dropped = choose_executions(byslot, k)
        where = {i: "%s execution_%d" % slots_of[model][i] for i in slots_of[model]}
        if mode != "single" or len(take) < k:
            notes.append(
                "%s: %s" % (model, describe(mode, take, dropped, k, labels=where))
            )
        if len(take) < k:
            short.add(model)
        for i, trial in take:
            rev, ex = slots_of[model][i]
            key = (model, rev, ex, trial)
            if key in groups:
                kept[key] = groups[key]

    # A trial holding a lease with no reward is still running, and shipping one means an
    # archive that goes stale the moment it lands. Refuse only when that trial could
    # still CHANGE the answer, which means its MODEL has not reached k yet.
    # SVC-PC-14-2-0 is why this is scoped: a v6 trial has held a lease since 01:08Z
    # while v7 holds a complete k=4, so v6 is dropped either way and blocking on it
    # would refuse a task that is finished. A live trial for a model still short of k is
    # a real block, because its reward would land inside the delivered set.
    blocking = [t for t in live if t[0] in short]
    if blocking:
        notes.append(
            "%d trial(s) in flight for a model short of k=%d, refusing to build: %s"
            % (
                len(blocking),
                k,
                ", ".join("%s %s e%d trial_%d" % t for t in blocking[:4]),
            )
        )
        return {}, [], notes, []
    for t in sorted(set(live) - set(blocking)):
        notes.append(
            "ignored a live lease on %s %s execution_%d trial_%d, because that "
            "model already holds k=%d without it" % (t + (k,))
        )

    # Two different reasons a trial is not in the archive, and calling both "no reward"
    # sent a reader looking for a missing verdict that was never missing.
    excluded = set(groups) - set(kept)
    no_reward = sorted(t for t in excluded if t not in scored)
    superseded = sorted(t for t in excluded if t in scored)
    if no_reward:
        notes.append(
            "excluded %d trial(s) that produced no reward: %s"
            % (
                len(no_reward),
                ", ".join("%s %s e%d trial_%d" % t for t in no_reward[:4]),
            )
        )
    if superseded:
        notes.append(
            "excluded %d scored trial(s) in a superseded revision or execution: %s"
            % (
                len(superseded),
                ", ".join("%s %s e%d trial_%d" % t for t in superseded[:4]),
            )
        )

    # revision collision: both kept, renumber per model in (rev, ex, trial) order
    per_model = collections.defaultdict(list)
    for model, rev, ex, trial in kept:
        per_model[model].append((int(rev[1:]), ex, trial, rev))
    mapping, prov = {}, []
    for model, items in per_model.items():
        items.sort()
        for newidx, (revnum, ex, trial, rev) in enumerate(items, start=1):
            for gcs, rest in kept[(model, rev, ex, trial)]:
                entry = "evals/%s/trial_%d/%s" % (model, newidx, rest)
                mapping[gcs] = entry
                prov.append(
                    {
                        "gcs": gcs,
                        "entry": entry,
                        "model": model,
                        "source_revision": rev,
                        "source_execution": ex,
                        "source_trial": trial,
                        "archive_trial": newidx,
                    }
                )
        if len({t for _, _, t, _ in items}) != len(items):
            notes.append(
                "%s: trial numbers repeat across revisions or executions, renumbered to "
                "trial_1..%d" % (model, len(items))
            )
    return mapping, sorted(per_model), notes, prov


def download(task, mapping, root):
    """Bring every kept object down under root, keyed by its archive name.

    Copies only the (revision, execution, model) prefixes the resolver kept, not the whole
    task. An SVC task carries six models' artifacts and the Grok Build zip needs one of
    them, so copying the task prefix is most of the bytes for none of the output.
    """
    dest = os.path.join(root, task)
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)

    prefixes = set()
    for gcs in mapping:
        m = OBJ_RE.search(gcs)
        prefixes.add((m.group("rev"), m.group("ex"), m.group("model")))

    for rev, ex, model in sorted(prefixes):
        # cp -r of <...>/execution_N/<model> into <local>/execution_N/ recreates <model>
        # underneath, so the local tree mirrors GCS and local_for keeps resolving.
        into = os.path.join(dest, task, rev, "execution_" + ex)
        os.makedirs(into, exist_ok=True)
        src = "gs://{}/evals/{}/{}/execution_{}/{}".format(BUCKET, task, rev, ex, model)
        r = gcloud(["cp", "-r", src, into + "/"])
        if r.returncode != 0:
            print("   download warning: %s" % (r.stderr or "")[-200:])
    return dest


def local_for(gcs, dest, task):
    """Where `download` put a given gcs object."""
    tail = gcs.split("/evals/%s/" % task, 1)[1]
    return os.path.join(dest, task, *tail.split("/"))


def build(task, out_dir, work_root, keep, agent=None, zip_name=None, k=10, model=None):
    print("\n=== %s ===" % task, flush=True)
    lines = listing(task)
    mapping, models, notes, prov = resolve(task, lines, agent, k, model)
    for n in notes:
        print("   note: %s" % n)
    if not mapping:
        print("   no objects resolved, nothing to build")
        return None
    print("   objects resolved : %d" % len(mapping))
    print("   models           : %s" % ", ".join(models))

    dest = download(task, mapping, work_root)

    zpath = os.path.join(out_dir, "%s.%s" % (task, zip_name or "evals.zip"))
    missing = []
    rescued = 0
    salvage = os.path.join(work_root, "s")
    os.makedirs(salvage, exist_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for n, (gcs, entry) in enumerate(sorted(mapping.items(), key=lambda kv: kv[1])):
            lp = local_for(gcs, dest, task)
            if not os.path.isfile(lp):
                # The recursive copy skips objects whose mirrored local path breaks
                # Windows: over the 260-char MAX_PATH, or holding a character Windows
                # cannot write. Models name their own deliverables, and task_197 alone
                # produced 22 such files with names like "Confidentiality of Substance
                # Use Disorder (SUD) Patient Records ... 2024 Final Rule (89 FR 12472_
                # RIN 0930-AA32).pdf". gcloud leaves a .gstmp behind and carries on, so
                # the loss is silent and only checks 1 and 3 catch it.
                #
                # Fetch those individually to a SHORT flat name. The zip entry keeps the
                # real long name, because a zip entry is not a filesystem path.
                lp = os.path.join(salvage, "%s_%06d" % (task[-12:], n))
                r = gcloud(["cp", gcs, lp], timeout=600)
                if r.returncode != 0 or not os.path.isfile(lp):
                    missing.append(gcs)
                    continue
                rescued += 1
            z.write(lp, entry)

    if rescued:
        print(
            "   %d object(s) too long or unwriteable for a mirrored path, fetched flat"
            % rescued
        )
    if missing:
        print("   %d object(s) did not download, zip is incomplete" % len(missing))
        for g in missing[:3]:
            print("      %s" % g)

    # ---- the six checks -------------------------------------------------------
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
    want = set(mapping.values())
    fails = []
    if len(names) != len(want):
        fails.append("1: entry count %d != resolved %d" % (len(names), len(want)))
    if len(names) != len(set(names)):
        fails.append("2: duplicate entry names")
    if set(names) != want:
        fails.append("3: entry names do not match the resolved set")
    if not all(n.startswith("evals/") for n in names):
        fails.append("4: some entries are not under evals/")
    zip_models = sorted({n.split("/")[1] for n in names if n.count("/") > 1})
    if zip_models != models:
        fails.append("5: zip models %s != gcs models %s" % (zip_models, models))
    leaks = [
        n
        for n in names
        if any(seg in BAD_SEGMENTS for seg in n.split("/"))
        or any(b in n.lower() for b in BAD_SUBSTRINGS)
    ]
    if leaks:
        fails.append("6: %d answer-key path(s), e.g. %s" % (len(leaks), leaks[:2]))

    size_mb = os.path.getsize(zpath) / 1048576.0
    if fails:
        print("   REJECTED, deleting the zip:")
        for f in fails:
            print("      check %s" % f)
        os.remove(zpath)
        if not keep:
            shutil.rmtree(os.path.join(work_root, task), ignore_errors=True)
        return None

    io.open(
        os.path.join(out_dir, "%s.provenance.json" % task), "w", encoding="utf-8"
    ).write(json.dumps(prov, indent=1))
    print("   OK  %d entries, %.1f MB, all six checks passed" % (len(names), size_mb))
    if not keep:
        shutil.rmtree(os.path.join(work_root, task), ignore_errors=True)
    return zpath


def main():
    global BUCKET
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="comma separated task ids")
    ap.add_argument("--out", default="./eval_zips/out")
    ap.add_argument("--work", default="./eval_zips/work")
    ap.add_argument("--keep-download", action="store_true")
    ap.add_argument(
        "--bucket",
        default=BUCKET,
        help="evals bucket. QA for the Google run, long-horizon-evals-beta for Grok Build",
    )
    ap.add_argument(
        "--agent",
        default="",
        help="keep only executions whose config.json names this harness, e.g. grok-build. "
        "The model slug does not encode the agent, so without this an opencode execution "
        "ships inside a grok-build zip",
    )
    ap.add_argument(
        "--zip-name",
        default="evals.zip",
        help="suffix for the built file, so <task>.<zip-name>",
    )
    ap.add_argument(
        "--model",
        default="",
        help="keep only this model slug, e.g. xai__grok-4.6. Applied BEFORE the --agent "
        "config reads, which is what keeps an SVC task from costing 30 gcloud cats",
    )
    ap.add_argument(
        "--k",
        type=int,
        default=10,
        help="trials per task the run asked for. This decides whether a second "
        "execution is a duplicate full set or a partial top-up, so it must match the "
        "run: 10 for the Google EKW run, 4 for Grok Build on SVC",
    )
    a = ap.parse_args()

    BUCKET = a.bucket

    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)
    tasks = [t.strip() for t in a.tasks.split(",") if t.strip()]
    print("bucket : %s" % BUCKET)
    print("agent  : %s" % (a.agent or "not filtered"))
    print("building %d zip(s) into %s" % (len(tasks), a.out))

    built = []
    for t in tasks:
        p = build(
            t,
            a.out,
            a.work,
            a.keep_download,
            a.agent or None,
            a.zip_name,
            a.k,
            a.model or None,
        )
        if p:
            built.append(p)

    print("\n=== summary ===")
    print("built %d of %d" % (len(built), len(tasks)))
    total = sum(os.path.getsize(p) for p in built) / 1048576.0
    print("total %.1f MB" % total)
    for p in built:
        print("   %8.1f MB  %s" % (os.path.getsize(p) / 1048576.0, p))


if __name__ == "__main__":
    main()
