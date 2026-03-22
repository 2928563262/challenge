from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict
from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATASET_DIR = DATA_DIR / "processed" / "ner"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "models" / "baseline" / "ner"
DEFAULT_EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "ner"
DEFAULT_MODEL_NAME = "ethanyt/guwenbert-base"


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


def build_tokenize_function(tokenizer, label_to_id: dict[str, int], label_all_tokens: bool = True):
    def tokenize_and_align_labels(examples):
        tokenized_inputs = tokenizer(
            examples["tokens"],
            truncation=True,
            is_split_into_words=True,
            max_length=256,
        )

        aligned_labels = []
        for batch_index, labels in enumerate(examples["tags"]):
            word_ids = tokenized_inputs.word_ids(batch_index=batch_index)
            previous_word_id = None
            label_ids = []
            for word_id in word_ids:
                if word_id is None:
                    label_ids.append(-100)
                    continue

                label = labels[word_id]
                if word_id != previous_word_id:
                    label_ids.append(label_to_id[label])
                elif label_all_tokens:
                    inside_label = f"I-{label[2:]}" if label.startswith("B-") else label
                    label_ids.append(label_to_id.get(inside_label, label_to_id[label]))
                else:
                    label_ids.append(-100)
                previous_word_id = word_id

            aligned_labels.append(label_ids)

        tokenized_inputs["labels"] = aligned_labels
        return tokenized_inputs

    return tokenize_and_align_labels


def build_compute_metrics(label_list: list[str]):
    def compute_metrics(eval_prediction):
        predictions, labels = eval_prediction
        predicted_ids = predictions.argmax(axis=2)

        true_predictions = []
        true_labels = []
        for prediction_row, label_row in zip(predicted_ids, labels):
            row_predictions = []
            row_labels = []
            for predicted_id, label_id in zip(prediction_row, label_row):
                if label_id == -100:
                    continue
                row_predictions.append(label_list[predicted_id])
                row_labels.append(label_list[label_id])
            true_predictions.append(row_predictions)
            true_labels.append(row_labels)

        return {
            "precision": precision_score(true_labels, true_predictions),
            "recall": recall_score(true_labels, true_predictions),
            "f1": f1_score(true_labels, true_predictions),
            "accuracy": accuracy_score(true_labels, true_predictions),
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
) -> dict[str, Any]:
    dataset, label_list = load_dataset_dict(dataset_dir)
    label_to_id = {label: index for index, label in enumerate(label_list)}

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(label_list),
        id2label={index: label for index, label in enumerate(label_list)},
        label2id=label_to_id,
    )

    tokenized_dataset = dataset.map(
        build_tokenize_function(tokenizer, label_to_id),
        batched=True,
        remove_columns=dataset["train"].column_names,
    )

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
        metric_for_best_model="f1",
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
        data_collator=DataCollatorForTokenClassification(tokenizer=tokenizer),
        compute_metrics=build_compute_metrics(label_list),
    )

    train_result = trainer.train()
    validation_metrics = trainer.evaluate(tokenized_dataset["validation"])
    test_metrics = trainer.evaluate(tokenized_dataset["test"], metric_key_prefix="test")
    trainer.save_model(str(output_dir / "best"))
    tokenizer.save_pretrained(str(output_dir / "best"))

    summary = {
        "run_name": run_name,
        "model_name": model_name,
        "dataset_dir": str(dataset_dir),
        "label_list": label_list,
        "train_metrics": train_result.metrics,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "output_dir": str(output_dir / "best"),
    }
    (experiment_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a transformer NER baseline on the prepared Shanghanlun dataset.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--experiment-root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--model-name", type=str, default=DEFAULT_MODEL_NAME)
    parser.add_argument("--run-name", type=str, default="guwenbert-ner-baseline")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--batch-size", type=int, default=8)
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
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
