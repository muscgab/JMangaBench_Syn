from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "evaluate.py"


def run(tmp_path: Path, manifest: list[dict], predictions: list[dict]) -> tuple[subprocess.CompletedProcess[str], dict]:
    manifest_path, predictions_path, output = tmp_path / "manifest.jsonl", tmp_path / "predictions.jsonl", tmp_path / "report.json"
    manifest_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in manifest), encoding="utf-8")
    predictions_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in predictions), encoding="utf-8")
    process = subprocess.run([sys.executable, str(EVALUATOR), "--manifest", str(manifest_path), "--predictions", str(predictions_path), "--output", str(output)], text=True, capture_output=True)
    return process, json.loads(output.read_text(encoding="utf-8"))


def test_v21_main_score_raw_score_subsets_and_weighted_cer(tmp_path: Path) -> None:
    manifest = [
        {"id": "a", "subset": "real", "image": "a.png", "reference": "『待て』・・・"},
        {"id": "b", "subset": "realscan", "image": "b.png", "reference": "abc"},
        {"id": "c", "subset": "enhanced", "image": "c.png", "reference": ""},
    ]
    predictions = [
        {"id": "a", "prediction": "「待て」......", "error": None},
        {"id": "b", "prediction": "axc", "error": ""},
        {"id": "c", "prediction": "x", "error": ""},
    ]
    process, report = run(tmp_path, manifest, predictions)
    assert process.returncode == 0
    assert report["metrics"]["v2_2"]["real"]["em"] == 1
    assert report["metrics"]["raw"]["real"]["em"] == 0
    all_v21 = report["metrics"]["v2_2"]["all"]
    assert (all_v21["edit_distance"], all_v21["reference_characters"], all_v21["cer"]) == (2, 8, 2 / 8)
    assert report["counts"]["body_excluded_empty_reference"] == 1


def test_strict_mode_reports_duplicate_missing_and_error_without_dropping(tmp_path: Path) -> None:
    manifest = [{"id": "a", "subset": "real", "image": "a.png", "reference": "ab"}, {"id": "b", "subset": "real", "image": "b.png", "reference": "c"}]
    predictions = [{"id": "a", "prediction": "ab", "error": "backend timeout"}, {"id": "a", "prediction": "ab", "error": ""}]
    process, report = run(tmp_path, manifest, predictions)
    assert process.returncode == 2 and not report["valid"]
    kinds = {issue["kind"] for issue in report["validation_issues"]}
    assert {"duplicate_prediction_id", "missing_prediction"} <= kinds
    assert report["counts"]["prediction_error_records"] == 1
    assert report["metrics"]["v2_2"]["all"]["samples"] == 2


def test_rejects_duplicate_manifest_id_and_bad_prediction_schema(tmp_path: Path) -> None:
    manifest = [{"id": "a", "subset": "real", "image": "a.png", "reference": "a"}, {"id": "a", "subset": "real", "image": "b.png", "reference": "b"}]
    predictions = [{"id": "a", "prediction": 3, "error": ""}]
    process, report = run(tmp_path, manifest, predictions)
    assert process.returncode == 2
    kinds = {issue["kind"] for issue in report["validation_issues"]}
    assert {"duplicate_manifest_id", "invalid_prediction_record", "missing_prediction"} <= kinds


def test_reports_paired_group_shape_without_treating_members_as_independent_groups(tmp_path: Path) -> None:
    manifest = [
        {"id": f"a{i}", "subset": "real", "image": f"a{i}.png", "reference": "a",
         "paired_group_id": "draft-1", "pair_role": role}
        for i, role in enumerate(("normal_unlikely", "normal_possible", "scan_unlikely", "scan_possible"))
    ]
    predictions = [{"id": row["id"], "prediction": "a", "error": ""} for row in manifest]
    process, report = run(tmp_path, manifest, predictions)
    assert process.returncode == 0
    assert report["paired_groups"] == {"groups": 1, "samples": 4, "group_sizes": {"4": 1},
                                       "role_sets": {"normal_possible|normal_unlikely|scan_possible|scan_unlikely": 1}}


def test_body_renders_private_ellipsis_token_then_excludes_punctuation_only_reference(tmp_path: Path) -> None:
    manifest = [{"id": "dots", "subset": "enhanced", "image": "dots.png", "reference": "......"}]
    predictions = [{"id": "dots", "prediction": "・・・", "error": ""}]
    process, report = run(tmp_path, manifest, predictions)
    assert process.returncode == 0
    assert report["metrics"]["v2_2"]["all"]["em"] == 1
    assert report["counts"]["body_excluded_empty_reference"] == 1
    assert report["counts"]["empty_reference_by_subset"]["enhanced"] == 0
    assert report["metrics"]["body"]["all"]["samples"] == 0


def test_normalization_error_is_reported_and_strictly_fails_without_dropping_raw_sample(tmp_path: Path) -> None:
    manifest = [{"id": "bad", "subset": "real", "image": "bad.png", "reference": "a\x01"}]
    predictions = [{"id": "bad", "prediction": "a", "error": ""}]
    process, report = run(tmp_path, manifest, predictions)
    assert process.returncode == 2 and not report["valid"]
    assert report["counts"]["normalization_fallback_raw_records"] == 1
    assert report["metrics"]["raw"]["all"]["samples"] == 1
    assert any(issue["kind"] == "normalization_error" for issue in report["validation_issues"])
