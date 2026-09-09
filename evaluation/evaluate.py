#!/usr/bin/env python3
"""Strict, portable scorer for JmangaBench-Syn R33 JSONL submissions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
import sys
import unicodedata
from typing import Any

SUBSETS = ("real", "realscan", "enhanced")
SCHEMA = "jmangabench_syn_r33_evaluation_v1"


def edit_distance(left: str, right: str) -> int:
    """Levenshtein distance without an optional third-party dependency."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, a in enumerate(left, 1):
        current = [row]
        for column, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (a != b)))
        previous = current
    return previous[-1]


class Score:
    def __init__(self) -> None:
        self.samples = self.exact = self.distance = self.characters = 0

    def add(self, reference: str, prediction: str) -> None:
        self.samples += 1
        self.exact += reference == prediction
        self.distance += edit_distance(reference, prediction)
        self.characters += len(reference)

    def report(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "exact_matches": self.exact,
            "edit_distance": self.distance,
            "reference_characters": self.characters,
            "em": self.exact / self.samples if self.samples else None,
            "cer": self.distance / self.characters if self.characters else None,
        }


def body_text(text: str) -> str:
    """Optional diagnostic view: remove Unicode P*/S* only.

    This retains letters, numbers and marks, including U+30FC (Lm, prolonged
    sound mark).  A standalone spacing dakuten/handakuten U+309B/U+309C is Sk
    and is therefore removed; a combining dakuten/handakuten is Mn and stays.
    V2.2 NFC/alias normalization is applied before this view is made.
    """
    return "".join(char for char in text if unicodedata.category(char)[0] not in {"P", "S"})


