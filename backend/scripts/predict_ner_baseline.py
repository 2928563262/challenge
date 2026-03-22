from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "baseline" / "ner" / "guwenbert-ner-baseline" / "best"


def decode_entities(text: str, labels: list[str]) -> list[dict[str, object]]:
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


def predict(model_dir: Path, text: str) -> dict[str, object]:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir)
    tokens = list(text)
    encoded = tokenizer(tokens, is_split_into_words=True, return_tensors="pt", truncation=True, max_length=256)

    with torch.no_grad():
        logits = model(**encoded).logits
    predictions = logits.argmax(dim=-1).squeeze(0).tolist()
    word_ids = encoded.word_ids(batch_index=0)

    char_labels: list[str] = []
    seen_word_ids = set()
    for token_prediction, word_id in zip(predictions, word_ids):
        if word_id is None or word_id in seen_word_ids:
            continue
        char_labels.append(model.config.id2label[token_prediction])
        seen_word_ids.add(word_id)

    entities = decode_entities(text, char_labels)
    return {
        "text": text,
        "tokens": tokens,
        "labels": char_labels,
        "entities": entities,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NER baseline inference on a single Shanghanlun sentence.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--text", type=str, required=True)
    args = parser.parse_args()

    result = predict(args.model_dir, args.text)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
