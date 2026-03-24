from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modeling.services import predict_ner
from graph.services import search_entities, get_entity_detail


class AskQuestionView(APIView):
    """
    智能问答接口

    流程：
    1. 使用 NER 识别问题中的实体（如失败则降级为关键词匹配）
    2. 在知识图谱中搜索相关实体
    3. 获取实体的详细关系图谱
    4. 组织成自然语言答案
    """

    def post(self, request):
        question = str(request.data.get("question") or "").strip()
        if not question:
            return Response({"detail": "question is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Step 1: 尝试用 NER 识别问题中的实体
            entities = []
            try:
                ner_result = predict_ner(question)
                entities = ner_result.get("entities", [])
            except Exception:
                # NER 失败（如GLM API未配置），降级为关键词提取
                entities = self._extract_entities_from_question(question)

            # 如果没有识别到实体，直接返回提示
            if not entities:
                return Response({
                    "answer": "抱歉，我无法在你输入的问题中识别到相关的实体（如方剂、症状、证候等）。请尝试使用更明确的术语，例如「桂枝汤」、「太阳病」等。",
                    "confidence": 0.0,
                    "entities": [],
                    "related_entities": [],
                })

            # Step 2: 在知识图谱中搜索这些实体
            related_entities = []
            for entity in entities:
                # 根据识别到的实体类型和文本搜索
                results = search_entities(
                    keyword=entity["text"],
                    entity_type=entity["type"],
                    limit=5
                )
                related_entities.extend(results.get("results", []))

            # 去重（按 entity_id）
            seen = set()
            unique_entities = []
            for e in related_entities:
                if e["entity_id"] not in seen:
                    seen.add(e["entity_id"])
                    unique_entities.append(e)

            # Step 3: 获取第一个（最相关）实体的详细信息
            if unique_entities:
                main_entity = unique_entities[0]
                detail = get_entity_detail(main_entity["entity_id"], relation_limit=10, evidence_limit=3)

                # Step 4: 组织答案
                answer = self._build_answer(question, main_entity, detail, len(entities))
                confidence = self._calculate_confidence(main_entity, detail, len(entities))

                return Response({
                    "answer": answer,
                    "confidence": confidence,
                    "entities": entities,
                    "related_entities": unique_entities[:5],
                    "cypher": None,  # 可选：记录使用的查询语句
                })

            return Response({
                "answer": "抱歉，知识图谱中没有找到相关的内容。",
                "confidence": 0.0,
                "entities": entities,
                "related_entities": [],
            })

        except Exception as exc:
            return Response(
                {"detail": f"问答处理失败: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _extract_entities_from_question(self, question: str) -> list[dict]:
        """
        从问题中提取实体（降级方案）
        简单匹配图谱中存在的实体名称
        """
        from graph.services import load_graph_data

        # 加载图谱实体
        data = load_graph_data()
        entities = []

        # 遍历图谱实体，看问题中是否包含实体名
        for entity in data["entities"].values():
            if entity["name"] in question:
                entities.append({
                    "type": entity["entity_type"],
                    "text": entity["name"],
                    "start": question.find(entity["name"]),
                    "end": question.find(entity["name"]) + len(entity["name"]),
                })

        # 去重（按文本）
        seen = set()
        unique = []
        for e in entities:
            if e["text"] not in seen:
                seen.add(e["text"])
                unique.append(e)

        return unique

    def _build_answer(self, question: str, entity: dict, detail: dict, entity_count: int) -> str:
        """根据图谱信息构建自然语言答案"""
        entity_type = entity["entity_type"]
        entity_name = entity["name"]

        # 中文实体类型映射
        type_names = {
            "SYNDROME": "证候",
            "SYMPTOM": "症状",
            "FORMULA": "方剂",
            "HERB": "中药",
            "THERAPY": "治法",
        }
        type_name = type_names.get(entity_type, entity_type)

        # 开始构建答案
        parts = [f"关于“{entity_name}”（{type_name}）："]

        # 添加统计信息
        stats = detail.get("stats", {})
        parts.append(f"它在知识图谱中关联 {stats.get('incoming_relation_count', 0)} 条入边、{stats.get('outgoing_relation_count', 0)} 条出边，")
        parts.append(f"共在 {stats.get('mention_count', 0)} 条原文中提及。")

        # 添加关键关系（入边：谁指向它；出边：它指向谁）
        incoming = detail.get("incoming_relations", [])
        outgoing = detail.get("outgoing_relations", [])

        if incoming:
            top_incoming = incoming[:3]
            parts.append("\n**相关关系：**")
            for rel in top_incoming:
                related = rel["related_entity"]
                rel_type = self._translate_relation_type(rel["relation_type"])
                parts.append(f"• {related['name']} → {entity_name}（{rel_type}，证据 {rel['evidence_count']} 条）")

        if outgoing:
            for rel in outgoing[:3]:
                related = rel["related_entity"]
                rel_type = self._translate_relation_type(rel["relation_type"])
                parts.append(f"• {entity_name} → {related['name']}（{rel_type}，证据 {rel['evidence_count']} 条）")

        # 添加原文证据
        mentions = detail.get("mentions", [])
        if mentions:
            parts.append("\n**原文证据：**")
            for i, mention in enumerate(mentions[:2], 1):
                parts.append(f"{i}. “{mention['clause_text']}”")
                parts.append(f"   （出处：第 {mention['line_number']} 行）")

        parts.append("\n以上信息来自《伤寒论》知识图谱。")

        return "".join(parts)

    def _translate_relation_type(self, rel_type: str) -> str:
        """将英文关系类型翻译为中文"""
        relation_map = {
            "SYNDROME_HAS_SYMPTOM": "证候具有症状",
            "SYNDROME_TO_FORMULA": "证候对应方剂",
            "FORMULA_CONTAINS_HERB": "方剂包含中药",
            "FORMULA_HAS_ADMINISTRATION": "方剂具有煎服法",
            "HAS_SYMPTOM": "具有症状",
            "INDICATES_SYNDROME": "对应证候",
            "TREATS_WITH_FORMULA": "使用方剂",
            "CONTAINS_HERB": "包含中药",
            "HAS_THERAPY": "具有治法",
            "FROM_ARTICLE": "来源于条文",
        }
        return relation_map.get(rel_type, rel_type)

    def _calculate_confidence(self, entity: dict, detail: dict, entity_count: int) -> float:
        """简单计算置信度"""
        # 根据实体被提及次数、关系数量等因素
        mention_count = entity.get("mention_count", 0)
        outgoing_count = detail.get("stats", {}).get("outgoing_relation_count", 0)
        incoming_count = detail.get("stats", {}).get("incoming_relation_count", 0)

        # 基础分
        if mention_count > 10:
            base = 0.9
        elif mention_count > 5:
            base = 0.8
        elif mention_count > 0:
            base = 0.7
        else:
            base = 0.5

        # 有多条关系链加分
        if outgoing_count >= 3 and incoming_count >= 2:
            bonus = 0.1
        elif outgoing_count >= 2 or incoming_count >= 2:
            bonus = 0.05
        else:
            bonus = 0.0

        return min(0.99, base + bonus)