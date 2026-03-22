from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "baseline" / "relation" / "guwenbert-relation-baseline" / "best"


def resolve_span(text: str, entity: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entity)
    entity_text = str(payload.get("text") or "").strip()
    entity_type = str(payload.get("type") or "").strip()
    start = payload.get("start")
    end = payload.get("end")

    if start is None or end is None:
        if not entity_text:
            raise ValueError("Entity text is required when start/end are not provided.")
        start = text.find(entity_text)
        if start < 0:
            raise ValueError(f"Entity text not found in sentence: {entity_text}")
        end = start + len(entity_text)

    start = int(start)
    end = int(end)
    if start < 0 or end > len(text) or start >= end:
        raise ValueError(f"Invalid entity span: {start}-{end}")
    if not entity_text:
        entity_text = text[start:end]

    return {
        "text": entity_text,
        "type": entity_type,
        "start": start,
        "end": end,
    }


def mark_entity_pair(text: str, head: dict[str, Any], tail: dict[str, Any]) -> str:
    head_start = int(head["start"])
    head_end = int(head["end"])
    tail_start = int(tail["start"])
    tail_end = int(tail["end"])
    if max(head_start, tail_start) < min(head_end, tail_end):
        raise ValueError("Overlapping entity spans are not supported.")

    segments = [
        (head_start, head_end, "[HEAD]", "[/HEAD]"),
        (tail_start, tail_end, "[TAIL]", "[/TAIL]"),
    ]
    segments.sort(key=lambda item: item[0], reverse=True)

    marked_text = text
    for start, end, prefix, suffix in segments:
        marked_text = marked_text[:start] + prefix + marked_text[start:end] + suffix + marked_text[end:]
    return marked_text


def build_sequence_text(text: str, head: dict[str, Any], tail: dict[str, Any]) -> str:
    marked_text = mark_entity_pair(text, head, tail)
    return f"{marked_text}\nHEAD_TYPE={head['type']};TAIL_TYPE={tail['type']}"


def predict(model_dir: Path, text: str, head: dict[str, Any], tail: dict[str, Any]) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)

    resolved_head = resolve_span(text, head)
    resolved_tail = resolve_span(text, tail)
    sequence_text = build_sequence_text(text, resolved_head, resolved_tail)

    encoded = tokenizer(sequence_text, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        logits = model(**encoded).logits

    probabilities = torch.softmax(logits, dim=-1).squeeze(0)
    predicted_id = int(torch.argmax(probabilities).item())
    topk = min(5, probabilities.shape[0])
    top_values, top_indices = torch.topk(probabilities, k=topk)

    return {
        "text": text,
        "head": resolved_head,
        "tail": resolved_tail,
        "sequence_text": sequence_text,
        "label": model.config.id2label[predicted_id],
        "confidence": float(probabilities[predicted_id].item()),
        "top_predictions": [
            {
                "label": model.config.id2label[int(index.item())],
                "score": float(value.item()),
            }
            for value, index in zip(top_values, top_indices)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run relation baseline inference on a single Shanghanlun sentence.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--text", type=str, required=True)
    parser.add_argument("--head-text", type=str, required=True)
    parser.add_argument("--head-type", type=str, required=True)
    parser.add_argument("--head-start", type=int)
    parser.add_argument("--head-end", type=int)
    parser.add_argument("--tail-text", type=str, required=True)
    parser.add_argument("--tail-type", type=str, required=True)
    parser.add_argument("--tail-start", type=int)
    parser.add_argument("--tail-end", type=int)
    args = parser.parse_args()

    result = predict(
        model_dir=args.model_dir,
        text=args.text,
        head={"text": args.head_text, "type": args.head_type, "start": args.head_start, "end": args.head_end},
        tail={"text": args.tail_text, "type": args.tail_type, "start": args.tail_start, "end": args.tail_end},
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
