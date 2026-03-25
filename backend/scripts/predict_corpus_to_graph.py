from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoModelForTokenClassification, AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.modeling.registry import get_active_model
from scripts.export_graph_csv import export_graph_records

DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "clean_text" / "shanghanlun_cleaned.txt"
DEFAULT_OUTPUT_JSONL = DATA_DIR / "annotation" / "model_predicted_corpus.jsonl"
DEFAULT_GRAPH_OUTPUT_DIR = DATA_DIR / "processed" / "graph-model-predicted"
DEFAULT_NER_MODEL_DIR = PROJECT_ROOT / "models" / "baseline" / "ner" / "guwenbert-ner-baseline" / "best"
DEFAULT_RELATION_MODEL_DIR = PROJECT_ROOT / "models" / "baseline" / "relation" / "guwenbert-relation-baseline" / "best"

ALLOWED_ENTITY_TYPES = {"SYNDROME", "SYMPTOM", "FORMULA", "HERB", "THERAPY", "ADMINISTRATION"}
PAIR_TO_RELATION = {
    ("SYNDROME", "SYMPTOM"): "SYNDROME_HAS_SYMPTOM",
    ("SYNDROME", "FORMULA"): "SYNDROME_TO_FORMULA",
    ("FORMULA", "HERB"): "FORMULA_CONTAINS_HERB",
    ("FORMULA", "ADMINISTRATION"): "FORMULA_HAS_ADMINISTRATION",
}
NO_RELATION = "NO_RELATION"


def resolve_model_dir(task: str, fallback: Path) -> Path:
    active = get_active_model(task)
    model_dir = Path(str(active.get("model_dir") or "")) if active else fallback
    if not model_dir.exists():
        return fallback
    return model_dir


def load_lines(path: Path, limit: int = 0) -> list[str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit > 0:
        lines = lines[:limit]
    return lines


def infer_entry_type(text: str) -> str:
    formula_markers = ["汤方", "散方", "丸方", "右", "煮取", "去滓", "温服"]
    if any(marker in text for marker in formula_markers):
        return "formula_entry"
    return "syndrome_entry"


def decode_entities(text: str, labels: list[str]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    current_type: str | None = None
    current_start: int | None = None

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


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, int]] = set()
    output: list[dict[str, Any]] = []
    for entity in sorted(entities, key=lambda item: (int(item["start"]), int(item["end"]), str(item["type"]))):
        entity_type = str(entity["type"])
        start = int(entity["start"])
        end = int(entity["end"])
        if entity_type not in ALLOWED_ENTITY_TYPES:
            continue
        if start < 0 or end > len(entity["text"]) + start or start >= end:
            continue
        signature = (entity_type, start, end)
        if signature in seen:
            continue
        seen.add(signature)
        output.append(entity)
    return output


