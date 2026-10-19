# CompanyBench report builder

Turns one model's CompanyBench runs in Data OS into the report Khiem sent Google for Gemini 4 Argon: a website (80 minute view, 5 hour view, side by side, failure modes, trace player, matrix with a prompt dropdown), a single-file copy of it, and a Word Doc. It compares the new model with the four saved baseline models (Gemini 4 Argon, Claude Fable 5.1, GPT 6.1 Sol, GPT 6 Astra), and with every model you add later.

Everything runs on your own computer from this folder. You need Python 3.10 or newer, the repo, a signed-in Data OS tab, and nothing else: no server, no shared machine, no other repo.

Do the run first: `../README.md` (steps 1 to 10) runs the model in Data OS and gives you two CSV files. This README starts from those two files.

## Commands at a glance

Replace `Grok`, `"Grok 4.7"` and `65` with the model you ran (Inkling is `Inkling`, `"Inkling"`, `74`). Run everything from this folder (`companybench-model-eval/report`).

```bash
pip install -r requirements.txt
python add_model.py --key Grok --label "Grok 4.7" --id 65
python fetch.py --key Grok --main ../companybench_model65_main.csv --long ../companybench_model65_long.csv
python analyze.py --key Grok
python build_site.py --subject Grok
python build_doc.py --subject Grok
python leakscan.py out/Grok --deny work/denylist.txt --allow-url https://where-you-will-serve-the-site/
```

Results land in `out/Grok/`: `site/` (the website), `report.html` (the same thing as one file), `Grok-companybench-report.docx` and `.md` (the Doc), two chart PNGs. Details of each step follow.

## Step 1. Install

```bash
pip install -r requirements.txt
```

Only `build_doc.py` needs the two packages (python-docx, matplotlib). Every other script uses the Python standard library.

## Step 2. Register the model

```bash
python add_model.py --key Grok --label "Grok 4.7" --id 65
```

`--key` is a short name (letters and digits) used in run keys such as `T07-grok-2` and in file names. It adds the model to `data/models.json` with the next colour in the palette. Commit that file with the results.

## Step 3. Get a token

The fetch reads Data OS the same way the website does, read only, so it needs your access token.

1. Open https://data-os.turing.com and sign in.
2. DevTools (F12), Console, run `copy(sessionStorage.getItem('data-os.access-token'))`. If Chrome blocks pasting into the console, type `allow pasting` first.
3. Paste the result into a new file `work/token.txt` (create the `work` folder; it is gitignored). Do not paste the token anywhere else and do not commit it.

A token lives 15 minutes. If it expires during the fetch, the script pauses and asks for a new one (paste it into the same file and press Enter), or, when run without a terminal, stops with exit code 3. Nothing is lost: run the same command again and it skips everything already downloaded.

## Step 4. Fetch the runs

```bash
python fetch.py --key Grok --main ../companybench_model65_main.csv --long ../companybench_model65_long.csv
```

`--main` and `--long` are the two files the runner wrote (`CB.exportCsv(65, 'main')` and `CB.exportCsv(65, 'long')`); they hold the run ids. Leave `--long` out when no run timed out. The script saves, under `work/Grok/`:

* `selection.json`: which runs count (the first 3 per task), which timed-out run each 5 hour rerun replaces, and which timed-out runs have no scored rerun yet (their tasks are dropped from the same-task 5 hour view for every model);
* `raw/runs/<run id>.json`: the run record with every step of the trajectory;
* `raw/graders/<run id>.json`: the grader output of each run;
* `attempts.csv`: the evaluation lists of the 40 tasks and their 5 hour copies, which give the provider-stall counts.

It stops with exit code 2 if a task has fewer than 3 counted runs: finish the 80 minute part first (`CB.status`). About 160 runs take 10 to 20 minutes. `--skip-attempts` skips the stall counts; `--selection-only` writes `selection.json` and downloads nothing.

## Step 5. Analyse

```bash
python analyze.py --key Grok
```

Writes `work/models/Grok/`:

| File | What it holds |
|---|---|
| `runs.json` | one row per counted run and per 5 hour rerun: score, minutes, tokens, cost, turns, largest turn, checks passed |
| `traces.json.gz` | the step timeline of every run: class of command, systems touched, minute, output tokens, seconds, masked command |
| `full/<T>.json.gz` | masked step detail (reasoning, command, output) per task, for the trace player |
| `why.json` | steps, errors, retries, polls, repeats, re-checks, unreadable replies, time in turns of 8,000+ tokens, for all runs, runs that timed out and runs that finished |
| `longturns.json`, `longturn_runs.json` | long turns (8,000+ output tokens), re-check cycles, steps from the first data query to the first deliverable |
| `modes.json` | a rule-based failure mode for every run below full marks |
| `meta.json` | reruns scored and pending, provider stalls, turn-size counts |

Every measure is a word pattern or arithmetic on the recorded trajectory; no model reads anything. The definitions are at the top of `cbr/runmetrics.py`. `--full misses` limits the masked step detail to runs below full marks and reruns (smaller site); `--strict` masks every number of 3 or more digits and every decimal in step detail.

Step detail is masked per task with the values the grader holds for that task (all numbers and strings under the `expected`, `reference`, `golden`, `definition`, `details`, `rubric` fields of every grader output fetched for the task), plus emails, URLs and capitalised first-and-last name pairs.

To keep a finished model for the next report, copy `work/models/Grok/` to `data/models/Grok/` and commit it. `data/models/<key>/` is the saved copy the builders use when no fresh analysis exists in `work/models/<key>/`. The four baseline models are saved there already.

## Step 6. Build the site

```bash
python build_site.py --subject Grok
```

