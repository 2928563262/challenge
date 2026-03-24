from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.conf import settings

# GLM API 配置
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_API_BASE = os.getenv("GLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4-flash")

# 保留原有路径用于兼容，但不再依赖本地模型
DEFAULT_NER_MODEL_DIR = settings.PROJECT_ROOT / "models" / "baseline" / "ner" / "guwenbert-ner-baseline" / "best"
DEFAULT_RELATION_MODEL_DIR = settings.PROJECT_ROOT / "models" / "baseline" / "relation" / "guwenbert-relation-baseline" / "best"
RUNTIME_DEPENDENCIES = ["openai"]
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


def _get_glm_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelUnavailableError("OpenAI client not installed") from exc

    if not GLM_API_KEY:
        raise ModelUnavailableError("GLM_API_KEY environment variable not set")

    return OpenAI(api_key=GLM_API_KEY, base_url=GLM_API_BASE)


def _call_glm(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    client = _get_glm_client()
    try:
        response = client.chat.completions.create(
            model=GLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        raise ModelUnavailableError(f"GLM API error: {exc}") from exc


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def _compatible_relation_labels(head_type: str, tail_type: str) -> list[str]:
    """返回允许的关系类型列表"""
    allowed = RELATION_TYPE_COMPATIBILITY.get((head_type, tail_type))
    if allowed is None:
        return ["NO_RELATION"]
    return allowed


def _has_formula_trigger(text: str, formula_text: str) -> bool:
    normalized_formula = formula_text.strip()
    if not normalized_formula:
        return False
    candidates = [f"{normalized_formula}{FORMULA_TRIGGER_SUFFIX}", *[f"{prefix}{normalized_formula}" for prefix in FORMULA_TRIGGER_PREFIXES]]
    return any(candidate in text for candidate in candidates)


def _constrain_relation_prediction_simple(head_type: str, tail_type: str, label: str) -> str:
    """根据实体类型对关系标签进行约束（适用于API输出）"""
    allowed = _compatible_relation_labels(head_type, tail_type)
    if label in allowed:
        return label
    # 如果预测的标签不在允许列表中，返回 NO_RELATION
    return "NO_RELATION"


def _apply_relation_heuristics(
    text: str,
    head: dict[str, Any],
    tail: dict[str, Any],
    label: str,
    confidence: float,
) -> tuple[str, float, dict[str, Any]]:
    """应用启发式规则（仅处理 formula_trigger）"""
    override = False
    reason = None

    if (
        head.get("type") == "SYNDROME"
        and tail.get("type") == "FORMULA"
        and "SYNDROME_TO_FORMULA" in _compatible_relation_labels(head["type"], tail["type"])
        and _has_formula_trigger(text, str(tail.get("text") or ""))
    ):
        label = "SYNDROME_TO_FORMULA"
        confidence = max(confidence, 0.8)  # 提信
        override = True
        reason = "formula_trigger"

    return label, confidence, {"heuristic_override": override, "heuristic_reason": reason}


def get_ner_status() -> dict[str, Any]:
    """获取 NER 服务状态（使用 GLM API）"""
    missing_dependencies = _missing_dependencies(RUNTIME_DEPENDENCIES)
    api_configured = bool(GLM_API_KEY)

    return {
        "ready": api_configured and not missing_dependencies,
        "base_model_name": GLM_MODEL,
        "model_type": "glm_api",
        "checkpoint_exists": api_configured,
        "dataset_manifest_exists": None,
        "dataset_manifest_path": None,
        "missing_dependencies": missing_dependencies,
        "required_dependencies": RUNTIME_DEPENDENCIES,
        "label_list": [
            "SYMPTOM", "SYNDROME", "FORMULA", "HERB", "THERAPY", "ADMINISTRATION"
        ],
        "dataset_summary": None,
        "commands": {},
    }


def get_relation_status() -> dict[str, Any]:
    """获取关系抽取服务状态（使用 GLM API）"""
    missing_dependencies = _missing_dependencies(RUNTIME_DEPENDENCIES)
    api_configured = bool(GLM_API_KEY)

    return {
        "ready": api_configured and not missing_dependencies,
        "base_model_name": GLM_MODEL,
        "model_type": "glm_api",
        "checkpoint_exists": api_configured,
        "dataset_manifest_exists": None,
        "dataset_manifest_path": None,
        "missing_dependencies": missing_dependencies,
        "required_dependencies": RUNTIME_DEPENDENCIES,
        "label_list": [
            "SYNDROME_HAS_SYMPTOM",
            "SYNDROME_TO_FORMULA",
            "FORMULA_CONTAINS_HERB",
            "FORMULA_HAS_ADMINISTRATION",
            "NO_RELATION",
        ],
        "dataset_summary": None,
        "commands": {},
    }


def get_model_summary() -> dict[str, Any]:
    return {
        "ner": get_ner_status(),
        "relation": get_relation_status(),
    }


def predict_ner(text: str) -> dict[str, Any]:
    """使用 GLM-4-flash API 进行命名实体识别"""
    if not GLM_API_KEY:
        raise ModelUnavailableError("GLM_API_KEY environment variable not set")

    system_prompt = """你是一个中医文本命名实体识别专家。从《伤寒论》条文中抽取以下实体：
- SYMPTOM: 症状与体征（如发热、头痛、汗出）
- SYNDROME: 证候或病机（如太阳病、中风）
- FORMULA: 方剂名（如桂枝汤、白虎加人参汤）
- HERB: 中药名（如桂枝、芍药、甘草）
- THERAPY: 治法（如发汗、下、温针）
- ADMINISTRATION: 煎服法（如温服一升、日三服）

输出格式为 JSON：
{
  "entities": [
    {"type": "ENTITY_TYPE", "text": "实体文本", "start": 起始位置, "end": 结束位置}
  ]
}

注意：start 和 end 是字符级别的位置索引（从0开始）。"""

    user_prompt = f"请从以下条文中抽取实体：\n\n{text}"

    try:
        result_text = _call_glm(system_prompt, user_prompt)
        result = json.loads(result_text)
        entities = result.get("entities", [])
    except json.JSONDecodeError:
        # 尝试从回复中提取 JSON 部分
        import re
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            entities = result.get("entities", [])
        else:
            entities = []

    # 构建标签序列（用于向后兼容）
    tokens = list(text)
    labels = ["O"] * len(tokens)
    for entity in entities:
        start = int(entity.get("start", 0))
        end = int(entity.get("end", 0))
        etype = entity.get("type", "UNKNOWN")
        if 0 <= start < end <= len(tokens):
            labels[start] = f"B-{etype}"
            for i in range(start + 1, end):
                if i < len(labels):
                    labels[i] = f"I-{etype}"

    return {
        "text": text,
        "tokens": tokens,
        "labels": labels,
        "entities": entities,
    }


def predict_relation(text: str, head: dict[str, Any], tail: dict[str, Any]) -> dict[str, Any]:
    """使用 GLM-4-flash API 进行关系抽取"""
    if not GLM_API_KEY:
        raise ModelUnavailableError("GLM_API_KEY environment variable not set")

    resolved_head = _resolve_entity_payload(text, head, "head")
    resolved_tail = _resolve_entity_payload(text, tail, "tail")

    system_prompt = """你是一个中医文本关系抽取专家。根据《伤寒论》条文内容，判断头实体和尾实体之间的关系类型。

可选的实体类型：
- SYMPTOM: 症状
- SYNDROME: 证候
- FORMULA: 方剂
- HERB: 中药
- THERAPY: 治法
- ADMINISTRATION: 煎服法

关系类型：
- SYNDROME_HAS_SYMPTOM: 证候具有症状
- SYNDROME_TO_FORMULA: 证候对应方剂
- FORMULA_CONTAINS_HERB: 方剂包含中药
- FORMULA_HAS_ADMINISTRATION: 方剂具有煎服法
- NO_RELATION: 无稳定关系

请根据条文语义判断，输出 JSON：
{
  "label": "关系类型",
  "confidence": 置信度(0-1之间的小数)
}"""

    user_prompt = f"""条文：{text}

头实体：{resolved_head['text']} (类型: {resolved_head['type']})
尾实体：{resolved_tail['text']} (类型: {resolved_tail['type']})

请判断两者之间的关系。"""

    try:
        result_text = _call_glm(system_prompt, user_prompt)
        result = json.loads(result_text)
        label = result.get("label", "NO_RELATION")
        confidence = float(result.get("confidence", 0.5))
    except (json.JSONDecodeError, ValueError, KeyError):
        label = "NO_RELATION"
        confidence = 0.0

    # 应用类型约束
    constrained_label = _constrain_relation_prediction_simple(
        head_type=resolved_head["type"],
        tail_type=resolved_tail["type"],
        label=label,
    )

    # 应用启发式规则
    final_label, final_confidence, heuristic_meta = _apply_relation_heuristics(
        text=text,
        head=resolved_head,
        tail=resolved_tail,
        label=constrained_label,
        confidence=confidence,
    )

    return {
        "text": text,
        "head": resolved_head,
        "tail": resolved_tail,
        "label": final_label,
        "confidence": final_confidence,
        "heuristic_override": heuristic_meta["heuristic_override"],
        "heuristic_reason": heuristic_meta["heuristic_reason"],
        "top_predictions": [{"label": final_label, "score": final_confidence}],
    }
