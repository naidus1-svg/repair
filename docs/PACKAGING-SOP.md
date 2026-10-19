# Packaging SOP: turning passed tasks into something a customer can open

For the packaging team. Written 2026-10-14. Owner: Khiem Doan. The build tool is [`packaging/build_eval_zips.py`](../packaging/build_eval_zips.py); its tests are [`packaging/test_eval_counting.py`](../packaging/test_eval_counting.py).

Packaging means: a requester (sales, a customer lead, or Andrew) asks for tasks, samples, a folder, a zip or a report, and you build exactly that from tasks that have finished QC. Most asks have a deadline the same day.

## 1. What comes in

Seven kinds of ask. Real asks from 2026-09-14 to 2026-10-12 (24 in four weeks, customers not named here).

| Kind | What was asked | What it needs |
|---|---|---|
| Sample pack by domain | 1 to 2 samples for each of 4 domains by 5 PM the same day; 3 per domain were sent | Pick by quality and domain; send one more than asked so the customer can choose |
| Everything that passed, one folder | All passing tasks, 512 SVC and 530 EKW, same day; a downloaded copy of the passed set (532 SVC and 625 EKW) staged on GCS because the DataOS download was too slow | A passing-only filter that is right, and a place to stage a large set |
| Folders and zips with a summary sheet | 192 finance tasks as zips shared one by one, summary sheet in the passed-QC list format; two tasks replaced mid-day | Folder per domain, summary sheet, swap a task without rebuilding all |
| Eval evidence zips | 10 samples at k=3 plus a 50-task run; judge changed at the customer's request | The right trials, the right k, the harness named in the file name |
| Report or breakdown | Which tasks a customer bought, finance first; DataOS-style results with a report PDF, a sheet and zips | A filtered sheet that matches what they bought; a report from run data |
| "Do we have X" and volume | Ready volume for two benches and a minimum order; a fit check against a customer request (5 items judged a poor fit) | A number you can defend with the time you read it, and a quick fit judgment |
| Delivery logistics | Put a bench on an external drive and post it to blob storage; shipping address and SAS token still missing | Ask for the missing logistics item first; it blocks everything |

A new type as of 2026-10-13: choose a subset of long-horizon tasks for expensive model runs and a failure analysis. The selection is the whole job.

## 2. Where "passed" comes from

A task is packageable only after the four QC steps: GitHub checks, the DataOS pipeline (oracle run, no-op run, 2 evals, 4 comprehensive reviews that all accept), the manager review, then manual review. A task still in a step, or rejected, is not in the pool.

- **SVC and EKW:** the consolidated tracker is the pool of record. Filter to the passed status; never use a copy from last week or a DataOS download older than the ask.
- **Other pods (tax, legal, medical, company bench, sheet recipes, EKW-OTS and the rest):** each pod keeps its own sheet. The links are in the table below and in the QC team leads channel pins.

