from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "annotation" / "preannotated_corpus.jsonl"
DEFAULT_CLEANED_OUTPUT = DATA_DIR / "annotation" / "cleaned_silver_corpus.jsonl"
DEFAULT_DROPPED_OUTPUT = DATA_DIR / "annotation" / "dropped_records.jsonl"
DEFAULT_REPORT_OUTPUT = DATA_DIR / "annotation" / "cleaning_report.md"
DEFAULT_ERROR_OUTPUT = DATA_DIR / "annotation" / "error_examples.md"
DEFAULT_DICTIONARY = DATA_DIR / "dictionary" / "entity_terms.json"

ALLOWED_ENTITY_TYPES = {
    "SYNDROME",
    "SYMPTOM",
    "FORMULA",
    "HERB",
    "THERAPY",
    "ADMINISTRATION",
}

ALLOWED_RELATION_TYPES = {
    "SYNDROME_HAS_SYMPTOM",
    "SYNDROME_TO_FORMULA",
    "FORMULA_CONTAINS_HERB",
    "FORMULA_HAS_ADMINISTRATION",
}

COMMENTARY_KEYWORDS = [
    "臣亿等谨按",
    "今以算法约之",
    "旧云",
    "本云",
    "收之得",
    "分之",
    "铢",
    "枚之",
    "算法",
    "合方",
]

THERAPY_BLACKLIST_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"下利",
        r"心下",
        r"胁下",
        r"身下",
        r"吐逆",
        r"干呕",
        r"汗出",
    ]
]

FORMULA_TRIGGER_PATTERNS = [
    re.compile(r"([一-龥]{2,24}(?:汤|散|丸))\s*方"),
    re.compile(r"([一-龥]{2,24}(?:汤|散|丸))主之"),
    re.compile(r"宜([一-龥]{2,24}(?:汤|散|丸))"),
    re.compile(r"(?:与|可与|当与|乃可与)([一-龥]{2,24}(?:汤|散|丸))"),
]

EXTRA_FORMULA_TERMS = {
    "甘草泻心汤",
    "柴胡桂枝汤",
    "桂枝加桂汤",
    "新加汤",
    "小柴胡汤",
    "五苓散",
    "十枣汤",
    "柴胡加龙骨牡蛎汤",
}

FORMULA_ENTRY_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"(?:汤|散|丸)方",
        r"右[一二三四五六七八九十百\d]+味",
        r"煮取",
        r"去滓",
        r"温服",
    ]
]

FORMULA_RELATION_TRIGGER_PATTERNS = [
    re.compile(pattern)
    for pattern in [r"主之", r"宜", r"可与", r"当与", r"乃可与", r"与.*(?:汤|散|丸)"]
]

SYNDROME_ANCHOR_PATTERNS = [
    re.compile(pattern)
    for pattern in [r"名为", r"名", r"此为", r"为", r"属"]
]

SENTENCE_DELIMITERS = "。；"
CLAUSE_DELIMITERS = "，。；："
NEGATION_DIRECT_PREFIXES = ("不", "未", "勿", "无", "非")
THERAPY_NEGATION_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"不可更?发汗",
        r"不可复?下",
        r"不可复?吐",
        r"勿发汗",
        r"勿吐",
        r"勿下",
        r"未发汗",
    ]
]


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_dictionary(path: Path) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def record_action(record: dict[str, object], action: str, payload: dict[str, object] | None = None) -> None:
    meta = record.setdefault("meta", {})
    cleaning = meta.setdefault("cleaning", [])
    item: dict[str, object] = {"action": action}
    if payload:
        item.update(payload)
    cleaning.append(item)


def reindex_entities(record: dict[str, object]) -> None:
    entities = sorted(record.get("entities", []), key=lambda entity: (int(entity["start"]), int(entity["end"]), str(entity["type"])))
    for idx, entity in enumerate(entities, start=1):
        entity["id"] = f"e{idx}"
    record["entities"] = entities


def slice_matches(text: str, entity: dict[str, object]) -> bool:
    start = int(entity["start"])
    end = int(entity["end"])
    return 0 <= start < end <= len(text) and text[start:end] == str(entity["text"])


