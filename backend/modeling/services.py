from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.conf import settings

DEFAULT_NER_BASE_MODEL = os.getenv("NER_BASE_MODEL", "ethanyt/guwenbert-base")
DEFAULT_RELATION_BASE_MODEL = os.getenv("RELATION_BASE_MODEL", DEFAULT_NER_BASE_MODEL)
DEFAULT_NER_MODEL_DIR = settings.PROJECT_ROOT / "models" / "baseline" / "ner" / "guwenbert-ner-baseline" / "best"
DEFAULT_RELATION_MODEL_DIR = settings.PROJECT_ROOT / "models" / "baseline" / "relation" / "guwenbert-relation-baseline" / "best"
DEFAULT_NER_DATASET_MANIFEST = settings.DATA_DIR / "processed" / "ner" / "dataset_manifest.json"
DEFAULT_RELATION_DATASET_MANIFEST = settings.DATA_DIR / "processed" / "relation" / "dataset_manifest.json"
DEFAULT_ACCEPTED_DATASET_DIR = settings.DATA_DIR / "processed" / "annotation"
DEFAULT_ACCEPTED_JSONL_PATH = DEFAULT_ACCEPTED_DATASET_DIR / "accepted_candidates.jsonl"
DEFAULT_ACCEPTED_REPORT_PATH = DEFAULT_ACCEPTED_DATASET_DIR / "accepted_candidates_report.json"
DEFAULT_INCREMENTAL_DIR = settings.DATA_DIR / "processed" / "annotation" / "incremental"
DEFAULT_INCREMENTAL_REPORT_PATH = DEFAULT_INCREMENTAL_DIR / "incremental_dataset_report.json"
DEFAULT_MERGED_ROOT = settings.DATA_DIR / "processed" / "merged"
DEFAULT_MERGED_REPORT_PATH = DEFAULT_MERGED_ROOT / "merge_report.json"
DEFAULT_MERGED_NER_MANIFEST = DEFAULT_MERGED_ROOT / "ner" / "dataset_manifest.json"
DEFAULT_MERGED_RELATION_MANIFEST = DEFAULT_MERGED_ROOT / "relation" / "dataset_manifest.json"
RUNTIME_DEPENDENCIES = ["torch", "transformers"]
RELATION_TYPE_COMPATIBILITY = {
    ("SYNDROME", "SYMPTOM"): ["SYNDROME_HAS_SYMPTOM", "NO_RELATION"],
    ("SYNDROME", "FORMULA"): ["SYNDROME_TO_FORMULA", "NO_RELATION"],
    ("FORMULA", "HERB"): ["FORMULA_CONTAINS_HERB", "NO_RELATION"],
    ("FORMULA", "ADMINISTRATION"): ["FORMULA_HAS_ADMINISTRATION", "NO_RELATION"],
}
FORMULA_TRIGGER_SUFFIX = "".join(chr(code) for code in (0x4E3B, 0x4E4B))
FORMULA_TRIGGER_PREFIXES = [
    "".join(chr(code) for code in (0x5B9C,)),
    "".join(chr(code) for code in (0x4E0E,)),
    "".join(chr(code) for code in (0x53EF, 0x4E0E)),
    "".join(chr(code) for code in (0x5F53, 0x4E0E)),
    "".join(chr(code) for code in (0x4E43, 0x53EF, 0x4E0E)),
]


class ModelUnavailableError(RuntimeError):
    pass


class InvalidModelInputError(ValueError):
    pass


def get_ner_model_dir() -> Path:
    configured = os.getenv("NER_MODEL_DIR")
    if configured:
        return Path(configured)
    return DEFAULT_NER_MODEL_DIR


def get_relation_model_dir() -> Path:
    configured = os.getenv("RELATION_MODEL_DIR")
    if configured:
        return Path(configured)
    return DEFAULT_RELATION_MODEL_DIR


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_report(path: Path) -> dict[str, Any]:
    payload = _load_manifest(path)
    return {
        "exists": payload is not None,
        "path": str(path),
        "updated_at": path.stat().st_mtime if path.exists() else None,
        "data": payload,
    }


def _missing_dependencies(package_names: list[str]) -> list[str]:
    missing: list[str] = []
    for package_name in package_names:
        try:
            __import__(package_name)
        except Exception:
            missing.append(package_name)
    return missing


def _artifact_commands() -> dict[str, str]:
    return {
        "prepare_ner_dataset": "python scripts/prepare_ner_dataset.py",
        "train_ner_baseline": "python scripts/train_ner_baseline.py",
        "prepare_relation_dataset": "python scripts/prepare_relation_dataset.py",
        "train_relation_baseline": "python scripts/train_relation_baseline.py",
        "export_accepted_candidates": "python scripts/export_accepted_candidates.py",
        "prepare_accepted_incremental_datasets": "python scripts/prepare_accepted_incremental_datasets.py",
        "merge_incremental_datasets": "python scripts/merge_incremental_datasets.py",
    }