| Pod or domain | Sheet | What it is |
|---|---|---|
| SVC and EKW (pool of record) | [Consolidated sheet](https://docs.google.com/spreadsheets/d/1X0vP1QuAZNqeSOT-bHKR8lye8fcVVuFFyA1f1bg0XNc/edit?gid=1720843765) | Where pod leads upload approved tasks. Start here for any SVC or EKW ask. |
| SVC and EKW | [SVC QC tracker](https://docs.google.com/spreadsheets/d/1JmpP38bcOUDmKlkx_2HndB4GdncPgObC4-_vnQFNaw4/edit?gid=973351887) | Per-task QC and rework status; the EKW bundle script adds a row per task ([EKW tab](https://docs.google.com/spreadsheets/d/1JmpP38bcOUDmKlkx_2HndB4GdncPgObC4-_vnQFNaw4/edit?gid=537173372)). Use it to see why a task is not in the pool. |
| EKW-OTS and Company Bench | [QC Tracker](https://docs.google.com/spreadsheets/d/1X0vP1QuAZNqeSOT-bHKR8lye8fcVVuFFyA1f1bg0XNc/edit?gid=416594350) | Pending tasks for these two pods |
| Company Bench | [Internal tracker](https://docs.google.com/spreadsheets/d/1DA7CTg74vjf0m8aDI6pGhXQ0Gp61LY9VZ6v-ZklhDGU/edit?usp=sharing) | The pod's own tabs by person and batch |
| Tax | [PMA task tracker](https://docs.google.com/spreadsheets/d/1X0vP1QuAZNqeSOT-bHKR8lye8fcVVuFFyA1f1bg0XNc/edit?gid=889398860) | Where tax tasks are logged for review |
| Tax | [Internal pod sheet](https://docs.google.com/spreadsheets/d/18WlVRq1xdwwqWTnOhekSKLLBOTwL0xp6AZecpJTXYM4/edit?gid=0) | Tasks picked up; must match the PMA tracker |
| Pod leads | [Pending and rejected sheet](https://docs.google.com/spreadsheets/d/1F02SBuSIbqSA5jfM19Wm-u7rSknUnKU7mYe2aYOVHQc/edit?gid=1523286527) | Pending tasks per person and tasks rejected after approval |
| Legal, medical, sheet recipes | none found | No sheet link was posted in the leads channels as of 2026-10-14. Ask the pod lead in the first message of the ask. |

Team roster and pod assignments are in the [QC Team Structure](https://docs.google.com/spreadsheets/d/1U2frJ6eK88xel-tlyP4CICDNyzTVRYso9bfQl6NO5WY/edit?gid=570670823) sheet.

When two sources disagree about whether a task passed, the consolidated tracker wins; tell Khiem which task and which sheet disagree.

## 3. The seven steps

1. **Restate the ask in one line** in the packaging channel: customer, what, how many, deadline in Pacific, who receives it. If a number or the recipient is missing, ask the requester once in the same thread.
2. **Pick the pool.** The right sheet from section 2, filtered to passed.
3. **Select.** Domain first, then quality, then difficulty. Leave out any task with a major review finding or a QC note. For customer samples prefer tasks the customer's own team can judge without extra context. Write one line per pick saying why.
4. **Build.** One folder per domain (or the customer's format). Names the customer can read. A summary sheet in the passed-QC list format. For eval evidence use the tool in section 6.
5. **Check.** Every line in section 4, by a second person when the deadline allows.
6. **Get approval, then deliver.** Post the folder link and your check results in the ask's thread. Khiem replies approved. Only then send it to the requester or the customer (section 5).
7. **Log.** One row in the request log: asked time, who, customer, what, size, deadline, finished time, who did it, link to the folder.

How long it takes, from the log: a domain sample pack took 15 minutes to about 4 hours; a passing-only folder was built the same day; an eval-backed set with a report took 2 days; a new full SVC sample run is 1 to 2 days. Say the expected time back to the requester in step 1.

## 4. Checks before anything leaves

Every one of these has failed at least once.

- **No answer key.** No `solution/`, `golden_output`, `answer_key`, or expected values anywhere in a folder or zip a customer or a model will read. Match `solution` as a whole path segment, not a substring.
- **No internal figures.** No pricing, unit cost, owner names, or internal model results on anything customer-facing.
- **The count matches the ask and the sheet.** Files in the folder equal rows in the summary sheet.
- **Open every zip.** `zipfile.ZipFile(path).testzip()` must return `None`. A half-uploaded file returns a file id and success; only the byte size differs, so compare the uploaded size with the local size.
- **Eval zips:** one `evals/` root, one model folder, trials numbered 1 to N with no gap, N equals k, a verifier reward in every trial folder, no `lease.json`.
- **Windows long names.** File names written by models break Windows paths and a copy can still report success. Check the missing-object list.
- **Keep the runs.** Copy task folders with their runs; a re-export without them loses the runs and they cannot be rebuilt.
- **Rebuild after a top-up run lands,** or the zip ships the older trial set.
- **Customer-confidential data.** The Company Bench corpus is real redacted data. Never name a counterparty in a sample, a summary or a message.

## 5. Delivery and approval

- In the first weeks you can send to customers, **after Khiem approves in the thread**. No approval, no send.
- Shared folders: share by link to the requester's address. Large sets are staged on GCS first.
- If a delivery needs a logistics item (address, token, access), get it before you build.
- The same request twice is a repeat: reuse the earlier folder and say what changed.

## 6. Building evals.zip and which trials count

```
python packaging/build_eval_zips.py --tasks <id1,id2> --k 10
python packaging/build_eval_zips.py --tasks <id> --bucket long-horizon-evals-beta \
    --model xai__grok-4.6 --agent grok-build \
    --zip-name eval_grok_4.6_grok_build.zip --k 4
```

Needs the gcloud CLI signed in with read on the evals bucket. Output goes to `./eval_zips/out` and `./eval_zips/work` unless you pass `--out` and `--work`.

- **Always pass `--k`.** It is the only thing that separates a duplicate re-fire from a top-up.
- **Grok Build needs `--agent grok-build`.** The model name does not say which harness ran, so without it a different harness's trials ship under the wrong name.
- **Pass `--model` first.** It cuts a build from minutes to seconds per task.
- **A live trial blocks the build.** A trial with `lease.json` and no reward is still running; the tool refuses that task.
- The tool runs six checks and deletes a zip that fails any: entry count equals the resolved count, no duplicate names, names match exactly, everything under `evals/`, model folders equal the models present, no `solution`, `golden_output` or `answer_key`. Do not weaken them. Then run the cold audit in section 4 on the finished file.

### Which trials count (the counting rules)

The rule lives in `packaging/eval_counting.py`. Do not write another copy. Four scripts once carried four copies and every copy was wrong a different way.

1. A revision and an execution are one dimension. A (revision, execution) pair is a slot, oldest first.
2. The earliest slot that holds a full k scored trials is the task's result. Any later slot is an accidental re-fire.
3. A slot holding more than k scored trials is capped at k in trial order.
4. If no slot reaches k alone, the slots combine in trial order, capped at k. That is a top-up.
5. Only scored trials count, and the choice is by trial number, never by reward. Choosing a task's best k results is not its result.

Run `python packaging/test_eval_counting.py` after any change. All 29 tests must pass.

## 7. Logging, handoffs and who to ask

- **Handoff** at the end of each shift in the packaging channel: open asks, what is built, what is blocked, the next deadline, who to ask.
- **Escalation:** pod lead for process questions, then Salman, then Khiem. If you hear nothing in 2 hours, message again.
- **Do not wait quietly** when you are blocked on access or credits.
