#!/usr/bin/env python3
"""Convert a DataOS findings-format export into an External QC feedback JSON file.

DataOS now writes each Comprehensive Review as a list of findings, which the
platform's DataOS ZIP import does not read yet. This script turns such an
export into the feedback JSON file the External QC page already accepts, so
it can be uploaded with "Upload QC Feedback" as a .json file.

Usage:
    python3 dataos_findings_to_feedback_json.py EXPORT.zip
    python3 dataos_findings_to_feedback_json.py EXPORT.zip --task-id TASK_ID --version 13
    python3 dataos_findings_to_feedback_json.py EXPORT.zip --output feedback.json

Task id and version: read from the export's package folder, which keeps the
name of the DataOS package downloaded from the platform,
"<task id>-v<version>-dataos-harbor". Pass --task-id and --version if the
download was renamed before it went to DataOS. The External QC page refuses a
file whose task id or version differs from the page's.

The feedback written:
  - one blocking item per finding. Any finding sends the version back for
    rework, matching DataOS, which ships a task only when every review
    accepts it;
  - one pass item for each review that accepted the task. If every review
    accepted, the upload approves the version.
Each finding lists tests/verifier.json (where its criteria live) and the
package files its evidence cites. Its explanation holds the review, the
criteria at risk, the evidence, and the answer the grader would wrongly fail.

The script refuses an export it can't read faithfully: a report that isn't a
comprehensive review, a report file name without a review id, two reports
with the same id, a verdict JSON that is missing, malformed, or inconsistent
(say, "reject" with no findings), the retired ten-check format, or a report
whose ## task_ids doesn't list its revision folder's DataOS task.

Criteria are read against the package's tests/verifier.json. A reviewer that
summarizes them ("all 31 verifiers (workbook_*, note_*, deck_*)") gets the
verifier names the summary covers; text that names no verifier is kept as
written. Either way the script says so in a warning. A text field longer
than the upload allows is shortened, with a note saying so, and a warning.

Unlike the platform's ZIP import, the script can't confirm the reviews were
run on this version's exact package. Upload the JSON only to the task
version named in it, and only from the download DataOS reviewed.

Needs Python 3.8 or later and nothing else. Exit status: 0 on success, 1 when
the export can't be converted, 2 for a usage error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

FINDING_TYPE_LABELS = {
    "READINGS": "Several valid readings",
    "WRONG_VALUE": "Wrong expected value",
    "GOLDEN": "Wrong golden answer",
    "CONFLICT": "Conflicting requirement",
    "UNASKED": "Unasked requirement",
    "WEAK_GRADER": "Weak grader",
    "GRADER_BUG": "Grader bug",
}
ACCEPT, REJECT = "accept", "reject"
REVIEW_TYPE = "COMPREHENSIVE_REVIEW"
TRANSCRIPT_HEADER = "transcript"
VERDICT_KEYS = {"overall_verdict", "major_count", "findings", "readings_count"}
FINDING_KEYS = {
    "type",
    "severity",
    "criteria",
    "weight_at_risk",
    "evidence",
    "correct_answer_that_fails",
    "fix",
}
RETIRED_FORMAT_KEY = "checks"

# Upload limits of the External QC feedback file, and the API's 10 MB request
# body limit, less room for the request's other fields.
LIMITS = {
    "category": 200,
    "description": 2_000,
    "explanation": 10_000,
    "remediation": 10_000,
    "overallNotes": 20_000,
}
MAX_FEEDBACK_BYTES = 9 * 1024 * 1024
MAX_LISTED_CRITERIA = 50
MAX_VERDICT_CANDIDATES = 50

FEEDBACK_ID_PREFIX = "dataos-"
ACCEPTED_CATEGORY = "DataOS review accepted"
ACCEPTED_REMEDIATION = "No changes required."
HARBOR_PREFIX = "harbor_task/"
VERIFIER_JSON = "tests/verifier.json"
SEPARATOR = " \u00b7 "
TRUNCATION_NOTE = (
    "\n\n[Shortened to fit the upload limit; the full text is in the DataOS report.]"
)

REPORT_ENTRY = re.compile(
    r"^(?P<root>(?:[^/]+/)*)verifications/(?P<file>comprehensive_review_[^/]*\.md)$"
)
REPORT_FILE = re.compile(r"^comprehensive_review_(?P<id>[1-9]\d*)(?:_[^/]*)?\.md$")
PACKAGE_FOLDER = re.compile(r"^(?P<task>.+)-v(?P<version>[1-9]\d*)-dataos-harbor$")
REVISION_FOLDER = re.compile(r"^rev_\d+__(?P<dataos_task>\d+)$")
HEADER_KEY = re.compile(r"^## (\S+)\s*$")
ANSWER_LINE = re.compile(r"^A:\s?")
FENCE_LINE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
# How a reviewer may summarize criteria instead of naming them: "all 31
# verifiers", "all the criteria", or patterns such as `workbook_*`.
ALL_CRITERIA = re.compile(
    r"\ball\b(?:\s+(?:of\s+)?the)?(?:\s+(?P<count>\d+))?\s+(?:rubric\s+)?(?:verifiers|criteria|checks)\b",
    re.IGNORECASE,
)
CRITERION_PATTERN = re.compile(r"[\w.-]*\*[\w.*-]*")
CRITERION_TOKEN = re.compile(r"[\w.-]+")
BACKTICKED = re.compile(r"`([^`\n]+)`")
PATH_TOKEN = re.compile(
    r"(?<![\w/.-])((?:\.{1,2}/|/)?(?:[\w.@+-]+/)*[\w@+-][\w.@+-]*\.[A-Za-z][A-Za-z0-9]{0,9})(?::\d+(?:-\d+)?)?"
)

EVIDENCE_SEPARATOR = " | "
EVIDENCE_LABELS = {
    "source or run": "Source or run",
    "criterion": "Criterion",
    "prompt": "Prompt",
    "source": "Source",
    "run": "Run",
}
# Where the reviewer saw package files, mapped back to package paths: the task
# image's /workspace folders, DataOS's /app/, and the export's own folders.
CONTAINER_ROOTS = (
    ("workspace/environment/", "environment/"),
    ("workspace/data/", "environment/data/"),
    ("workspace/tests/", "tests/"),
    ("app/", ""),
    ("task_files/", ""),
    ("harbor_task/", ""),
)
# A model run's outputs; the golden solution keeps same-named copies under
# solution/output/, which a quote of the prompt must not point at.
RUN_OUTPUT_ROOTS = ("output/", "workspace/output/")
# Files a finding never points at: the verifier harness DataOS regenerates and
# the vendored document skills.
NOT_CITABLE_FILES = {
    "tests/test.sh",
    "tests/verifier_runtime.py",
    "tests/verifier_runtime.pyrun",
    "tests/dataos_discovery_probe.py",
}
NOT_CITABLE_PREFIXES = (
    "tests/verifier_lib/",
    "tests/__verifier_lib/",
    "environment/skills/",
)
EXTENSIONLESS_FILE_NAMES = {"Dockerfile"}


class ConversionError(Exception):
    """The export can't be converted faithfully; the message says why."""