def _accepted_pipeline_commands() -> dict[str, str]:
    return {
        "refresh_pipeline": "accepted -> export -> incremental -> merged",
        "train_ner_with_merged": (
            "python scripts/train_ner_baseline.py "
            f"--dataset-dir {DEFAULT_MERGED_ROOT / 'ner'} --epochs 3 --batch-size 4 "
            "--run-name guwenbert-ner-accepted-merged"
        ),
        "train_relation_with_merged": (
            "python scripts/train_relation_baseline.py "
            f"--dataset-dir {DEFAULT_MERGED_ROOT / 'relation'} --epochs 1 --batch-size 4 "
            "--run-name guwenbert-relation-accepted-merged"
        ),
    }


def get_accepted_pipeline_status() -> dict[str, Any]:
    accepted_report = _read_report(DEFAULT_ACCEPTED_REPORT_PATH)
    incremental_report = _read_report(DEFAULT_INCREMENTAL_REPORT_PATH)
    merge_report = _read_report(DEFAULT_MERGED_REPORT_PATH)
    merged_ner_manifest = _read_report(DEFAULT_MERGED_NER_MANIFEST)
    merged_relation_manifest = _read_report(DEFAULT_MERGED_RELATION_MANIFEST)

    return {
        "accepted_report": accepted_report,
        "incremental_report": incremental_report,
        "merge_report": merge_report,
        "merged_ner_manifest": merged_ner_manifest,
        "merged_relation_manifest": merged_relation_manifest,
        "commands": _accepted_pipeline_commands(),
    }


def run_accepted_pipeline_refresh(limit: int | None = None) -> dict[str, Any]:
    from scripts.export_accepted_candidates import export_accepted_candidates
    from scripts.merge_incremental_datasets import merge_incremental_datasets
    from scripts.prepare_accepted_incremental_datasets import prepare_incremental_datasets

    export_report = export_accepted_candidates(output_dir=DEFAULT_ACCEPTED_DATASET_DIR, limit=limit)
    incremental_report = prepare_incremental_datasets(
        accepted_path=DEFAULT_ACCEPTED_JSONL_PATH,
        output_dir=DEFAULT_INCREMENTAL_DIR,
    )
    merge_report = merge_incremental_datasets(
        ner_base_dir=settings.DATA_DIR / "processed" / "ner",
        relation_base_dir=settings.DATA_DIR / "processed" / "relation",
        incremental_dir=DEFAULT_INCREMENTAL_DIR,
        output_root=DEFAULT_MERGED_ROOT,
    )
    return {
        "export_report": export_report,
        "incremental_report": incremental_report,
        "merge_report": merge_report,
        "status": get_accepted_pipeline_status(),
    }


def _decode_entities(text: str, labels: list[str]) -> list[dict[str, object]]:
    entities = []
    current_type = None
    current_start = None

    for index, label in enumerate(labels + ["O"]):
        if label.startswith("B-"):
            if current_type is not None and current_start is not None:
                entities.append(
                    {
                        "type": current_type,
                        "text": text[current_start:index],
                        "start": current_start,
                        "end": index,
                    }
                )
            current_type = label[2:]
            current_start = index
        elif label.startswith("I-") and current_type == label[2:]:
            continue
        else:
            if current_type is not None and current_start is not None:
                entities.append(
                    {
                        "type": current_type,
                        "text": text[current_start:index],
                        "start": current_start,
                        "end": index,
                    }
                )
            current_type = None
            current_start = None

    return entities


def _resolve_entity_payload(text: str, entity: dict[str, Any], role: str) -> dict[str, Any]:
    payload = dict(entity)
    entity_text = str(payload.get("text") or "").strip()
    entity_type = str(payload.get("type") or "").strip()
    start = payload.get("start")
    end = payload.get("end")

    if not entity_type:
        raise InvalidModelInputError(f"{role}.type is required.")

    if start is None or end is None:
        if not entity_text:
            raise InvalidModelInputError(f"{role}.text is required when start/end are absent.")
        start = text.find(entity_text)
        if start < 0:
            raise InvalidModelInputError(f"{role}.text was not found in the input sentence.")
        end = start + len(entity_text)

    start = int(start)
    end = int(end)
    if start < 0 or end > len(text) or start >= end:
        raise InvalidModelInputError(f"{role} span is invalid: {start}-{end}.")

    if not entity_text:
        entity_text = text[start:end]

    return {
        "text": entity_text,
        "type": entity_type,
        "start": start,
        "end": end,
    }


