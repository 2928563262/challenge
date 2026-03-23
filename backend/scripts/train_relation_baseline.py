from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modeling.registry import infer_dataset_source, register_model_run

DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATASET_DIR = DATA_DIR / "processed" / "relation"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "models" / "baseline" / "relation"
DEFAULT_EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "relation"
DEFAULT_MODEL_NAME = "ethanyt/guwenbert-base"
SPECIAL_TOKENS = ["[HEAD]", "[/HEAD]", "[TAIL]", "[/TAIL]"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def load_dataset_dict(dataset_dir: Path) -> tuple[DatasetDict, list[str]]:
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    dataset = DatasetDict(
        {
            split: Dataset.from_list(load_jsonl(dataset_dir / f"{split}.jsonl"))
            for split in ["train", "validation", "test"]
        }
    )
    return dataset, manifest["label_list"]


def mark_entity_pair(text: str, head: dict[str, Any], tail: dict[str, Any]) -> str:
    head_start = int(head["start"])
    head_end = int(head["end"])
    tail_start = int(tail["start"])
    tail_end = int(tail["end"])
    if head_end <= head_start or tail_end <= tail_start:
        raise ValueError("Invalid entity span.")
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
    head_type = str(head.get("type") or "UNKNOWN")
    tail_type = str(tail.get("type") or "UNKNOWN")
    return f"{marked_text}\nHEAD_TYPE={head_type};TAIL_TYPE={tail_type}"


def tokenize_dataset(dataset: DatasetDict, tokenizer, label_to_id: dict[str, int]) -> DatasetDict:
    def tokenize_batch(examples):
        sequences = []
        for text, head, tail in zip(examples["text"], examples["head"], examples["tail"]):
            sequences.append(build_sequence_text(str(text), dict(head), dict(tail)))

        encoded = tokenizer(
            sequences,
            truncation=True,
            max_length=256,
        )
        encoded["labels"] = [label_to_id[str(label)] for label in examples["label"]]
        return encoded

    return dataset.map(tokenize_batch, batched=True, remove_columns=dataset["train"].column_names)


def compute_metrics_builder(label_list: list[str]):
    def compute_metrics(eval_prediction):
        predictions, labels = eval_prediction
        predicted_ids = predictions.argmax(axis=1)

        total = len(labels)
        accuracy = sum(int(pred == gold) for pred, gold in zip(predicted_ids, labels)) / total if total else 0.0

        f1_scores = []
        for label_id, _label_name in enumerate(label_list):
            true_positive = sum(1 for pred, gold in zip(predicted_ids, labels) if pred == label_id and gold == label_id)
            false_positive = sum(1 for pred, gold in zip(predicted_ids, labels) if pred == label_id and gold != label_id)
            false_negative = sum(1 for pred, gold in zip(predicted_ids, labels) if pred != label_id and gold == label_id)

            precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
            recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
            f1_scores.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))

        macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
        return {
            "accuracy": accuracy,
            "macro_f1": macro_f1,
        }

    return compute_metrics


def train_baseline(
    dataset_dir: Path,
    output_root: Path,
    experiment_root: Path,
    model_name: str,
    run_name: str,
    epochs: int,
    learning_rate: float,
    batch_size: int,
    activate: bool,
) -> dict[str, Any]:
    dataset, label_list = load_dataset_dict(dataset_dir)
    label_to_id = {label: index for index, label in enumerate(label_list)}

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.add_special_tokens({"additional_special_tokens": SPECIAL_TOKENS})
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(label_list),
        id2label={index: label for index, label in enumerate(label_list)},
        label2id=label_to_id,
    )
    model.resize_token_embeddings(len(tokenizer))

    tokenized_dataset = tokenize_dataset(dataset, tokenizer, label_to_id)

    output_dir = output_root / run_name
    experiment_dir = experiment_root / run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=learning_rate,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        num_train_epochs=epochs,
        weight_decay=0.01,
        logging_dir=str(experiment_dir / "logs"),
        logging_steps=20,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        report_to="none",
        save_total_limit=2,
        use_cpu=True,
        dataloader_pin_memory=False,
        optim="adamw_torch",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=compute_metrics_builder(label_list),
    )

    train_result = trainer.train()
    validation_metrics = trainer.evaluate(tokenized_dataset["validation"])
    test_metrics = trainer.evaluate(tokenized_dataset["test"], metric_key_prefix="test")
    best_dir = output_dir / "best"
    trainer.save_model(str(best_dir))
    tokenizer.save_pretrained(str(best_dir))

    summary = {
        "run_name": run_name,
        "task": "relation",
        "model_name": model_name,
        "dataset_dir": str(dataset_dir),
        "dataset_source": infer_dataset_source(dataset_dir),
        "label_list": label_list,
        "train_metrics": train_result.metrics,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "output_dir": str(best_dir),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    registry_record = register_model_run(summary=summary, task="relation", activate=activate)
    summary["registry_record"] = registry_record
    (experiment_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (best_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a transformer relation classification baseline on the prepared Shanghanlun dataset.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--experiment-root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--model-name", type=str, default=DEFAULT_MODEL_NAME)
    parser.add_argument("--run-name", type=str, default="guwenbert-relation-baseline")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    summary = train_baseline(
        dataset_dir=args.dataset_dir,
        output_root=args.output_root,
        experiment_root=args.experiment_root,
        model_name=args.model_name,
        run_name=args.run_name,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        activate=args.activate,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
