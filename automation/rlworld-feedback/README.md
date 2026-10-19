# RL World feedback from a DataOS download

RL World's External QC page takes a feedback JSON file under "Upload QC Feedback". This folder gets an RL World task ready for DataOS, and turns the DataOS "Task with runs" or "Dataset with runs" download back into that file.

## Before DataOS

Tasks downloaded from RL World do not carry the judge key or long enough time limits for DataOS. Run this on the RL World download, then upload the `_dataos_ready.zip` it writes to DataOS:

```bash
python qc.py rlworld-prep <rl world download>.zip
```

It sets `[agent] timeout_sec` to 14400 and `[verifier] timeout_sec` to 3600 when they are lower, and adds `ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"` under `[verifier.env]`. No other file changes.

## After DataOS

```bash
python qc.py rlworld <dataset>_with_runs.zip
```

- You get two files per task in `qc_rlworld_out/`: `<task id>-v<version>-external-qc-feedback.json` and `<task id>-v<version>-dataos-with-runs.zip`.
- Open that exact task version in RL World, go to its External QC page, click "Upload QC Feedback" and choose the JSON. Tested on prod on 2026-10-15 with task nurse_practitioners v19: the upload returned "QC feedback uploaded" and the 7 findings appeared as feedback items.
- Do not upload the zip to prod yet. Prod's zip import is older than RL World's main branch and refused every DataOS review it was given on 2026-10-15 (it does not read the code fence around the verdict JSON). RL World main reads it, and expands summaries like "all 31 verifiers", since PR 1174. Once that release reaches prod, the zip uploads as is.
- Each finding becomes a blocking item, so uploading sends the version back for rework. When all 4 reviews accept, the upload approves the version.
- `python qc.py release` writes the same files into `qc_release_out/rlworld_feedback/` as part of step 3, so you usually do not need a separate run.

## Which tasks it converts

- **A task downloaded from RL World**: its DataOS folder is named `<task id>-v<version>-dataos-harbor`, and the task id and version come from that name. This is the normal case.
- **Any other task**: the folder has no RL World name, so it is skipped with a message. For a one-task zip, give `--task-id` and `--version` to convert it anyway.
- **A task DataOS reviewed more than once**: only the newest 4 reviews are used, which is one pipeline run. `--all-reviews` keeps the older ones too.

## Files

- `dataos_findings_to_feedback_json.py` is Camus Lam's converter from the RL World team. It was shared in Slack on 2026-10-14, and Luiz Araujo tested it on RL World prod tasks. Only the code layout was reformatted; the logic is unchanged. It can also be run alone on a one-task zip: `python dataos_findings_to_feedback_json.py EXPORT.zip`.
- `qc.py rlworld` splits a many-task download into one zip per task, keeps the newest 4 reviews, and runs the converter on each.

This is a stopgap. When RL World ships its own DataOS zip import, upload the zip there instead.