def _mark_entity_pair(text: str, head: dict[str, Any], tail: dict[str, Any]) -> str:
    head_start = int(head["start"])
    head_end = int(head["end"])
    tail_start = int(tail["start"])
    tail_end = int(tail["end"])
    if max(head_start, tail_start) < min(head_end, tail_end):
        raise InvalidModelInputError("head and tail spans overlap.")

    segments = [
        (head_start, head_end, "[HEAD]", "[/HEAD]"),
        (tail_start, tail_end, "[TAIL]", "[/TAIL]"),
    ]
    segments.sort(key=lambda item: item[0], reverse=True)

    marked_text = text
    for start, end, prefix, suffix in segments:
        marked_text = marked_text[:start] + prefix + marked_text[start:end] + suffix + marked_text[end:]
    return marked_text


def _build_ranked_predictions(probabilities: Any, id2label: dict[int, str]) -> list[dict[str, float | str]]:
    ranked: list[dict[str, float | str]] = []
    for index in range(probabilities.shape[0]):
        ranked.append(
            {
                "label": id2label[int(index)],
                "score": float(probabilities[index].item()),
            }
        )
    ranked.sort(key=lambda item: float(item["score"]), reverse=True)
    return ranked


def _compatible_relation_labels(head_type: str, tail_type: str, labels: list[str]) -> list[str]:
    allowed = RELATION_TYPE_COMPATIBILITY.get((head_type, tail_type))
    if allowed is None:
        return ["NO_RELATION"] if "NO_RELATION" in labels else []
    return [label for label in allowed if label in labels]


def _has_formula_trigger(text: str, formula_text: str) -> bool:
    normalized_formula = formula_text.strip()
    if not normalized_formula:
        return False
    candidates = [f"{normalized_formula}{FORMULA_TRIGGER_SUFFIX}", *[f"{prefix}{normalized_formula}" for prefix in FORMULA_TRIGGER_PREFIXES]]
    return any(candidate in text for candidate in candidates)


def _apply_relation_heuristics(
    text: str,
    head: dict[str, Any],
    tail: dict[str, Any],
    constrained_result: dict[str, Any],
) -> dict[str, Any]:
    if (
        head.get("type") == "SYNDROME"
        and tail.get("type") == "FORMULA"
        and "SYNDROME_TO_FORMULA" in constrained_result.get("compatible_labels", [])
        and _has_formula_trigger(text, str(tail.get("text") or ""))
    ):
        boosted = next(
            (item for item in constrained_result["top_predictions"] if item["label"] == "SYNDROME_TO_FORMULA"),
            None,
        )
        if boosted is None:
            boosted = {"label": "SYNDROME_TO_FORMULA", "score": 0.0}
            constrained_result["top_predictions"] = [boosted, *constrained_result["top_predictions"]][:5]
        constrained_result["label"] = "SYNDROME_TO_FORMULA"
        constrained_result["confidence"] = float(boosted["score"])
        constrained_result["heuristic_override"] = True
        constrained_result["heuristic_reason"] = "formula_trigger"
        return constrained_result

    constrained_result["heuristic_override"] = False
    constrained_result["heuristic_reason"] = None
    return constrained_result


def _constrain_relation_predictions(
    probabilities: Any,
    id2label: dict[int, str],
    head_type: str,
    tail_type: str,
) -> dict[str, Any]:
    ranked_predictions = _build_ranked_predictions(probabilities, id2label)
    allowed_labels = _compatible_relation_labels(head_type, tail_type, [str(item["label"]) for item in ranked_predictions])

    constrained_predictions = [item for item in ranked_predictions if str(item["label"]) in allowed_labels]
    raw_prediction = ranked_predictions[0]

    if constrained_predictions:
        final_prediction = constrained_predictions[0]
    else:
        final_prediction = {"label": "NO_RELATION", "score": 1.0 if raw_prediction["label"] == "NO_RELATION" else 0.0}
        constrained_predictions = [final_prediction]

    return {
        "raw_label": str(raw_prediction["label"]),
        "raw_confidence": float(raw_prediction["score"]),
        "label": str(final_prediction["label"]),
        "confidence": float(final_prediction["score"]),
        "constraint_applied": str(raw_prediction["label"]) != str(final_prediction["label"]),
        "compatible_labels": allowed_labels,
        "top_predictions": constrained_predictions[:5],
    }