@dataclass
class Finding:
    type: str
    criteria: List[str]
    weight_at_risk: float
    evidence: str
    correct_answer_that_fails: str
    fix: str


@dataclass
class Review:
    review_id: int
    file_name: str
    agent: str
    model: str
    verdict: str
    findings: List[Finding]
    readings_count: int
    dataos_task_ids: List[int] = field(default_factory=list)
    evaluation_run_ids: List[int] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"Review {self.review_id} ({self.agent}{SEPARATOR}{self.model})"


@dataclass
class Export:
    task_id: Optional[str]
    version: Optional[int]
    dataos_task_id: Optional[int]
    reviews: List[Review]
    package_paths: List[str]


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


# --- Reading the export -------------------------------------------------------


def read_export(zip_path: Path) -> Export:
    """Reads every comprehensive review, and the reviewed package's file list."""
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ConversionError(f"{zip_path} is not a readable ZIP: {error}") from error
    with archive:
        names = {info.filename.replace("\\", "/"): info for info in archive.infolist()}
        matches = [(name, REPORT_ENTRY.match(name)) for name in names]
        reports = [(name, match) for name, match in matches if match]
        if not reports:
            raise ConversionError(
                "the ZIP has no verifications/comprehensive_review_*.md report; is it a DataOS export?"
            )
        roots = sorted({match.group("root") for _, match in reports})
        if len(roots) > 1:
            raise ConversionError(
                "the reports come from more than one revision folder: "
                + ", ".join(root or "(archive root)" for root in roots)
            )
        root = roots[0]
        identified = []
        for name, match in reports:
            file_name = match.group("file")
            id_match = REPORT_FILE.match(file_name)
            if not id_match:
                raise ConversionError(
                    f"{file_name} doesn't start with a DataOS review id (comprehensive_review_<id>...)"
                )
            identified.append((int(id_match.group("id")), file_name, name))
        identified.sort()
        for (left, _, _), (right, file_name, _) in zip(identified, identified[1:]):
            if left == right:
                raise ConversionError(
                    f"two reports have review id {right} ({file_name})"
                )
        reviews = [
            parse_report(
                review_id, file_name, decode(archive.read(names[name]), file_name)
            )
            for review_id, file_name, name in identified
        ]
        package_prefix = f"{root}task_files/"
        package_paths = sorted(
            name[len(package_prefix) :]
            for name, info in names.items()
            if name.startswith(package_prefix) and not info.is_dir()
        )
        verifier_json = names.get(f"{package_prefix}{VERIFIER_JSON}")
        rubric = rubric_criteria(archive.read(verifier_json)) if verifier_json else None
    task_id, version, dataos_task_id = identify_package(root)
    check_revision(reviews, dataos_task_id)
    for review in reviews:
        resolve_review_criteria(review, rubric)
    return Export(task_id, version, dataos_task_id, reviews, package_paths)


