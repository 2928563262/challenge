from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from graph.services import GraphDataUnavailableError, get_entity_detail, load_graph_data, search_entities
from modeling.services import predict_ner


class AskQuestionView(APIView):
    """
    基于图谱的问答接口（当前为模板化回答）。

    流程：
    1. 尝试 NER 识别问题实体；
    2. 图谱检索相关实体并去重；
    3. 拉取主实体详情（关系 + 原文证据）；
    4. 组装中文回答。
    """

    def post(self, request):
        question = str(request.data.get("question") or "").strip()
        if not question:
            return Response({"detail": "question 不能为空。"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entities = self._extract_entities(question)
            if not entities:
                return Response(
                    {
                        "answer": "未在问题中识别到有效实体。请尽量使用明确术语，如“桂枝汤”“中风”“发热”。",
                        "confidence": 0.0,
                        "entities": [],
                        "related_entities": [],
                        "cypher": None,
                    }
                )

            related_entities = self._search_related_entities(entities)
            if not related_entities:
                return Response(
                    {
                        "answer": "图谱中没有检索到相关实体，请换一个术语再试。",
                        "confidence": 0.0,
                        "entities": entities,
                        "related_entities": [],
                        "cypher": None,
                    }
                )

            main_entity = related_entities[0]
            detail = get_entity_detail(str(main_entity["entity_id"]), relation_limit=10, evidence_limit=3)
            answer = self._build_answer(main_entity=main_entity, detail=detail)
            confidence = self._calculate_confidence(main_entity=main_entity, detail=detail)

            return Response(
                {
                    "answer": answer,
                    "confidence": confidence,
                    "entities": entities,
                    "related_entities": related_entities[:5],
                    "cypher": None,
                }
            )
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"detail": f"问答处理失败：{exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _extract_entities(self, question: str) -> list[dict[str, Any]]:
        try:
            ner_result = predict_ner(question)
            ner_entities = ner_result.get("entities", [])
            if ner_entities:
                return self._dedupe_prediction_entities(ner_entities)
        except Exception:
            pass
        return self._extract_entities_from_graph(question)

    @staticmethod
    def _dedupe_prediction_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entity in entities:
            entity_text = str(entity.get("text") or "").strip()
            entity_type = str(entity.get("type") or "").strip()
            start = int(entity.get("start") or 0)
            end = int(entity.get("end") or 0)
            if not entity_text or not entity_type or end <= start:
                continue
            key = f"{entity_type}|{entity_text}|{start}|{end}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"type": entity_type, "text": entity_text, "start": start, "end": end})
        return deduped

    @staticmethod
    def _extract_entities_from_graph(question: str) -> list[dict[str, Any]]:
        data = load_graph_data()
        entity_rows = sorted(
            data["entities"].values(),
            key=lambda item: len(str(item.get("name") or "")),
            reverse=True,
        )

        matched: list[dict[str, Any]] = []
        seen_text: set[str] = set()
        for entity in entity_rows:
            name = str(entity.get("name") or "").strip()
            if not name or name in seen_text:
                continue
            start = question.find(name)
            if start < 0:
                continue
            seen_text.add(name)
            matched.append(
                {
                    "type": str(entity.get("entity_type") or ""),
                    "text": name,
                    "start": start,
                    "end": start + len(name),
                }
            )
        return matched

    @staticmethod
    def _search_related_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for entity in entities:
            payload = search_entities(
                keyword=str(entity.get("text") or ""),
                entity_type=str(entity.get("type") or ""),
                limit=5,
            )
            for row in payload.get("results", []):
                entity_id = str(row.get("entity_id") or "")
                if not entity_id or entity_id in seen_ids:
                    continue
                seen_ids.add(entity_id)
                merged.append(row)
        return merged

    def _build_answer(self, main_entity: dict[str, Any], detail: dict[str, Any]) -> str:
        entity_name = str(main_entity.get("name") or "")
        entity_type = str(main_entity.get("entity_type") or "")
        type_name = self._translate_entity_type(entity_type)

        stats = detail.get("stats") or {}
        incoming = detail.get("incoming_relations") or []
        outgoing = detail.get("outgoing_relations") or []
        mentions = detail.get("mentions") or []

        parts: list[str] = []
        parts.append(f"【{entity_name}】（{type_name}）")
        parts.append(
            f"图谱统计：入边 {int(stats.get('incoming_relation_count') or 0)} 条，"
            f"出边 {int(stats.get('outgoing_relation_count') or 0)} 条，"
            f"原文提及 {int(stats.get('mention_count') or 0)} 次。"
        )

        relation_lines: list[str] = []
        for rel in incoming[:3]:
            related = rel.get("related_entity") or {}
            relation_lines.append(
                f"{related.get('name', '未知实体')} → {entity_name}（{self._translate_relation_type(str(rel.get('relation_type') or ''))}）"
            )
        for rel in outgoing[:3]:
            related = rel.get("related_entity") or {}
            relation_lines.append(
                f"{entity_name} → {related.get('name', '未知实体')}（{self._translate_relation_type(str(rel.get('relation_type') or ''))}）"
            )
        if relation_lines:
            parts.append("关键关系：")
            parts.extend([f"- {line}" for line in relation_lines])

        if mentions:
            parts.append("原文证据：")
            for mention in mentions[:2]:
                clause_text = str(mention.get("clause_text") or "").strip()
                line_number = mention.get("line_number")
                if clause_text:
                    if line_number is not None:
                        parts.append(f"- “{clause_text}”（行号：{line_number}）")
                    else:
                        parts.append(f"- “{clause_text}”")

        parts.append("说明：当前为图谱模板回答，不是通用大模型自由生成。")
        return "\n".join(parts)

    @staticmethod
    def _translate_entity_type(entity_type: str) -> str:
        mapping = {
            "SYNDROME": "证候",
            "SYMPTOM": "症状",
            "FORMULA": "方剂",
            "HERB": "中药",
            "THERAPY": "治法",
            "ADMINISTRATION": "服法",
        }
        return mapping.get(entity_type, entity_type)

    @staticmethod
    def _translate_relation_type(relation_type: str) -> str:
        mapping = {
            "SYNDROME_HAS_SYMPTOM": "证候具有症状",
            "SYNDROME_TO_FORMULA": "证候对应方剂",
            "FORMULA_CONTAINS_HERB": "方剂包含中药",
            "FORMULA_HAS_ADMINISTRATION": "方剂对应服法",
        }
        return mapping.get(relation_type, relation_type)

    @staticmethod
    def _calculate_confidence(main_entity: dict[str, Any], detail: dict[str, Any]) -> float:
        mention_count = int(main_entity.get("mention_count") or 0)
        stats = detail.get("stats") or {}
        incoming_count = int(stats.get("incoming_relation_count") or 0)
        outgoing_count = int(stats.get("outgoing_relation_count") or 0)

        if mention_count >= 10:
            base = 0.9
        elif mention_count >= 5:
            base = 0.8
        elif mention_count >= 1:
            base = 0.7
        else:
            base = 0.5

        if incoming_count + outgoing_count >= 6:
            bonus = 0.08
        elif incoming_count + outgoing_count >= 3:
            bonus = 0.04
        else:
            bonus = 0.0
        return round(min(0.98, base + bonus), 4)