Builds the report for Grok against every model in `data/models.json` (use `--models Argon,Fable,Grok` to choose). The model named by `--subject` is the one the text is about; the others are its comparison. Output: `out/Grok/site/index.html` plus `data/traces/` and `data/full/` (ready for GitHub Pages), and `out/Grok/report.html`, one file with the timelines inside. For the single file to show full step detail, build with `--live-url https://where-you-will-serve-the-site/`; without it the single file shows the masked commands only.

To look at it locally: `python -m http.server 8000 --directory out/Grok/site`, then open http://localhost:8000.

The views: 80 minute limit, with 5 hour reruns (the toggle at the top), results bars and table, where the time goes, side by side, failure modes, a matrix of every task and run with the full prompt under each task name, a trace player (every step of any run), every miss with its card, method and denominators. The 5 hour view reruns only the models that had timeouts, and drops a task for every model when any rerun on it has not finished; a sensitivity line keeps all 40 tasks and scores unfinished reruns as 0.

What is written by measures and what needs a reader: the numbers, charts, tables, failure-mode labels (rule-based, from run measures), long-turn examples and the side-by-side table of the ten widest task gaps are all generated. The written read of each run pair, the mode explanations and the step-by-step notes in the trace player come from a reader pass (Step 9) and appear only when one exists for the subject model. For the Argon report that pass is saved in `data/reader/Argon/`.

## Step 7. Build the Doc

```bash
python build_doc.py --subject Grok --site-url https://where-you-will-serve-the-site/
```

Writes the Word file and a Markdown copy to `out/Grok/`: talking points, the checks that rule out the harness, the why section, dataset and harness description, both result views with charts and tables, how the model runs out of time, side by side, failure modes, tasks the other models solve and this one does not, and what the report does not establish. The text states measures and ranks; it makes no claim a reader would have to judge.

## Step 8. Leak scan

```bash
python leakscan.py out/Grok --deny work/denylist.txt --allow-url https://where-you-will-serve-the-site/
```

Must print `HITS: 0` before anything is shared. `--allow-url` names the address you passed to `build_doc.py --site-url` (the scan flags every other URL). It checks every output file against the grader values of each task (looked for only in text that belongs to that task), the task, run and evaluation ids, URLs, emails, dashes, the word "simulated", and every line of the deny file. Create `work/denylist.txt` yourself with the names that must never appear (the company and its counterparties, one per line); it stays in `work/`, which is gitignored. Never put those names in a file that gets committed.

Fix a hit at its source (re-run `analyze.py --strict` for step-detail hits, edit the reader text for hits in reader text), rebuild, and scan again.

## Step 9. Optional: a reader pass

A person or an agent reads the traces and writes the judgement layer. Put the files in `data/reader/Grok/` (same shapes as `data/reader/Argon/`; `data/reader/SCHEMA.md` lists them): `cards.json` (one entry per run below full marks: mode, what the grader said, what happened, notes by step), `mx.json` (one explanation per mode, with example runs), `sbs.json` (side-by-side pairs), `walk.json`, `notes.json`, `stories.json`. Rules for the reader: write plain sentences; name the step; never copy a number or phrase the grader holds as expected. Run `python validate_reader.py --subject Grok` and then Step 8 again. Rebuild the site and Doc; they pick the files up.

## Step 10. Optional: publish

```bash
python publish_pages.py --subject Grok --owner YOUR-ORG-OR-USER --repo grok-companybench --dry-run
```

Publishes `out/Grok/site/` to GitHub Pages through the `gh` CLI. A page is public: run the leak scan, get the go-ahead from Khiem, then run it without `--dry-run`.

## Check the pipeline against the Gemini report

Run Argon through the same commands as if it were the new model and compare with what was published (55 of 120 full marks at 80 minutes; 73 of 117 with 5 hour reruns on the 39 tasks whose reruns finished):

```bash
python fetch.py --key Argon --main repro/argon_main.csv --long repro/argon_long.csv
python analyze.py --key Argon
python check_repro.py
```

It prints `REPRODUCES THE PUBLISHED NUMBERS` when the fresh analysis matches the published figures and every counted run matches the saved copy in `data/models/Argon/`. `python -m unittest discover -s tests` runs the unit tests (counting rule, masking, classifier).

## Files

| Path | Purpose |
|---|---|
| `fetch.py`, `analyze.py`, `build_site.py`, `build_doc.py`, `leakscan.py` | the five steps |
| `add_model.py`, `check_repro.py`, `publish_pages.py`, `validate_reader.py` | register a model, check against the published report, publish, check reader files |
| `cbr/` | the code behind them: Data OS client, step classifier, per-run measures, masking, counting rule, failure modes, views |
| `site/` | the page: `style.css`, `body.html`, `app.js` |
| `data/models.json` | the model registry (label, colour, Data OS id) |
| `data/models/<key>/` | saved results of a finished model |
| `data/reader/<key>/` | saved reader pass for a subject model |
| `data/tasks.json`, `data/prompts.json` | the 40 tasks by alias (T01 to T40), generic titles, and the masked prompts |
| `repro/` | the two CSVs that reproduce the Argon numbers |
| `work/`, `out/` | downloads, fresh analysis, built pages (gitignored) |

## Rules

* Tasks appear only by alias and a generic title. No task ids, expected values or names from task data go into a page.
* The data is real operational data of a fintech and personal finance company, redacted and consented. Describe it that way, do not call it simulated, and do not name the company or its counterparties.
* A run counts when it finishes with a score or times out; the first 3 per task are the task's runs. Provider stalls ("sent nothing for 1800s") are replaced and not counted.
* Do not commit `work/`, `out/` or a token.