def normalize_entities(record: dict[str, object], stats: Counter[str]) -> None:
    text = str(record["text"])
    normalized: list[dict[str, object]] = []
    seen = set()

    for entity in record.get("entities", []):
        entity_type = str(entity.get("type", ""))
        if entity_type not in ALLOWED_ENTITY_TYPES:
            stats["removed_disallowed_entity_type"] += 1
            record_action(record, "drop_entity", {"reason": "disallowed_entity_type", "entity": entity})
            continue

        try:
            entity = {
                "id": str(entity.get("id", "")),
                "type": entity_type,
                "text": str(entity.get("text", "")),
                "start": int(entity.get("start")),
                "end": int(entity.get("end")),
                "source": str(entity.get("source", "unknown")),
            }
        except (TypeError, ValueError):
            stats["removed_invalid_entity_structure"] += 1
            record_action(record, "drop_entity", {"reason": "invalid_entity_structure", "entity": entity})
            continue

        if not slice_matches(text, entity):
            stats["removed_invalid_entity_span"] += 1
            record_action(record, "drop_entity", {"reason": "invalid_entity_span", "entity": entity})
            continue

        dedupe_key = (entity["type"], entity["text"], entity["start"], entity["end"])
        if dedupe_key in seen:
            stats["removed_duplicate_entities"] += 1
            record_action(record, "drop_entity", {"reason": "duplicate_entity", "entity": entity})
            continue

        seen.add(dedupe_key)
        normalized.append(entity)

    record["entities"] = normalized
    reindex_entities(record)

def is_negated_entity(text: str, entity: dict[str, object]) -> bool:
    start = int(entity["start"])
    entity_text = str(entity["text"])
    prefix = text[max(0, start - 3):start]

    if entity["type"] == "SYMPTOM":
        if prefix.endswith("不可"):
            return True
        return any(prefix.endswith(token) for token in NEGATION_DIRECT_PREFIXES)

    if entity["type"] == "THERAPY":
        local = text[max(0, start - 4): min(len(text), int(entity["end"]) + 1)]
        for pattern in THERAPY_NEGATION_PATTERNS:
            if pattern.search(local) or pattern.search(text[max(0, start - 6): min(len(text), int(entity["end"]) + 2)]):
                return True
        if prefix.endswith("不可") or prefix.endswith("勿"):
            return True
        if any(local.startswith(token + entity_text) for token in NEGATION_DIRECT_PREFIXES):
            return True
    return False


def apply_negation_rules(record: dict[str, object], stats: Counter[str]) -> None:
    text = str(record["text"])
    kept: list[dict[str, object]] = []
    negated_entities: list[dict[str, object]] = []

    for entity in record.get("entities", []):
        if entity["type"] in {"SYMPTOM", "THERAPY"} and is_negated_entity(text, entity):
            negated_entities.append(entity)
            stats["negated_candidates_removed"] += 1
            stats[f"negated_{entity['type'].lower()}_removed"] += 1
            record_action(record, "drop_entity", {"reason": "negated_candidate", "entity": entity})
            continue
        kept.append(entity)

    if negated_entities:
        record.setdefault("meta", {}).setdefault("negated_candidates", []).extend(
            [{"type": entity["type"], "text": entity["text"], "start": entity["start"], "end": entity["end"]} for entity in negated_entities]
        )
    record["entities"] = kept
    reindex_entities(record)


def therapy_is_allowed(text: str, entity: dict[str, object]) -> bool:
    entity_text = str(entity["text"])
    start = int(entity["start"])
    end = int(entity["end"])
    context = text[max(0, start - 2): min(len(text), end + 3)]

    if entity_text in {"下", "吐", "汗", "刺"}:
        return False
    if entity_text in {"发汗", "汗法", "温针", "烧针", "解肌", "针足阳明"}:
        return True
    for pattern in THERAPY_BLACKLIST_PATTERNS:
        if pattern.search(context):
            return False
    return len(entity_text) >= 2


