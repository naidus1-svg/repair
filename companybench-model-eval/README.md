# CompanyBench model run kit (Data OS)

Runs one model on the same 40 CompanyBench tasks, 3 runs each, with the same settings used for Gemini 4 Argon, Claude Fable 5.1, GPT 6.1 Sol and GPT 6 Astra. Then reruns every run that hits the 80 minute limit at 5 hours, exports the results and compares them with those four models.

You do not need Python, a sandbox or an API key for the Data OS part. You need a signed-in Data OS tab and a browser console.

## Which model to run

| Run | Model | Data OS id | Notes |
|---|---|---|---|
| Start here | Grok 4.7 (xAI), the latest Grok in Data OS on 2026-10-17 | 65 | context 500,000; $2 in, $0.50 cached, $6 out per million tokens |
| Next | Inkling (Thinking Machines model), hosted by Together AI, 512K | 73 | litellm backend like the four baseline models; context 524,288; $1.00 in, $0.17 cached, $4.05 out per million tokens |
| Do not use | Inkling (256K), Thinking Machines own backend | 74 | fails at start with Terminus 2 ("Invalid kwargs for agent terminus-2", evaluation 964336). Platform issue, reported |

Check the list again before you start: `await CB.preflight(<id>)` prints the model name, whether it is active and whether it supports the effort setting. If a newer Grok or Thinking Machines model has appeared, ask Khiem before running.

## Settings (do not change any of these)

| Setting | Value | Why |
|---|---|---|
| Agent | Terminus 2 (id 3) | the harness all five models use: the model gets the task plus a live Linux terminal |
| Reasoning effort | high | every model in the comparison ran at high |
| Internet access | on | same for every model |
| Web search | off (Terminus 2 has it always off) | same for every model |
| Runs | 3 per task, 40 tasks = 120 runs | the counted runs |
| Tasks | the 40 tasks in Data OS dataset 5156, "CompanyBench 40 tasks (Gemini comparison)" | exact copies of the originals (instruction, config and tests checked identical) |
| Time limit | 80 minutes per run, set inside each task | nothing to configure |
| 5 hour limit | separate copies of each task in dataset 4900 (40 tasks) | used only for runs that timed out |

Both datasets are shared with the people running this at operator access. If a launch fails with a permission error, ask Khiem to share dataset 5156 and 4900 with you.

## Steps

1. Sign in at https://data-os.turing.com. Keep the tab open.
2. Open DevTools (F12), go to Console. Open `companybench-runner.js` from this folder, copy the whole file, paste it in the Console and press Enter. If Chrome blocks pasting, type `allow pasting` first. You should see `undefined` or nothing; no red error.
3. Check the model: `await CB.preflight(65)`. It must end with `OK: active and supports effort "high".` and `Agent 3: Terminus 2 active=true`. If it says STOP, message Khiem.
4. Dry run: `await CB.launch(65, {dry: true})`. It must end with `DRY RUN: 120 runs would be launched.` and must not create anything.
5. Launch: `await CB.launch(65)`. It prints one line per run and ends with `Done. Launched 120 runs.` It takes about a minute. Data OS queues them and limits how many run at once, so expect several hours.
6. Check progress about every 30 minutes: `await CB.status(65)`. The table shows, per task, runs counted, timed out, in flight, stalled and errored.
7. Replace stalled or errored runs: run `await CB.launch(65)` again. It only tops up what is missing, so running it twice never creates duplicates. A stall is a run that ends with the note "sent nothing for 1800s": the model provider stopped responding. It is retried and not counted. If more than about one run in six stalls, tell Khiem.
8. The 80 minute part is finished when the totals line says `in flight 0` and every task has 3 runs counted or timed out. Then export: `await CB.exportCsv(65, 'main')`. It downloads `companybench_model65_main.csv` with 120 rows.
9. Rerun the timed-out runs at 5 hours. Dry run first: `await CB.launch(65, {dry: true, view: 'long'})`. It prints how many reruns it will launch, one per run that timed out. Then `await CB.launch(65, {view: 'long'})`. A long rerun can take up to 5 hours.
10. Check: `await CB.status(65, 'long')`. Replace stalls the same way as step 7, with `{view: 'long'}`. When nothing is in flight, export: `await CB.exportCsv(65, 'long')`.
11. Compare with the four baseline models. In a terminal, in this folder: `python compare.py --name "Grok 4.7" --main companybench_model65_main.csv --long companybench_model65_long.csv`. It prints three tables: the 80 minute view, the 5 hour view on the same tasks for every model, and the 5 hour view over all 40 tasks with unfinished reruns scored as 0.
12. Send Khiem and Andrew: both CSV files, and the compare output pasted as text.

If you see `No access token`, the sign-in expired: reload the Data OS tab, sign in, paste the runner file again, and carry on. Nothing is lost; every step reads the current state from Data OS.

## Rules that keep the numbers comparable

* A run counts when it finishes with a score, or when it times out. The first 3 counted runs per task, in launch order, are the task's runs. Anything past 3 is ignored.
* Run only on dataset 5156 (and dataset 4900 for the 5 hour reruns). Do not cancel or delete runs.
* You can launch with the runner script (`CB.launch`) or with the Data OS "Evaluate" button on dataset 5156. If you use the button, set exactly: agent Terminus 2, your model, reasoning effort high, internet access on, web search off, number of runs 3. Click it once. The button does not replace stalled runs or top up missing ones, so use `CB.status` to check and `CB.launch` to fill gaps.
* Do not change the effort, agent or task. A different setting makes the model not comparable.
* The 5 hour reruns are only for runs that timed out at 80 minutes. The kit launches exactly one per timed-out run.
* "Full marks" means a reward of 0.9999 or more.

## Expected cost and time

At the 80 minute limit, 120 runs cost, on the platform's own cost field: Gemini 4 Argon about $484, Claude Fable 5.1 about $362, GPT 6.1 Sol about $72, GPT 6 Astra about $442. Argon runs averaged 60 minutes; the others 15 to 22. Plan for $100 to $500 for the 80 minute part of a new model, plus up to 5 hours of wall clock for each rerun. Ask Khiem before launching if the Data OS credit balance is below that.

## How we know this kit counts the way the Gemini report did

The runner and `compare.py` were run against Gemini 4 Argon's real runs (read only, nothing launched). They reproduced the published Argon numbers exactly: 55 of 120 full marks, mean score 0.603, 37 timeouts, and all 40 tasks' three scores identical to the saved baseline. The 5 hour view reproduced 73 of 117 full marks on the 39 tasks whose reruns finished.

## The report (website and Doc)

The failure analysis (steps, errors, long turns, re-check cycles, failure modes) and the website and Doc that Khiem shared with Google are built from the two CSV files plus the run traces. The builder is in `report/`: see `report/README.md` for the exact commands, from the two CSVs to the site, the Doc and the leak scan.

## Files

* `companybench-runner.js`: the console script (preflight, launch, status, exportCsv).
* `compare.py`: the comparison table (standard library only).
* `baseline_perrun.csv`: the 480 counted runs of the four baseline models, one row per run.
* `tasks.json`: the 40 tasks with the Data OS id of each task and of its 5 hour copy.
* `report/`: the report builder (fetch traces from Data OS, analyse, build the site and the Doc, leak scan).