def rubric_criteria(content: bytes) -> Optional[List[str]]:
    """The verifier names in the reviewed package's tests/verifier.json, in its order."""
    try:
        verifiers = json.loads(content.decode("utf-8")).get("verifiers")
        names = [
            verifier["name"]
            for verifier in verifiers
            if isinstance(verifier.get("name"), str)
        ]
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        AttributeError,
        TypeError,
        KeyError,
    ):
        return None
    return list(dict.fromkeys(names))


def check_revision(reviews: Sequence[Review], dataos_task_id: Optional[int]) -> None:
    """Refuses a report moved in from another DataOS revision."""
    if dataos_task_id is None:
        warn(
            "the reports aren't in a rev_<n>__<DataOS task id> folder; can't check they belong together"
        )
        return
    for review in reviews:
        if review.dataos_task_ids and dataos_task_id not in review.dataos_task_ids:
            raise ConversionError(
                f"{review.file_name} lists DataOS task {review.dataos_task_ids}, "
                f"not {dataos_task_id} from its revision folder; it reviewed a different revision"
            )


def resolve_review_criteria(review: Review, rubric: Optional[List[str]]) -> None:
    """Reads each finding's criteria as verifier names from the package's rubric.

    Reviewers sometimes summarize instead of listing names, as in
    "all 31 verifiers (workbook_*, note_*, deck_*)". A summary is read as the
    verifier names it covers; text that names no verifier is kept as written.
    """
    for number, finding in enumerate(review.findings, 1):
        where = f"{review.file_name} finding {number}"
        if rubric is None:
            if finding.criteria:
                warn(
                    f"{where}: the package's {VERIFIER_JSON} is missing or unreadable; its criteria are kept as written"
                )
            continue
        resolved: List[str] = []
        for criterion in finding.criteria:
            if criterion in rubric:
                resolved.append(criterion)
                continue
            expanded = expand_criterion(criterion, rubric, where)
            if expanded:
                names = "name" if len(expanded) == 1 else "names"
                warn(
                    f"{where}: read {criterion!r} as {len(expanded)} verifier {names} from {VERIFIER_JSON}"
                )
                resolved += expanded
            else:
                warn(
                    f"{where}: {criterion!r} names no verifier in {VERIFIER_JSON}; kept as written"
                )
                resolved.append(criterion)
        finding.criteria = list(dict.fromkeys(resolved))