def read_jsonl(path: Path, kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                issues.append({"kind": "blank_line", "file": kind, "line": number})
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append({"kind": "invalid_json", "file": kind, "line": number,
                               "detail": str(error)})
                continue
            if not isinstance(value, dict):
                issues.append({"kind": "not_object", "file": kind, "line": number})
                continue
            value["_line"] = number
            rows.append(value)
    return rows, issues


def validate_manifest(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for row in rows:
        sample_id = row.get("id")
        valid = (isinstance(sample_id, str) and sample_id and
                 row.get("subset") in SUBSETS and
                 isinstance(row.get("image"), str) and bool(row["image"]) and
                 isinstance(row.get("reference"), str))
        if not valid:
            issues.append({"kind": "invalid_manifest_record", "line": row["_line"],
                           "id": sample_id})
            continue
        if sample_id in by_id:
            issues.append({"kind": "duplicate_manifest_id", "id": sample_id,
                           "line": row["_line"], "first_line": by_id[sample_id]["_line"]})
            continue
        by_id[sample_id] = row
    return by_id, issues


def validate_predictions(rows: list[dict[str, Any]], manifest: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for row in rows:
        sample_id = row.get("id")
        if (not isinstance(sample_id, str) or not sample_id or
                not isinstance(row.get("prediction"), str) or
                (row.get("error") is not None and not isinstance(row["error"], str))):
            issues.append({"kind": "invalid_prediction_record", "line": row["_line"], "id": sample_id})
            continue
        if sample_id in by_id:
            issues.append({"kind": "duplicate_prediction_id", "id": sample_id,
                           "line": row["_line"], "first_line": by_id[sample_id]["_line"]})
            continue
        if sample_id not in manifest:
            issues.append({"kind": "unknown_prediction_id", "id": sample_id, "line": row["_line"]})
            continue
        by_id[sample_id] = row
    return by_id, issues


def paired_groups(manifest: dict[str, dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest.values():
        group = row.get("paired_group_id")
        if group is not None:
            groups[str(group)].append(row)
    role_sets = Counter(tuple(sorted(str(row.get("pair_role", "")) for row in rows)) for rows in groups.values())
    return {"groups": len(groups), "samples": sum(map(len, groups.values())),
            "group_sizes": dict(sorted(Counter(map(len, groups.values())).items())),
            "role_sets": {"|".join(key): value for key, value in sorted(role_sets.items())}}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(here: Path) -> list[dict[str, Any]]:
    lock = json.loads((here / "LOCK.json").read_text(encoding="utf-8"))
    issues = []
    for name, expected in lock["sha256"].items():
        actual = sha256(here / name)
        if actual != expected:
            issues.append({"kind": "normalization_lock_mismatch", "file": name,
                           "expected_sha256": expected, "actual_sha256": actual})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="score missing predictions as empty, but retain all validation errors in the report")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    os.environ["JMANGA_NORMALIZATION_PRESET"] = str((here / "normalization_presets_semantic_visual_v2.yaml").resolve())
    manifest_rows, issues = read_jsonl(args.manifest, "manifest")
    issues.extend(verify_lock(here))
    sys.path.insert(0, str(here))
    from semantic_visual_v2_translation_eval import (
        EVALUATION_POLICY,
        normalize_pair,
        render_translation_normalized,
    )
    prediction_rows, prediction_parse_issues = read_jsonl(args.predictions, "predictions")
    issues.extend(prediction_parse_issues)
    manifest, manifest_issues = validate_manifest(manifest_rows)
    issues.extend(manifest_issues)
    predictions, prediction_issues = validate_predictions(prediction_rows, manifest)
    issues.extend(prediction_issues)
    missing = sorted(set(manifest) - set(predictions))
    issues.extend({"kind": "missing_prediction", "id": sample_id} for sample_id in missing)

    scores = {view: {subset: Score() for subset in (*SUBSETS, "all")} for view in ("v2_2", "raw", "body")}
    body_excluded = 0
    empty_reference_by_subset = Counter()
    normalization_fallbacks = 0
    prediction_errors: list[dict[str, Any]] = []
    for sample_id, row in manifest.items():
        prediction_row = predictions.get(sample_id)
        prediction = prediction_row["prediction"] if prediction_row else ""
        error = prediction_row.get("error") if prediction_row else None
        if error:
            prediction_errors.append({"id": sample_id, "error": str(error)})
        try:
            normalized_reference, normalized_prediction = normalize_pair(row["reference"], prediction)
        except (TypeError, ValueError) as error:
            # The raw view remains exact.  Strict mode cannot publish this run;
            # retaining unnormalized text here preserves the sample and exposes
            # the failure instead of deleting or silently repairing it.
            issues.append({"kind": "normalization_error", "id": sample_id, "detail": str(error)})
            normalized_reference, normalized_prediction = row["reference"], prediction
            normalization_fallbacks += 1
        reference_body = body_text(render_translation_normalized(normalized_reference))
        prediction_body = body_text(render_translation_normalized(normalized_prediction))
        if not reference_body:
            body_excluded += 1
        if not normalized_reference:
            empty_reference_by_subset[row["subset"]] += 1
            empty_reference_by_subset["all"] += 1
        for subset in (row["subset"], "all"):
            scores["v2_2"][subset].add(normalized_reference, normalized_prediction)
            scores["raw"][subset].add(row["reference"], prediction)
            if reference_body:
                scores["body"][subset].add(reference_body, prediction_body)

    strict_exit = bool(issues) and not args.allow_incomplete
    payload = {
        "schema": SCHEMA,
        "normalization": EVALUATION_POLICY,
        "metric_contract": "Main EM/CER: V2.2 normalized full text; CER is character-weighted.",
        "strict": not args.allow_incomplete,
        "valid": not issues,
        "inputs": {"manifest_sha256": sha256(args.manifest),
                   "predictions_sha256": sha256(args.predictions)},
        "counts": {"manifest_records": len(manifest), "prediction_records": len(predictions),
                   "missing_predictions": len(missing), "prediction_error_records": len(prediction_errors),
                   "body_excluded_empty_reference": body_excluded,
                   "normalization_fallback_raw_records": normalization_fallbacks,
                   "empty_reference_by_subset": {subset: empty_reference_by_subset[subset]
                                                 for subset in (*SUBSETS, "all")}},
        "metrics": {view: {subset: score.report() for subset, score in by_subset.items()}
                    for view, by_subset in scores.items()},
        "paired_groups": paired_groups(manifest),
        "validation_issues": issues,
        "prediction_errors": prediction_errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": payload["valid"], "counts": payload["counts"],
                      "v2_2": payload["metrics"]["v2_2"]}, ensure_ascii=False, indent=2))
    return 2 if strict_exit else 0


if __name__ == "__main__":
    raise SystemExit(main())