def fix_therapy_false_positives(record: dict[str, object], stats: Counter[str]) -> None:
    text = str(record["text"])
    kept: list[dict[str, object]] = []
    for entity in record.get("entities", []):
        if entity["type"] != "THERAPY":
            kept.append(entity)
            continue
        if not therapy_is_allowed(text, entity):
            stats["removed_false_positive_therapy"] += 1
            record_action(record, "drop_entity", {"reason": "therapy_false_positive", "entity": entity})
            continue
        kept.append(entity)
    record["entities"] = kept
    reindex_entities(record)


def detect_formula_candidates(text: str, existing_formulas: Iterable[str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen = set()

    def add_candidate(formula_text: str, start: int, end: int, source: str) -> None:
        key = (formula_text, start, end)
        if key in seen:
            return
        if not (0 <= start < end <= len(text)):
            return
        if text[start:end] != formula_text:
            return
        seen.add(key)
        candidates.append(
            {
                "id": "",
                "type": "FORMULA",
                "text": formula_text,
                "start": start,
                "end": end,
                "source": source,
            }
        )

    for formula_text in sorted(set(existing_formulas) | EXTRA_FORMULA_TERMS, key=lambda value: (-len(value), value)):
        start = 0
        while True:
            index = text.find(formula_text, start)
            if index == -1:
                break
            add_candidate(formula_text, index, index + len(formula_text), "formula_priority")
            start = index + 1

    for pattern in FORMULA_TRIGGER_PATTERNS:
        for match in pattern.finditer(text):
            formula_text = match.group(1)
            add_candidate(formula_text, match.start(1), match.end(1), "formula_trigger")

    selected: list[dict[str, object]] = []
    for candidate in sorted(candidates, key=lambda item: (int(item["start"]), -(int(item["end"]) - int(item["start"])) )):
        overlap = False
        for chosen in list(selected):
            if not (int(candidate["end"]) <= int(chosen["start"]) or int(candidate["start"]) >= int(chosen["end"])):
                if (int(candidate["end"]) - int(candidate["start"])) > (int(chosen["end"]) - int(chosen["start"])):
                    selected.remove(chosen)
                    overlap = False
                    break
                overlap = True
        if not overlap:
            selected.append(candidate)
    return sorted(selected, key=lambda item: (int(item["start"]), int(item["end"])))


def prioritize_formula_over_herb(record: dict[str, object], stats: Counter[str], known_formula_terms: set[str]) -> None:
    text = str(record["text"])
    original_formulas = [entity for entity in record.get("entities", []) if entity["type"] == "FORMULA"]
    formula_candidates = detect_formula_candidates(text, known_formula_terms | {entity["text"] for entity in original_formulas})
    existing_formula_keys = {(entity["text"], int(entity["start"]), int(entity["end"])) for entity in original_formulas}

    kept_entities: list[dict[str, object]] = []
    for entity in record.get("entities", []):
        if entity["type"] == "FORMULA":
            continue
        if entity["type"] == "HERB":
            covered = False
            for formula in formula_candidates:
                if int(formula["start"]) <= int(entity["start"]) and int(entity["end"]) <= int(formula["end"]):
                    covered = True
                    break
            if covered:
                stats["removed_herb_covered_by_formula"] += 1
                record_action(record, "drop_entity", {"reason": "formula_over_herb", "entity": entity})
                continue
        kept_entities.append(entity)

    for formula in formula_candidates:
        if (formula["text"], int(formula["start"]), int(formula["end"])) not in existing_formula_keys:
            stats["new_formula_entities_added"] += 1
            record_action(record, "add_entity", {"reason": "formula_trigger_detection", "entity": formula})
        kept_entities.append(formula)

    record["entities"] = kept_entities
    reindex_entities(record)


def formula_variant_parser(formula_text: str, herb_terms: set[str]) -> dict[str, list[str]]:
    removed: list[str] = []
    added: list[str] = []
    herb_order = sorted(herb_terms, key=lambda item: (-len(item), item))

    def extract(segment: str) -> list[str]:
        hits: list[str] = []
        for herb in herb_order:
            if herb in segment and herb not in hits:
                hits.append(herb)
        return hits

    if "去" in formula_text:
        after_qu = formula_text.split("去", 1)[1]
        removed_segment = after_qu.split("加", 1)[0].split("汤", 1)[0].split("散", 1)[0].split("丸", 1)[0]
        removed.extend(extract(removed_segment))
    if "加" in formula_text:
        additions = formula_text.split("加")[1:]
        for addition in additions:
            addition_segment = addition.split("去", 1)[0].split("汤", 1)[0].split("散", 1)[0].split("丸", 1)[0]
            added.extend([herb for herb in extract(addition_segment) if herb not in added])
    return {"removed_herbs": removed, "added_herbs": added}


def filter_annotation_commentary_records(record: dict[str, object], stats: Counter[str], raw_relation_count: int) -> list[str]:
    text = str(record["text"])
    reasons: list[str] = []
    matched_keywords = [keyword for keyword in COMMENTARY_KEYWORDS if keyword in text]
    if matched_keywords:
        stats["filtered_commentary_records"] += 1
        reasons.append("commentary_keywords:" + ",".join(matched_keywords))
    if len(text) > 180 and raw_relation_count > 30:
        stats["filtered_long_formula_records"] += 1
        reasons.append("long_formula_conversion_record")
    return reasons


def classify_entry(text: str) -> str:
    if any(pattern.search(text) for pattern in FORMULA_ENTRY_PATTERNS):
        return "formula_entry"
    return "syndrome_entry"

def split_spans(text: str, delimiters: str) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    start = 0
    for idx, char in enumerate(text):
        if char in delimiters:
            end = idx + 1
            segment_text = text[start:end]
            if segment_text.strip():
                spans.append({"start": start, "end": end, "text": segment_text})
            start = end
    if start < len(text):
        segment_text = text[start:]
        if segment_text.strip():
            spans.append({"start": start, "end": len(text), "text": segment_text})
    return spans


def entity_in_span(entity: dict[str, object], span: dict[str, object]) -> bool:
    return int(span["start"]) <= int(entity["start"]) < int(span["end"])


def choose_nearest_anchor(entity: dict[str, object], candidates: list[dict[str, object]], clause_index_map: dict[str, int]) -> dict[str, object] | None:
    if not candidates:
        return None
    entity_clause = clause_index_map.get(str(entity["id"]), 0)
    return min(
        candidates,
        key=lambda candidate: (
            abs(clause_index_map.get(str(candidate["id"]), 0) - entity_clause),
            0 if int(candidate["start"]) <= int(entity["start"]) else 1,
            int(candidate["start"]),
        ),
    )


def clause_has_formula_trigger(clause_text: str) -> bool:
    return any(pattern.search(clause_text) for pattern in FORMULA_RELATION_TRIGGER_PATTERNS)


def build_formula_entry_relations(record: dict[str, object], herb_terms: set[str], stats: Counter[str]) -> list[dict[str, object]]:
    text = str(record["text"])
    entities = list(record.get("entities", []))
    formulas = [entity for entity in entities if entity["type"] == "FORMULA"]
    if not formulas:
        return []

    commentary_start = len(text)
    for keyword in COMMENTARY_KEYWORDS:
        index = text.find(keyword)
        if index != -1:
            commentary_start = min(commentary_start, index)

    main_formula = min((formula for formula in formulas if int(formula["start"]) < commentary_start), key=lambda entity: int(entity["start"]), default=formulas[0])
    explicit_scope_start = int(main_formula["end"])
    explicit_scope_end = commentary_start

    herbs = [entity for entity in entities if entity["type"] == "HERB" and explicit_scope_start <= int(entity["start"]) < explicit_scope_end]
    administrations = [entity for entity in entities if entity["type"] == "ADMINISTRATION" and explicit_scope_start <= int(entity["start"]) < explicit_scope_end]
    has_explicit_herb_list = ("右" in text and "味" in text) or len(herbs) >= 2

    variant_info = formula_variant_parser(str(main_formula["text"]), herb_terms)
    if variant_info["removed_herbs"] or variant_info["added_herbs"]:
        record_action(record, "formula_variant_detected", {"formula": main_formula["text"], "removed_herbs": variant_info["removed_herbs"], "added_herbs": variant_info["added_herbs"]})
        stats["formula_variant_detected"] += 1

    relations: list[dict[str, object]] = []
    if has_explicit_herb_list:
        for herb in herbs:
            relations.append({"type": "FORMULA_CONTAINS_HERB", "head": str(main_formula["id"]), "tail": str(herb["id"]), "source": "clean_rule"})
    else:
        stats["formula_relations_skipped_without_explicit_herb_list"] += 1

    for administration in administrations:
        relations.append({"type": "FORMULA_HAS_ADMINISTRATION", "head": str(main_formula["id"]), "tail": str(administration["id"]), "source": "clean_rule"})

    return relations


def build_syndrome_entry_relations(record: dict[str, object], stats: Counter[str]) -> list[dict[str, object]]:
    text = str(record["text"])
    entities = list(record.get("entities", []))
    relations: list[dict[str, object]] = []
    sentences = split_spans(text, SENTENCE_DELIMITERS)
    if not sentences:
        sentences = [{"start": 0, "end": len(text), "text": text}]

    for sentence in sentences:
        sentence_entities = [entity for entity in entities if entity_in_span(entity, sentence)]
        clauses = split_spans(str(sentence["text"]), CLAUSE_DELIMITERS)
        if not clauses:
            clauses = [{"start": 0, "end": len(sentence["text"]), "text": str(sentence["text"])}]
        adjusted_clauses = [
            {"start": int(sentence["start"]) + int(clause["start"]), "end": int(sentence["start"]) + int(clause["end"]), "text": str(clause["text"])}
            for clause in clauses
        ]
        clause_index_map: dict[str, int] = {}
        for clause_index, clause in enumerate(adjusted_clauses):
            for entity in sentence_entities:
                if entity_in_span(entity, clause):
                    clause_index_map[str(entity["id"])] = clause_index

        sentence_syndromes = [entity for entity in sentence_entities if entity["type"] == "SYNDROME"]
        sentence_symptoms = [entity for entity in sentence_entities if entity["type"] == "SYMPTOM"]
        sentence_formulas = [entity for entity in sentence_entities if entity["type"] == "FORMULA"]

        strong_syndromes: list[dict[str, object]] = []
        for syndrome in sentence_syndromes:
            clause = adjusted_clauses[clause_index_map.get(str(syndrome["id"]), 0)]
            local_start = int(syndrome["start"]) - int(clause["start"])
            prefix = str(clause["text"])[:local_start]
            if any(pattern.search(prefix) for pattern in SYNDROME_ANCHOR_PATTERNS):
                strong_syndromes.append(syndrome)

        candidate_syndromes = strong_syndromes or sentence_syndromes
        for symptom in sentence_symptoms:
            syndrome = choose_nearest_anchor(symptom, candidate_syndromes, clause_index_map)
            if syndrome is None:
                continue
            relations.append({"type": "SYNDROME_HAS_SYMPTOM", "head": str(syndrome["id"]), "tail": str(symptom["id"]), "source": "clean_rule"})

        for formula in sentence_formulas:
            clause = adjusted_clauses[clause_index_map.get(str(formula["id"]), 0)]
            if not clause_has_formula_trigger(str(clause["text"])):
                continue
            preceding_syndromes = [syndrome for syndrome in candidate_syndromes if int(syndrome["start"]) <= int(formula["start"])]
            syndrome = choose_nearest_anchor(formula, preceding_syndromes or candidate_syndromes, clause_index_map)
            if syndrome is None:
                continue
            relations.append({"type": "SYNDROME_TO_FORMULA", "head": str(syndrome["id"]), "tail": str(formula["id"]), "source": "clean_rule"})

    return relations


def normalize_relations(record: dict[str, object], stats: Counter[str], herb_terms: set[str]) -> None:
    original_relations = list(record.get("relations", []))
    entry_type = classify_entry(str(record["text"]))
    record.setdefault("meta", {})["entry_type"] = entry_type
    stats[f"entry_type_{entry_type}"] += 1

    disallowed_original_relations = [relation for relation in original_relations if str(relation.get("type", "")) not in ALLOWED_RELATION_TYPES]
    stats["removed_disallowed_relation_type"] += len(disallowed_original_relations)
    if disallowed_original_relations:
        record_action(record, "drop_relations", {"reason": "disallowed_relation_types", "count": len(disallowed_original_relations)})

    if entry_type == "formula_entry":
        cleaned_relations = build_formula_entry_relations(record, herb_terms, stats)
    else:
        cleaned_relations = build_syndrome_entry_relations(record, stats)

    stats["original_relations_replaced"] += len(original_relations)
    stats["relations_regenerated"] += len(cleaned_relations)
    record["relations"] = cleaned_relations


def deduplicate_relations(record: dict[str, object], stats: Counter[str]) -> None:
    entity_map = {str(entity["id"]): (str(entity["type"]), str(entity["text"])) for entity in record.get("entities", [])}
    deduped: list[dict[str, object]] = []
    seen = set()
    for relation in record.get("relations", []):
        head_id = str(relation.get("head", ""))
        tail_id = str(relation.get("tail", ""))
        if head_id not in entity_map or tail_id not in entity_map:
            stats["removed_relations_missing_entity"] += 1
            continue
        head_type, head_text = entity_map[head_id]
        tail_type, tail_text = entity_map[tail_id]
        relation_type = str(relation.get("type", ""))
        canonical_key = (head_type, head_text, relation_type, tail_type, tail_text)
        if canonical_key in seen:
            stats["deduplicated_relations"] += 1
            continue
        seen.add(canonical_key)
        deduped.append({"type": relation_type, "head": head_id, "tail": tail_id, "source": str(relation.get("source", "clean_rule"))})
    record["relations"] = deduped


def validate_record(record: dict[str, object], stats: Counter[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    required_keys = {"id", "text", "entities", "relations", "meta"}
    missing = sorted(required_keys - set(record.keys()))
    if missing:
        reasons.append("missing_keys:" + ",".join(missing))

    text = str(record.get("text", ""))
    entity_ids: set[str] = set()
    for entity in record.get("entities", []):
        if entity["type"] not in ALLOWED_ENTITY_TYPES:
            reasons.append("invalid_entity_type")
            break
        if not slice_matches(text, entity):
            reasons.append("entity_span_mismatch")
            break
        entity_ids.add(str(entity["id"]))

    for relation in record.get("relations", []):
        if str(relation.get("type", "")) not in ALLOWED_RELATION_TYPES:
            reasons.append("invalid_relation_type")
            break
        if str(relation.get("head", "")) == str(relation.get("tail", "")):
            reasons.append("self_loop_relation")
            break
        if str(relation.get("head", "")) not in entity_ids or str(relation.get("tail", "")) not in entity_ids:
            reasons.append("relation_missing_entity")
            break

    if not record.get("entities"):
        reasons.append("no_valid_entities_after_cleaning")

    entry_type = str(record.get("meta", {}).get("entry_type", ""))
    if entry_type == "formula_entry" and not any(entity["type"] == "FORMULA" for entity in record.get("entities", [])):
        reasons.append("formula_entry_without_formula")
    if entry_type == "syndrome_entry" and not any(entity["type"] in {"SYNDROME", "FORMULA", "SYMPTOM"} for entity in record.get("entities", [])):
        reasons.append("syndrome_entry_without_core_entities")

    if reasons:
        stats["records_failed_validation"] += 1
    return (len(reasons) == 0, reasons)


def summarize_entities(record: dict[str, object]) -> list[dict[str, object]]:
    return [{"type": entity["type"], "text": entity["text"], "start": entity["start"], "end": entity["end"]} for entity in record.get("entities", [])]


def summarize_relations(record: dict[str, object]) -> list[dict[str, object]]:
    entity_map = {str(entity["id"]): entity for entity in record.get("entities", [])}
    items: list[dict[str, object]] = []
    for relation in record.get("relations", []):
        head = entity_map.get(str(relation["head"]), {})
        tail = entity_map.get(str(relation["tail"]), {})
        items.append({"type": relation["type"], "head": {"type": head.get("type"), "text": head.get("text")}, "tail": {"type": tail.get("type"), "text": tail.get("text")}})
    return items

def build_error_examples(examples: list[dict[str, object]], output_path: Path) -> None:
    lines = ["# Error Examples", "", f"共展示 {len(examples)} 条代表性修复案例。", ""]
    for index, example in enumerate(examples, start=1):
        lines.extend(
            [
                f"## Example {index}: {example['id']}",
                "",
                f"- 状态: {example['status']}",
                f"- 原因: {', '.join(example['reasons']) if example['reasons'] else 'cleaned'}",
                f"- 文本: {example['text']}",
                "",
                "### 原始实体",
                "```json",
                json.dumps(example['before_entities'], ensure_ascii=False, indent=2),
                "```",
                "",
                "### 原始关系",
                "```json",
                json.dumps(example['before_relations'], ensure_ascii=False, indent=2),
                "```",
                "",
                "### 清洗后实体",
                "```json",
                json.dumps(example['after_entities'], ensure_ascii=False, indent=2),
                "```",
                "",
                "### 清洗后关系",
                "```json",
                json.dumps(example['after_relations'], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def build_cleaning_report(
    stats: Counter[str],
    raw_count: int,
    kept_count: int,
    dropped_count: int,
    raw_entity_total: int,
    cleaned_entity_total: int,
    raw_relation_total: int,
    cleaned_relation_total: int,
    output_path: Path,
) -> None:
    entity_deletion_total = max(0, raw_entity_total + stats["new_formula_entities_added"] - cleaned_entity_total)
    relation_deletion_total = max(0, raw_relation_total - cleaned_relation_total)
    lines = [
        "# Cleaning Report",
        "",
        "## Summary",
        "",
        f"- ?????: {raw_count}",
        f"- ?????: {kept_count}",
        f"- ?????: {dropped_count}",
        f"- ??????: {raw_entity_total}",
        f"- ???????: {cleaned_entity_total}",
        f"- ??????: {raw_relation_total}",
        f"- ???????: {cleaned_relation_total}",
        "",
        "## Core Fix Stats",
        "",
        f"- ???????: {stats['negated_candidates_removed']}",
        f"- ????????: {stats['removed_false_positive_therapy']}",
        f"- ?????????????: {stats['removed_herb_covered_by_formula']}",
        f"- ?????????: {stats['new_formula_entities_added']}",
        f"- ???????: {stats['deduplicated_relations']}",
        f"- ?????????: {stats['removed_disallowed_relation_type']}",
        f"- ??????: {entity_deletion_total}",
        f"- ??????: {relation_deletion_total}",
        f"- ??????/?????: {stats['filtered_commentary_records']}",
        f"- ???????????: {stats['filtered_long_formula_records']}",
        "",
        "## Additional Stats",
        "",
    ]

    skip_keys = {
        'negated_candidates_removed', 'removed_false_positive_therapy', 'removed_herb_covered_by_formula',
        'new_formula_entities_added', 'deduplicated_relations', 'removed_disallowed_relation_type',
        'filtered_commentary_records', 'filtered_long_formula_records', 'original_relations_replaced',
        'relations_regenerated', 'removed_relations_missing_entity', 'removed_disallowed_entity_type',
        'removed_invalid_entity_structure', 'removed_invalid_entity_span', 'removed_duplicate_entities'
    }
    for key in sorted(stats):
        if key in skip_keys:
            continue
        lines.append(f"- {key}: {stats[key]}")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean preannotated Shanghanlun silver corpus.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cleaned-output", type=Path, default=DEFAULT_CLEANED_OUTPUT)
    parser.add_argument("--dropped-output", type=Path, default=DEFAULT_DROPPED_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    parser.add_argument("--error-output", type=Path, default=DEFAULT_ERROR_OUTPUT)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    args = parser.parse_args()

    dictionary = load_dictionary(args.dictionary)
    known_formula_terms = set(dictionary.get("FORMULA", []))
    herb_terms = set(dictionary.get("HERB", []))
    records = load_jsonl(args.input)

    stats: Counter[str] = Counter()
    cleaned_records: list[dict[str, object]] = []
    dropped_records: list[dict[str, object]] = []
    examples: list[dict[str, object]] = []
    raw_entity_total = sum(len(record.get("entities", [])) for record in records)
    raw_relation_total = sum(len(record.get("relations", [])) for record in records)

    for record in records:
        original = copy.deepcopy(record)
        raw_relation_count = len(record.get("relations", []))
        working = copy.deepcopy(record)
        working.setdefault("meta", {})

        normalize_entities(working, stats)
        apply_negation_rules(working, stats)
        fix_therapy_false_positives(working, stats)
        prioritize_formula_over_herb(working, stats, known_formula_terms)

        drop_reasons = filter_annotation_commentary_records(working, stats, raw_relation_count)
        if drop_reasons:
            dropped_records.append({"id": working["id"], "text": working["text"], "drop_reasons": drop_reasons, "meta": working.get("meta", {})})
            examples.append({
                "id": str(working["id"]),
                "text": str(working["text"]),
                "status": "dropped",
                "reasons": drop_reasons,
                "before_entities": summarize_entities(original),
                "before_relations": summarize_relations(original),
                "after_entities": summarize_entities(working),
                "after_relations": summarize_relations(working),
            })
            continue

        normalize_relations(working, stats, herb_terms)
        deduplicate_relations(working, stats)

        is_valid, validation_reasons = validate_record(working, stats)
        if not is_valid:
            dropped_records.append({"id": working["id"], "text": working["text"], "drop_reasons": validation_reasons, "meta": working.get("meta", {})})
            examples.append({
                "id": str(working["id"]),
                "text": str(working["text"]),
                "status": "dropped",
                "reasons": validation_reasons,
                "before_entities": summarize_entities(original),
                "before_relations": summarize_relations(original),
                "after_entities": summarize_entities(working),
                "after_relations": summarize_relations(working),
            })
            continue

        cleaned_records.append(working)
        if summarize_entities(original) != summarize_entities(working) or summarize_relations(original) != summarize_relations(working):
            examples.append({
                "id": str(working["id"]),
                "text": str(working["text"]),
                "status": "cleaned",
                "reasons": [item.get("action", "cleaned") for item in working.get("meta", {}).get("cleaning", [])],
                "before_entities": summarize_entities(original),
                "before_relations": summarize_relations(original),
                "after_entities": summarize_entities(working),
                "after_relations": summarize_relations(working),
            })

    examples.sort(key=lambda item: (0 if item["status"] == "dropped" else 1, -(len(item["before_relations"]) - len(item["after_relations"]) + len(item["before_entities"]) - len(item["after_entities"])), item["id"]))
    representative_examples = examples[:20]

    cleaned_entity_total = sum(len(record.get("entities", [])) for record in cleaned_records)
    cleaned_relation_total = sum(len(record.get("relations", [])) for record in cleaned_records)

    write_jsonl(args.cleaned_output, cleaned_records)
    write_jsonl(args.dropped_output, dropped_records)
    build_cleaning_report(
        stats,
        len(records),
        len(cleaned_records),
        len(dropped_records),
        raw_entity_total,
        cleaned_entity_total,
        raw_relation_total,
        cleaned_relation_total,
        args.report_output,
    )
    build_error_examples(representative_examples, args.error_output)

    print(f"wrote {len(cleaned_records)} cleaned records to {args.cleaned_output}")
    print(f"wrote {len(dropped_records)} dropped records to {args.dropped_output}")
    print(f"wrote report to {args.report_output}")
    print(f"wrote error examples to {args.error_output}")


if __name__ == "__main__":
    main()