def expand_criterion(text: str, rubric: Sequence[str], where: str) -> List[str]:
    """The verifier names a criterion summary covers, in rubric order: every
    verifier for "all N verifiers", else the names its patterns (`workbook_*`)
    match and the names it spells out."""
    match = ALL_CRITERIA.search(text)
    if match:
        stated = match.group("count")
        if stated and int(stated) != len(rubric):
            warn(
                f"{where}: {text!r} counts {stated} verifiers, but {VERIFIER_JSON} has {len(rubric)}"
            )
        return list(rubric)
    covered = {
        name
        for pattern in CRITERION_PATTERN.findall(text)
        for name in rubric
        if fnmatch.fnmatchcase(name, pattern)
    }
    covered |= {token for token in CRITERION_TOKEN.findall(text) if token in rubric}
    return [name for name in rubric if name in covered]


def identify_package(root: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """The platform task id and version, and the DataOS task id, from the folder names."""
    segments = [segment for segment in root.split("/") if segment]
    revision = REVISION_FOLDER.match(segments[-1]) if segments else None
    dataos_task_id = int(revision.group("dataos_task")) if revision else None
    package = (
        PACKAGE_FOLDER.match(segments[-2]) if revision and len(segments) >= 2 else None
    )
    if not package:
        return None, None, dataos_task_id
    return package.group("task"), int(package.group("version")), dataos_task_id


def decode(content: bytes, file_name: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConversionError(f"{file_name} is not UTF-8 text: {error}") from error


def parse_report(review_id: int, file_name: str, text: str) -> Review:
    lines = text.splitlines()
    header = parse_header(lines, file_name)
    review_type = header.get("type", "")
    if review_type != REVIEW_TYPE:
        raise ConversionError(
            f"{file_name} is not a comprehensive review (## type is {review_type or 'missing'})"
        )
    verdict = parse_verdict(answer_lines(lines, file_name), file_name)
    return Review(
        review_id=review_id,
        file_name=file_name,
        agent=header_text(header, "agent", file_name),
        model=header_text(header, "model", file_name),
        verdict=verdict["overall_verdict"],
        findings=verdict["findings"],
        readings_count=verdict["readings_count"],
        dataos_task_ids=header_ids(header, "task_ids", file_name),
        evaluation_run_ids=header_ids(header, "evaluationrun_ids", file_name),
    )


def parse_header(lines: Sequence[str], file_name: str) -> Dict[str, str]:
    """The `## key` blocks before `## transcript`. `## status` is never read: DataOS
    writes PASSED whatever the verdict."""
    header: Dict[str, List[str]] = {}
    key: Optional[str] = None
    for line in lines:
        match = HEADER_KEY.match(line)
        if match:
            key = match.group(1)
            if key == TRANSCRIPT_HEADER:
                return {
                    name: "\n".join(value).strip() for name, value in header.items()
                }
            header[key] = []
        elif key is not None:
            header[key].append(line)
    raise ConversionError(f"{file_name} has no ## {TRANSCRIPT_HEADER} section")


def header_text(header: Dict[str, str], key: str, file_name: str) -> str:
    value = header.get(key, "")
    if not value:
        warn(f"{file_name} has no ## {key}; its feedback names it as unknown")
        return f"unknown {key}"
    return value


def header_ids(header: Dict[str, str], key: str, file_name: str) -> List[int]:
    try:
        ids = json.loads(header.get(key, ""))
    except json.JSONDecodeError:
        ids = None
    if not isinstance(ids, list) or not all(isinstance(item, int) for item in ids):
        warn(f"{file_name} has no readable ## {key}; the overall notes leave it out")
        return []
    return ids


# --- The verdict JSON ---------------------------------------------------------


def answer_lines(lines: Sequence[str], file_name: str) -> List[str]:
    """The reviewer's last answer, from its `A:` line on; the prompt before it is never read."""
    starts = [index for index, line in enumerate(lines) if ANSWER_LINE.match(line)]
    if not starts:
        raise ConversionError(f"{file_name} has no 'A:' answer, so no verdict")
    start = starts[-1]
    return [ANSWER_LINE.sub("", lines[start], count=1), *lines[start + 1 :]]


def fenced_blocks(lines: Sequence[str]) -> List[Tuple[int, int]]:
    """Fenced code blocks as Markdown reads them; a fence left open runs to the end."""
    blocks: List[Tuple[int, int]] = []
    opening: Optional[Tuple[int, str]] = None
    for index, line in enumerate(lines):
        match = FENCE_LINE.match(line)
        if not match:
            continue
        fence, rest = match.group(1), match.group(2)
        if opening is None:
            if not (fence.startswith("`") and "`" in rest):
                opening = (index, fence)
        elif (
            fence[0] == opening[1][0]
            and len(fence) >= len(opening[1])
            and not rest.strip()
        ):
            blocks.append((opening[0], index))
            opening = None
    if opening is not None:
        blocks.append((opening[0], len(lines)))
    return blocks


def leading_json_object(text: str) -> Optional[str]:
    """The JSON object `text` starts with, up to its closing brace, skipping braces in strings."""
    depth, in_string, escaped = 0, False, False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[: index + 1]
    return None


def verdict_candidates(answer: Sequence[str]) -> List[str]:
    """Every stretch of the answer that may hold the verdict, latest first."""
    blocks = fenced_blocks(answer)
    candidates = [
        (opening, "\n".join(answer[opening + 1 : closing]))
        for opening, closing in blocks
        if "\n".join(answer[opening + 1 : closing]).lstrip().startswith("{")
    ]
    next_line = 0
    for index, line in enumerate(answer):
        inside_block = any(opening <= index <= closing for opening, closing in blocks)
        if index < next_line or inside_block or not line.lstrip().startswith("{"):
            continue
        limit = next((opening for opening, _ in blocks if opening > index), len(answer))
        rest = "\n".join(answer[index:limit]).lstrip()
        found = leading_json_object(rest)
        candidates.append((index, found if found is not None else rest))
        if found is not None:
            next_line = index + found.count("\n") + 1
    candidates.sort(key=lambda candidate: -candidate[0])
    return [text for _, text in candidates]


def parse_verdict(answer: Sequence[str], file_name: str) -> dict:
    candidates = verdict_candidates(answer)
    if not candidates:
        raise ConversionError(f"{file_name}: the reviewer's answer has no verdict JSON")
    first_error: Optional[json.JSONDecodeError] = None
    for text in candidates[:MAX_VERDICT_CANDIDATES]:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            first_error = first_error or error
            continue
        return validate_verdict(value, file_name)
    raise ConversionError(f"{file_name}: the verdict JSON is invalid: {first_error}")


def validate_verdict(value: object, file_name: str) -> dict:
    if not isinstance(value, dict):
        raise ConversionError(f"{file_name}: the verdict JSON is not an object")
    if RETIRED_FORMAT_KEY in value and "findings" not in value:
        raise ConversionError(
            f"{file_name} uses DataOS's retired ten-check format; upload that export as a ZIP instead"
        )
    unknown = sorted(set(value) - VERDICT_KEYS)
    if unknown:
        warn(f"{file_name}: ignoring unknown verdict fields {unknown}")
    verdict = value.get("overall_verdict")
    if verdict not in (ACCEPT, REJECT):
        raise ConversionError(
            f"{file_name}: overall_verdict must be 'accept' or 'reject', not {verdict!r}"
        )
    raw_findings = value.get("findings")
    if not isinstance(raw_findings, list):
        raise ConversionError(f"{file_name}: findings must be a list")
    findings = [
        parse_finding(raw, f"{file_name} finding {index}")
        for index, raw in enumerate(raw_findings, 1)
    ]
    major_count = non_negative_int(
        value.get("major_count"), f"{file_name}: major_count"
    )
    readings_count = non_negative_int(
        value.get("readings_count"), f"{file_name}: readings_count"
    )
    if major_count != len(findings):
        raise ConversionError(
            f"{file_name}: major_count is {major_count}, but the findings list has {len(findings)}"
        )
    if (verdict == REJECT) != bool(findings):
        raise ConversionError(
            f"{file_name}: the verdict is {verdict!r} with {len(findings)} findings; "
            "a review rejects exactly when it has findings"
        )
    return {
        "overall_verdict": verdict,
        "findings": findings,
        "readings_count": readings_count,
    }


def parse_finding(raw: object, where: str) -> Finding:
    if not isinstance(raw, dict):
        raise ConversionError(f"{where} is not an object")
    unknown = sorted(set(raw) - FINDING_KEYS)
    if unknown:
        warn(f"{where}: ignoring unknown fields {unknown}")
    finding_type = raw.get("type")
    if finding_type not in FINDING_TYPE_LABELS:
        raise ConversionError(f"{where}: unknown finding type {finding_type!r}")
    if raw.get("severity", "major") != "major":
        warn(
            f"{where}: severity is {raw.get('severity')!r}; it is imported as a blocking finding anyway"
        )
    criteria = raw.get("criteria")
    if not isinstance(criteria, list) or not all(
        isinstance(item, str) and item.strip() for item in criteria
    ):
        raise ConversionError(f"{where}: criteria must be a list of criterion names")
    weight = raw.get("weight_at_risk")
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not 0 <= weight <= 1
    ):
        raise ConversionError(f"{where}: weight_at_risk must be a number from 0 to 1")
    return Finding(
        type=finding_type,
        criteria=list(dict.fromkeys(item.strip() for item in criteria)),
        weight_at_risk=float(weight),
        evidence=required_text(raw.get("evidence"), f"{where}: evidence"),
        correct_answer_that_fails=required_text(
            raw.get("correct_answer_that_fails"), f"{where}: correct_answer_that_fails"
        ),
        fix=required_text(raw.get("fix"), f"{where}: fix"),
    )


def non_negative_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConversionError(f"{what} must be a whole number, 0 or more")
    return value


def required_text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConversionError(f"{what} must be non-empty text")
    return value.strip()


# --- Cited files --------------------------------------------------------------


class PackageIndex:
    """The reviewed package's files a finding may point at."""

    def __init__(self, paths: Sequence[str]):
        self.paths = {path for path in paths if is_citable(path)}
        self.by_name: Dict[str, List[str]] = {}
        for path in sorted(self.paths):
            self.by_name.setdefault(path.rsplit("/", 1)[-1], []).append(path)

    def resolve(self, cited: str) -> Optional[str]:
        raw = cited.strip().lstrip("/")
        while raw.startswith("./"):
            raw = raw[2:]
        mapped = raw
        for root, replacement in CONTAINER_ROOTS:
            if raw.startswith(root):
                mapped = replacement + raw[len(root) :]
                break
        if raw.startswith(RUN_OUTPUT_ROOTS) or mapped.startswith(RUN_OUTPUT_ROOTS):
            return None
        if mapped in self.paths:
            return mapped
        candidates = self.by_name.get(mapped.rsplit("/", 1)[-1], [])
        if "/" in mapped:
            candidates = [path for path in candidates if path.endswith(f"/{mapped}")]
        return candidates[0] if len(candidates) == 1 else None


def is_citable(path: str) -> bool:
    return path not in NOT_CITABLE_FILES and not path.startswith(NOT_CITABLE_PREFIXES)


def cited_files(evidence: str, package: PackageIndex) -> List[str]:
    """Package files the evidence names, in the order it names them."""
    spans: List[Tuple[int, str, bool]] = [
        (match.start(), match.group(1), True) for match in BACKTICKED.finditer(evidence)
    ]
    spans += [
        (match.start(), match.group(1), False)
        for match in PATH_TOKEN.finditer(evidence)
    ]
    resolved: List[str] = []
    for _, token, backticked in sorted(spans):
        cited = LINE_SUFFIX.sub("", token.strip())
        name = cited.rsplit("/", 1)[-1]
        if "." not in name and not backticked and name not in EXTENSIONLESS_FILE_NAMES:
            continue
        path = package.resolve(cited)
        if path and path not in resolved:
            resolved.append(path)
    return resolved


# --- Feedback -----------------------------------------------------------------


def fit(text: str, limit: int, what: str) -> str:
    if len(text) <= limit:
        return text
    warn(f"{what} is {len(text)} characters; shortened to the {limit}-character limit")
    return text[: limit - len(TRUNCATION_NOTE)].rstrip() + TRUNCATION_NOTE


def describe_criteria(criteria: Sequence[str]) -> Optional[str]:
    if not criteria:
        return None
    return criteria[0] if len(criteria) == 1 else f"{len(criteria)} criteria"


def format_evidence(evidence: str) -> str:
    bullets = []
    for part in (piece.strip() for piece in evidence.split(EVIDENCE_SEPARATOR)):
        if not part:
            continue
        label = next(
            (
                EVIDENCE_LABELS[prefix]
                for prefix in EVIDENCE_LABELS
                if part.lower().startswith(prefix)
                and part[len(prefix) :].lstrip().startswith(":")
            ),
            None,
        )
        text = part.split(":", 1)[1].strip() if label else part
        bullets.append(f"- **{label}:** {text}" if label else f"- {text}")
    return "\n".join(bullets)


def explain(review: Review, finding: Finding) -> str:
    parts = [f"**{review.label}**"]
    if finding.criteria:
        listed = [
            f"`{criterion}`" for criterion in finding.criteria[:MAX_LISTED_CRITERIA]
        ]
        unlisted = len(finding.criteria) - len(listed)
        if unlisted:
            listed.append(f"and {unlisted} more")
        parts.append(
            f"**Criteria at risk ({len(finding.criteria)}):** {', '.join(listed)}"
        )
    parts.append(format_evidence(finding.evidence))
    parts.append(f"**Why a correct answer fails:** {finding.correct_answer_that_fails}")
    return "\n\n".join(parts)


def finding_item(
    review: Review, finding: Finding, number: int, package: PackageIndex
) -> dict:
    where = f"review {review.review_id} finding {number}"
    artifacts = (
        [VERIFIER_JSON] if finding.criteria and VERIFIER_JSON in package.paths else []
    )
    artifacts += [
        path for path in cited_files(finding.evidence, package) if path not in artifacts
    ]
    description = SEPARATOR.join(
        part
        for part in (
            f"Review {review.review_id}",
            f"finding {number}",
            f"{round(finding.weight_at_risk * 100)}% of the grade at risk",
            describe_criteria(finding.criteria),
        )
        if part
    )
    return {
        "id": f"{FEEDBACK_ID_PREFIX}{review.review_id}-{number}",
        "category": FINDING_TYPE_LABELS[finding.type],
        "description": fit(description, LIMITS["description"], f"{where} description"),
        "severity": "blocking",
        "artifacts": [f"{HARBOR_PREFIX}{path}" for path in artifacts],
        "explanation": fit(
            explain(review, finding), LIMITS["explanation"], f"{where} explanation"
        ),
        "remediation": fit(finding.fix, LIMITS["remediation"], f"{where} fix"),
        "resolved": False,
        "verdict": "unlabeled",
        "autoVerdict": "true_positive",
    }


def accepted_item(review: Review) -> dict:
    explanation = (
        f"**{review.label}** accepted the task with no findings. "
        f"Defensible readings of the main answers: {review.readings_count}."
    )
    return {
        "id": f"{FEEDBACK_ID_PREFIX}{review.review_id}-accept",
        "category": ACCEPTED_CATEGORY,
        "description": f"Review {review.review_id}{SEPARATOR}no findings",
        "severity": "pass",
        "artifacts": [],
        "explanation": fit(
            explanation, LIMITS["explanation"], f"review {review.review_id} explanation"
        ),
        "remediation": ACCEPTED_REMEDIATION,
        "resolved": False,
        "verdict": "unlabeled",
        "autoVerdict": "true_positive",
    }


def overall_notes(export: Export) -> str:
    lines = []
    for review in export.reviews:
        count = len(review.findings)
        types = (
            f" ({', '.join(finding.type for finding in review.findings)})"
            if count
            else ""
        )
        readings = "reading" if review.readings_count == 1 else "readings"
        lines.append(
            f"{review.label}: {review.verdict}, {count} finding{'' if count == 1 else 's'}{types}, "
            f"{review.readings_count} defensible {readings}."
        )
    run_ids = sorted(
        {run for review in export.reviews for run in review.evaluation_run_ids}
    )
    provenance = [
        f"Converted from {len(export.reviews)} DataOS comprehensive review{'' if len(export.reviews) == 1 else 's'}"
    ]
    if export.dataos_task_id is not None:
        provenance.append(f"DataOS task {export.dataos_task_id}")
    if run_ids:
        provenance.append(f"evaluation runs {', '.join(str(run) for run in run_ids)}")
    lines.append(SEPARATOR.join(provenance))
    return fit("\n\n".join(lines), LIMITS["overallNotes"], "overall notes")


def build_feedback_file(export: Export, task_id: str, version: int) -> dict:
    package = PackageIndex(export.package_paths)
    feedback = []
    for review in export.reviews:
        if review.findings:
            feedback += [
                finding_item(review, finding, number, package)
                for number, finding in enumerate(review.findings, 1)
            ]
        else:
            feedback.append(accepted_item(review))
    return {
        "taskId": task_id,
        "version": version,
        "feedback": feedback,
        "overallNotes": overall_notes(export),
    }


def check_upload_rules(feedback_file: dict) -> None:
    """The checks the External QC page applies before it uploads the file."""
    ids = [item["id"] for item in feedback_file["feedback"]]
    if len(ids) != len(set(ids)):
        raise ConversionError("two feedback items share an id")
    for item in feedback_file["feedback"]:
        for key in ("category", "description", "explanation", "remediation"):
            if not item[key] or len(item[key]) > LIMITS[key]:
                raise ConversionError(f"{item['id']}: {key} is empty or too long")
        if item["severity"] == "pass" and item["verdict"] != "unlabeled":
            raise ConversionError(f"{item['id']}: a pass item must stay unlabeled")
    size = len(json.dumps(feedback_file, ensure_ascii=False).encode("utf-8"))
    if size > MAX_FEEDBACK_BYTES:
        raise ConversionError(
            f"the feedback is {size} bytes, more than one upload can carry ({MAX_FEEDBACK_BYTES})"
        )


# --- Command line -------------------------------------------------------------


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a DataOS findings-format export ZIP into the External QC feedback "
            "JSON file the platform accepts under 'Upload QC Feedback'."
        )
    )
    parser.add_argument("export", type=Path, help="the DataOS export ZIP")
    parser.add_argument(
        "--task-id", help="platform task id, when the package folder doesn't name it"
    )
    parser.add_argument(
        "--version",
        type=int,
        help="platform task version, when the package folder doesn't name it",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="where to write the JSON (default: <task id>-v<version>-external-qc-feedback.json here)",
    )
    args = parser.parse_args(argv)
    if args.version is not None and args.version < 1:
        parser.error("--version must be 1 or more")
    return args