def get_ner_status() -> dict[str, Any]:
    model_dir = get_ner_model_dir()
    manifest = _load_manifest(DEFAULT_NER_DATASET_MANIFEST)
    missing_dependencies = _missing_dependencies(RUNTIME_DEPENDENCIES)
    checkpoint_exists = model_dir.exists()

    return {
        "ready": checkpoint_exists and not missing_dependencies,
        "base_model_name": DEFAULT_NER_BASE_MODEL,
        "model_dir": str(model_dir),
        "checkpoint_exists": checkpoint_exists,
        "dataset_manifest_exists": manifest is not None,
        "dataset_manifest_path": str(DEFAULT_NER_DATASET_MANIFEST),
        "missing_dependencies": missing_dependencies,
        "required_dependencies": RUNTIME_DEPENDENCIES,
        "label_list": list(manifest.get("label_list", [])) if manifest else [],
        "dataset_summary": manifest.get("splits") if manifest else None,
        "commands": _artifact_commands(),
    }


def get_relation_status() -> dict[str, Any]:
    model_dir = get_relation_model_dir()
    manifest = _load_manifest(DEFAULT_RELATION_DATASET_MANIFEST)
    missing_dependencies = _missing_dependencies(RUNTIME_DEPENDENCIES)
    checkpoint_exists = model_dir.exists()
    return {
        "ready": checkpoint_exists and not missing_dependencies,
        "base_model_name": DEFAULT_RELATION_BASE_MODEL,
        "model_dir": str(model_dir),
        "checkpoint_exists": checkpoint_exists,
        "dataset_manifest_exists": manifest is not None,
        "dataset_manifest_path": str(DEFAULT_RELATION_DATASET_MANIFEST),
        "missing_dependencies": missing_dependencies,
        "required_dependencies": RUNTIME_DEPENDENCIES,
        "label_list": list(manifest.get("label_list", [])) if manifest else [],
        "dataset_summary": manifest.get("splits") if manifest else None,
        "commands": _artifact_commands(),
    }


def get_model_summary() -> dict[str, Any]:
    return {
        "ner": get_ner_status(),
        "relation": get_relation_status(),
        "accepted_pipeline": get_accepted_pipeline_status(),
    }


def predict_ner(text: str) -> dict[str, Any]:
    model_dir = get_ner_model_dir()
    if not model_dir.exists():
        raise ModelUnavailableError(f"NER checkpoint not found: {model_dir}")

    try:
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer
    except Exception as exc:  # pragma: no cover
        raise ModelUnavailableError(f"NER runtime dependencies are unavailable: {exc}") from exc

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir)
    tokens = list(text)
    encoded = tokenizer(tokens, is_split_into_words=True, return_tensors="pt", truncation=True, max_length=256)

    with torch.no_grad():
        logits = model(**encoded).logits
    predictions = logits.argmax(dim=-1).squeeze(0).tolist()
    word_ids = encoded.word_ids(batch_index=0)

    labels: list[str] = []
    seen_word_ids = set()
    for prediction, word_id in zip(predictions, word_ids):
        if word_id is None or word_id in seen_word_ids:
            continue
        labels.append(model.config.id2label[prediction])
        seen_word_ids.add(word_id)

    return {
        "text": text,
        "tokens": tokens,
        "labels": labels,
        "entities": _decode_entities(text, labels),
    }


def predict_relation(text: str, head: dict[str, Any], tail: dict[str, Any]) -> dict[str, Any]:
    model_dir = get_relation_model_dir()
    if not model_dir.exists():
        raise ModelUnavailableError(f"Relation checkpoint not found: {model_dir}")

    resolved_head = _resolve_entity_payload(text, head, "head")
    resolved_tail = _resolve_entity_payload(text, tail, "tail")
    sequence_text = _mark_entity_pair(text, resolved_head, resolved_tail)
    sequence_text = f"{sequence_text}\nHEAD_TYPE={resolved_head['type']};TAIL_TYPE={resolved_tail['type']}"

    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except Exception as exc:  # pragma: no cover
        raise ModelUnavailableError(f"Relation runtime dependencies are unavailable: {exc}") from exc

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    encoded = tokenizer(sequence_text, return_tensors="pt", truncation=True, max_length=256)

    with torch.no_grad():
        logits = model(**encoded).logits

    probabilities = torch.softmax(logits, dim=-1).squeeze(0)
    constrained_result = _constrain_relation_predictions(
        probabilities=probabilities,
        id2label=model.config.id2label,
        head_type=str(resolved_head["type"]),
        tail_type=str(resolved_tail["type"]),
    )
    constrained_result = _apply_relation_heuristics(
        text=text,
        head=resolved_head,
        tail=resolved_tail,
        constrained_result=constrained_result,
    )

    return {
        "text": text,
        "head": resolved_head,
        "tail": resolved_tail,
        "sequence_text": sequence_text,
        **constrained_result,
    }