def predict_ner_entities(
    *,
    text: str,
    tokenizer: AutoTokenizer,
    model: AutoModelForTokenClassification,
) -> list[dict[str, Any]]:
    tokens = list(text)
    encoded = tokenizer(tokens, is_split_into_words=True, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        logits = model(**encoded).logits
    predictions = logits.argmax(dim=-1).squeeze(0).tolist()
    word_ids = encoded.word_ids(batch_index=0)
    labels: list[str] = []
    seen_word_ids: set[int] = set()
    for token_prediction, word_id in zip(predictions, word_ids):
        if word_id is None or word_id in seen_word_ids:
            continue
        labels.append(str(model.config.id2label[token_prediction]))
        seen_word_ids.add(word_id)
    entities = decode_entities(text, labels)
    filtered = []
    for entity in entities:
        start = int(entity["start"])
        end = int(entity["end"])
        if start < 0 or end > len(text) or start >= end:
            continue
        mention_text = text[start:end]
        if not mention_text.strip():
            continue
        filtered.append(
            {
                "type": str(entity["type"]),
                "text": mention_text,
                "start": start,
                "end": end,
            }
        )
    return deduplicate_entities(filtered)


def mark_entity_pair(text: str, head: dict[str, Any], tail: dict[str, Any]) -> str:
    segments = [
        (int(head["start"]), int(head["end"]), "[HEAD]", "[/HEAD]"),
        (int(tail["start"]), int(tail["end"]), "[TAIL]", "[/TAIL]"),
    ]
    if max(segments[0][0], segments[1][0]) < min(segments[0][1], segments[1][1]):
        raise ValueError("Overlapping entity spans are not supported.")
    segments.sort(key=lambda item: item[0], reverse=True)

    marked = text
    for start, end, prefix, suffix in segments:
        marked = marked[:start] + prefix + marked[start:end] + suffix + marked[end:]
    return marked


def build_relation_candidates(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for head_index, head in enumerate(entities):
        for tail_index, tail in enumerate(entities):
            if head_index == tail_index:
                continue
            pair = (str(head["type"]), str(tail["type"]))
            relation_type = PAIR_TO_RELATION.get(pair)
            if relation_type is None:
                continue
            candidates.append(
                {
                    "head_index": head_index,
                    "tail_index": tail_index,
                    "relation_type": relation_type,
                    "head": head,
                    "tail": tail,
                }
            )
    return candidates


def batch_predict_relations(
    *,
    text: str,
    candidates: list[dict[str, Any]],
    tokenizer: AutoTokenizer,
    model: AutoModelForSequenceClassification,
    threshold: float,
    batch_size: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    label_to_id = {str(label): int(label_id) for label_id, label in model.config.id2label.items()}
    expected_labels = {row["relation_type"] for row in candidates}
    required_labels = expected_labels | {NO_RELATION}
    missing = [label for label in required_labels if label not in label_to_id]
    if missing:
        raise RuntimeError(f"Relation model missing labels: {missing}")

    results: list[dict[str, Any]] = []

    for offset in range(0, len(candidates), batch_size):
        chunk = candidates[offset : offset + batch_size]
        sequence_texts: list[str] = []
        for row in chunk:
            marked_text = mark_entity_pair(text, row["head"], row["tail"])
            sequence_text = (
                f"{marked_text}\nHEAD_TYPE={row['head']['type']};TAIL_TYPE={row['tail']['type']}"
            )
            sequence_texts.append(sequence_text)

        encoded = tokenizer(
            sequence_texts,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=256,
        )
        with torch.no_grad():
            logits = model(**encoded).logits
        probabilities = torch.softmax(logits, dim=-1).tolist()

        for row, prob_vector in zip(chunk, probabilities):
            expected_label = str(row["relation_type"])
            expected_score = float(prob_vector[label_to_id[expected_label]])
            no_relation_score = float(prob_vector[label_to_id[NO_RELATION]])
            if expected_score >= threshold and expected_score > no_relation_score:
                results.append(
                    {
                        "type": expected_label,
                        "head_index": int(row["head_index"]),
                        "tail_index": int(row["tail_index"]),
                        "confidence": round(expected_score, 6),
                        "source": "model",
                    }
                )

    deduped: dict[tuple[int, int, str], dict[str, Any]] = {}
    for relation in results:
        key = (relation["head_index"], relation["tail_index"], relation["type"])
        current = deduped.get(key)
        if current is None or float(relation["confidence"]) > float(current["confidence"]):
            deduped[key] = relation
    return list(deduped.values())


def to_record(
    *,
    index: int,
    text: str,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    local_entities: list[dict[str, Any]] = []
    for i, entity in enumerate(entities, start=1):
        local_entities.append(
            {
                "id": f"e{i}",
                "type": entity["type"],
                "text": entity["text"],
                "start": int(entity["start"]),
                "end": int(entity["end"]),
                "source": "model",
            }
        )

    local_relations: list[dict[str, Any]] = []
    for relation in relations:
        head_id = f"e{int(relation['head_index']) + 1}"
        tail_id = f"e{int(relation['tail_index']) + 1}"
        local_relations.append(
            {
                "type": relation["type"],
                "head": head_id,
                "tail": tail_id,
                "source": relation.get("source", "model"),
                "confidence": float(relation.get("confidence", 0.0)),
            }
        )

    return {
        "id": f"line-{index:04d}",
        "text": text,
        "entities": local_entities,
        "relations": local_relations,
        "meta": {
            "line_number": index,
            "entry_type": infer_entry_type(text),
            "generated_by": "model_batch_prediction",
        },
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_pipeline(
    *,
    input_path: Path,
    output_jsonl: Path,
    graph_output_dir: Path,
    run_name: str,
    relation_threshold: float,
    relation_batch_size: int,
    limit: int,
    activate: bool,
    ner_model_dir: Path,
    relation_model_dir: Path,
) -> dict[str, Any]:
    lines = load_lines(input_path, limit=limit)
    if not lines:
        raise RuntimeError(f"No non-empty lines found: {input_path}")

    ner_tokenizer = AutoTokenizer.from_pretrained(ner_model_dir)
    ner_model = AutoModelForTokenClassification.from_pretrained(ner_model_dir)

    relation_tokenizer = AutoTokenizer.from_pretrained(relation_model_dir)
    relation_model = AutoModelForSequenceClassification.from_pretrained(relation_model_dir)

    records: list[dict[str, Any]] = []
    entity_type_counter: Counter[str] = Counter()
    relation_type_counter: Counter[str] = Counter()

    for index, text in enumerate(lines, start=1):
        entities = predict_ner_entities(text=text, tokenizer=ner_tokenizer, model=ner_model)
        candidates = build_relation_candidates(entities)
        relations = batch_predict_relations(
            text=text,
            candidates=candidates,
            tokenizer=relation_tokenizer,
            model=relation_model,
            threshold=relation_threshold,
            batch_size=relation_batch_size,
        )

        record = to_record(index=index, text=text, entities=entities, relations=relations)
        records.append(record)

        for entity in record["entities"]:
            entity_type_counter[str(entity["type"])] += 1
        for relation in record["relations"]:
            relation_type_counter[str(relation["type"])] += 1

        if index % 50 == 0:
            print(f"[progress] processed {index}/{len(lines)} lines", flush=True)

    write_jsonl(output_jsonl, records)
    graph_summary = export_graph_records(
        records,
        graph_output_dir,
        run_name=run_name,
        activate=activate,
        input_path=output_jsonl,
        source_type="model_predicted",
    )

    return {
        "input_path": str(input_path),
        "output_jsonl": str(output_jsonl),
        "graph_output_dir": str(graph_output_dir),
        "run_name": run_name,
        "ner_model_dir": str(ner_model_dir),
        "relation_model_dir": str(relation_model_dir),
        "line_count": len(lines),
        "entity_count_by_type": dict(sorted(entity_type_counter.items())),
        "relation_count_by_type": dict(sorted(relation_type_counter.items())),
        "graph_summary": graph_summary,
        "created_at": datetime.now().astimezone().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict full corpus with active NER/RE models and export an active graph version.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--graph-output-dir", type=Path, default=DEFAULT_GRAPH_OUTPUT_DIR)
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--relation-threshold", type=float, default=0.5)
    parser.add_argument("--relation-batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--ner-model-dir", type=Path, default=None)
    parser.add_argument("--relation-model-dir", type=Path, default=None)
    args = parser.parse_args()

    ner_model_dir = args.ner_model_dir or resolve_model_dir("ner", DEFAULT_NER_MODEL_DIR)
    relation_model_dir = args.relation_model_dir or resolve_model_dir("relation", DEFAULT_RELATION_MODEL_DIR)
    if not ner_model_dir.exists():
        raise RuntimeError(f"NER model directory not found: {ner_model_dir}")
    if not relation_model_dir.exists():
        raise RuntimeError(f"Relation model directory not found: {relation_model_dir}")

    run_name = args.run_name.strip() or f"model-graph-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    summary = run_pipeline(
        input_path=args.input,
        output_jsonl=args.output_jsonl,
        graph_output_dir=args.graph_output_dir,
        run_name=run_name,
        relation_threshold=float(args.relation_threshold),
        relation_batch_size=max(1, int(args.relation_batch_size)),
        limit=max(0, int(args.limit)),
        activate=not args.no_activate,
        ner_model_dir=ner_model_dir,
        relation_model_dir=relation_model_dir,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