def main(argv: Sequence[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        export = read_export(args.export)
        task_id = args.task_id or export.task_id
        version = args.version or export.version
        if not task_id or not version:
            raise ConversionError(
                "the export's package folder isn't named <task id>-v<version>-dataos-harbor; "
                "pass --task-id and --version"
            )
        if export.task_id and args.task_id and args.task_id != export.task_id:
            warn(
                f"--task-id {args.task_id} differs from the package folder's {export.task_id}"
            )
        if export.version and args.version and args.version != export.version:
            warn(
                f"--version {args.version} differs from the package folder's v{export.version}"
            )
        feedback_file = build_feedback_file(export, task_id, version)
        check_upload_rules(feedback_file)
    except ConversionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    safe_task_id = re.sub(r"[^\w.-]", "_", task_id)
    output = args.output or Path(f"{safe_task_id}-v{version}-external-qc-feedback.json")
    output.write_text(
        json.dumps(feedback_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    issues = sum(1 for item in feedback_file["feedback"] if item["severity"] != "pass")
    reviews = export.reviews
    rejected = sum(1 for review in reviews if review.verdict == REJECT)
    print(
        f"Task {task_id} v{version}: {len(reviews)} reviews, {rejected} rejected the task."
    )
    if issues:
        print(
            f"{issues} finding{'' if issues == 1 else 's'} to label; uploading sends the version back for rework."
        )
    else:
        print("No findings; uploading approves the version.")
    print(f"Wrote {output}")
    print(
        "Upload it on that task version's External QC page with 'Upload QC Feedback'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
