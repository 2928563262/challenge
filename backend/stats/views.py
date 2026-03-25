from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from django.http import JsonResponse
from django.views import View

from corpus.services import build_overview_payload
from graph.services import build_graph_summary, load_graph_data


ENTITY_TYPES = [
    "SYNDROME",
    "SYMPTOM",
    "FORMULA",
    "HERB",
    "THERAPY",
    "ADMINISTRATION",
]


def _safe_limit(raw: str | None, *, default: int = 20, max_value: int = 80) -> int:
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, max_value))


def _entity_name(entity: dict[str, Any]) -> str:
    return str(entity.get("name") or "")


def _entity_type(entity: dict[str, Any]) -> str:
    return str(entity.get("entity_type") or "")


def _entity_mention(entity: dict[str, Any]) -> int:
    return int(entity.get("mention_count") or 0)


class OverviewStatsView(View):
    """统计总览接口。"""

    def get(self, request) -> JsonResponse:
        data = load_graph_data()
        graph_summary = build_graph_summary()

        try:
            corpus_overview = build_overview_payload()
            article_count = int(corpus_overview.get("stats", {}).get("entry_count", 0))
        except Exception:
            article_count = 0

        entities = list(data["entities"].values())
        top_entities_by_type: dict[str, list[dict[str, Any]]] = {entity_type: [] for entity_type in ENTITY_TYPES}
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in entities:
            grouped[_entity_type(entity)].append(entity)

        for entity_type in ENTITY_TYPES:
            ranked = sorted(grouped.get(entity_type, []), key=lambda item: (-_entity_mention(item), _entity_name(item)))
            top_entities_by_type[entity_type] = [
                {"name": _entity_name(item), "mention_count": _entity_mention(item)}
                for item in ranked[:20]
            ]

        return JsonResponse(
            {
                "kpi": {
                    "article_count": article_count,
                    "entity_count": int(graph_summary.get("entity_node_count", 0)),
                    "relation_count": int(graph_summary.get("entity_relation_count", 0)),
                    "clause_mention_count": int(graph_summary.get("clause_mention_count", 0)),
                },
                "entity_type_breakdown": graph_summary.get("entity_type_breakdown", {}),
                "relation_type_breakdown": graph_summary.get("relation_type_breakdown", {}),
                "top_entities_by_type": top_entities_by_type,
            }
        )


class HerbAnalysisView(View):
    """中药频次与共现分析。"""

    def get(self, request) -> JsonResponse:
        limit = _safe_limit(request.GET.get("limit"), default=20, max_value=60)
        data = load_graph_data()

        herbs = [entity for entity in data["entities"].values() if _entity_type(entity) == "HERB"]
        herbs.sort(key=lambda item: (-_entity_mention(item), _entity_name(item)))
        top_herbs = herbs[:limit]
        top_herb_ids = {str(item.get("entity_id") or "") for item in top_herbs}

        # 每味中药关联到的高频方剂（用于前端提示）
        top_herb_rows: list[dict[str, Any]] = []
        for herb in top_herbs:
            herb_id = str(herb.get("entity_id") or "")
            incoming = data["incoming_relations"].get(herb_id, [])
            formula_hits: list[tuple[str, int]] = []
            for relation in incoming:
                if str(relation.get("relation_type") or "") != "FORMULA_CONTAINS_HERB":
                    continue
                start_id = str(relation.get("start_id") or "")
                formula = data["entities"].get(start_id)
                if not formula or _entity_type(formula) != "FORMULA":
                    continue
                formula_hits.append((_entity_name(formula), int(relation.get("evidence_count") or 0)))
            formula_hits.sort(key=lambda item: (-item[1], item[0]))
            top_herb_rows.append(
                {
                    "name": _entity_name(herb),
                    "count": _entity_mention(herb),
                    "formulas": [name for name, _ in formula_hits[:8]],
                }
            )

        # 共现矩阵：同一方剂内共同出现即记一次
        pair_counter: Counter[tuple[str, str]] = Counter()
        for formula in data["entities"].values():
            if _entity_type(formula) != "FORMULA":
                continue
            formula_id = str(formula.get("entity_id") or "")
            outgoing = data["outgoing_relations"].get(formula_id, [])
            herb_names: list[str] = []
            for relation in outgoing:
                if str(relation.get("relation_type") or "") != "FORMULA_CONTAINS_HERB":
                    continue
                herb_id = str(relation.get("end_id") or "")
                if herb_id not in top_herb_ids:
                    continue
                herb_entity = data["entities"].get(herb_id)
                if herb_entity and _entity_type(herb_entity) == "HERB":
                    herb_names.append(_entity_name(herb_entity))

            unique_names = sorted(set(herb_names))
            for left, right in combinations(unique_names, 2):
                pair_counter[(left, right)] += 1
                pair_counter[(right, left)] += 1

        cooccurrence_matrix: dict[str, dict[str, int]] = {}
        top_names = [row["name"] for row in top_herb_rows]
        for herb_name in top_names:
            cooccurrence_matrix[herb_name] = {}
            for other_name in top_names:
                if herb_name == other_name:
                    continue
                count = int(pair_counter.get((herb_name, other_name), 0))
                if count > 0:
                    cooccurrence_matrix[herb_name][other_name] = count

        return JsonResponse({"top_herbs": top_herb_rows, "cooccurrence_matrix": cooccurrence_matrix})


class FormulaAnalysisView(View):
    """方剂频次与方剂-药味网络。"""

    def get(self, request) -> JsonResponse:
        limit = _safe_limit(request.GET.get("limit"), default=20, max_value=60)
        data = load_graph_data()

        formulas = [entity for entity in data["entities"].values() if _entity_type(entity) == "FORMULA"]
        formulas.sort(key=lambda item: (-_entity_mention(item), _entity_name(item)))
        top_formulas = formulas[:limit]

        formula_rows: list[dict[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_node_ids: set[str] = set()
        seen_edges: set[tuple[str, str]] = set()

        def ensure_node(node_id: str, node_name: str, node_type: str) -> None:
            if node_id in seen_node_ids:
                return
            seen_node_ids.add(node_id)
            nodes.append({"id": node_id, "name": node_name, "type": node_type})

        for formula in top_formulas:
            formula_id = str(formula.get("entity_id") or "")
            formula_name = _entity_name(formula)
            ensure_node(formula_id, formula_name, "formula")

            outgoing = data["outgoing_relations"].get(formula_id, [])
            herb_ids: list[str] = []
            for relation in outgoing:
                if str(relation.get("relation_type") or "") != "FORMULA_CONTAINS_HERB":
                    continue
                herb_id = str(relation.get("end_id") or "")
                herb_entity = data["entities"].get(herb_id)
                if not herb_entity or _entity_type(herb_entity) != "HERB":
                    continue
                herb_ids.append(herb_id)
                ensure_node(herb_id, _entity_name(herb_entity), "herb")
                edge_key = (formula_id, herb_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append({"source": formula_id, "target": herb_id})

            formula_rows.append(
                {
                    "name": formula_name,
                    "mention_count": _entity_mention(formula),
                    "herb_count": len(set(herb_ids)),
                }
            )

        return JsonResponse({"top_formulas": formula_rows, "formula_herb_network": {"nodes": nodes, "edges": edges}})


class ClinicalPathView(View):
    """临床路径：症状 -> 证候 -> 方剂。"""

    def get(self, request) -> JsonResponse:
        data = load_graph_data()

        symptom_to_syndrome_counter: Counter[tuple[str, str]] = Counter()
        syndrome_to_formula_counter: Counter[tuple[str, str]] = Counter()

        for syndrome in data["entities"].values():
            if _entity_type(syndrome) != "SYNDROME":
                continue
            syndrome_id = str(syndrome.get("entity_id") or "")
            syndrome_name = _entity_name(syndrome)
            outgoing = data["outgoing_relations"].get(syndrome_id, [])
            for relation in outgoing:
                relation_type = str(relation.get("relation_type") or "")
                end_id = str(relation.get("end_id") or "")
                target = data["entities"].get(end_id)
                if not target:
                    continue
                weight = max(1, int(relation.get("evidence_count") or 1))
                if relation_type == "SYNDROME_HAS_SYMPTOM" and _entity_type(target) == "SYMPTOM":
                    symptom_to_syndrome_counter[(_entity_name(target), syndrome_name)] += weight
                elif relation_type == "SYNDROME_TO_FORMULA" and _entity_type(target) == "FORMULA":
                    syndrome_to_formula_counter[(syndrome_name, _entity_name(target))] += weight

        symptom_to_syndrome = [
            {"from": left, "to": right, "weight": weight}
            for (left, right), weight in symptom_to_syndrome_counter.items()
        ]
        syndrome_to_formula = [
            {"from": left, "to": right, "weight": weight}
            for (left, right), weight in syndrome_to_formula_counter.items()
        ]

        symptom_to_syndrome.sort(key=lambda item: (-int(item["weight"]), item["from"], item["to"]))
        syndrome_to_formula.sort(key=lambda item: (-int(item["weight"]), item["from"], item["to"]))

        # 组装桑基图（限制规模，防止前端过重）
        max_symptom_links = 40
        max_formula_links = 40
        selected_symptom_links = symptom_to_syndrome[:max_symptom_links]
        selected_formula_links = syndrome_to_formula[:max_formula_links]

        node_category: dict[str, str] = {}
        for item in selected_symptom_links:
            node_category[item["from"]] = "symptom"
            node_category[item["to"]] = "syndrome"
        for item in selected_formula_links:
            node_category[item["from"]] = "syndrome"
            node_category[item["to"]] = "formula"

        nodes = [{"id": name, "name": name, "category": category} for name, category in node_category.items()]
        links = [
            {"source": item["from"], "target": item["to"], "value": int(item["weight"])}
            for item in [*selected_symptom_links, *selected_formula_links]
        ]

        return JsonResponse(
            {
                "symptom_to_syndrome": selected_symptom_links,
                "syndrome_to_formula": selected_formula_links,
                "full_sankey": {"nodes": nodes, "links": links},
            }
        )


class TextAnalysisView(View):
    """条文长度、密度与条文-实体矩阵。"""

    def get(self, request) -> JsonResponse:
        data = load_graph_data()

        clauses = sorted(
            list(data["clauses"].values()),
            key=lambda item: (
                str(item.get("record_id") or ""),
                int(item.get("line_number") or 0),
                str(item.get("clause_id") or ""),
            ),
        )

        mentions_by_clause: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity_id, mention_rows in data["mentions_by_entity"].items():
            for mention in mention_rows:
                clause_id = str(mention.get("clause_id") or "")
                if not clause_id:
                    continue
                mentions_by_clause[clause_id].append({"entity_id": entity_id, **mention})

        article_lengths: list[dict[str, Any]] = []
        entity_density: list[dict[str, Any]] = []
        for clause in clauses[:120]:
            clause_id = str(clause.get("clause_id") or "")
            text = str(clause.get("text") or "")
            mention_rows = mentions_by_clause.get(clause_id, [])
            mention_count = len(mention_rows)
            unique_entities = len({str(item.get("entity_id") or "") for item in mention_rows})
            text_len = max(1, len(text))
            article_lengths.append({"id": clause_id, "length": len(text), "entities": unique_entities})
            entity_density.append({"article_id": clause_id, "density": round(mention_count / text_len, 4)})

        top_entities = sorted(
            data["entities"].values(),
            key=lambda item: (-_entity_mention(item), _entity_name(item)),
        )[:12]
        top_entity_ids = [str(item.get("entity_id") or "") for item in top_entities]
        top_entity_names = [_entity_name(item) for item in top_entities]

        matrix_articles = [row["id"] for row in article_lengths[:40]]
        matrix_data: list[list[int]] = []
        for clause_id in matrix_articles:
            counter: Counter[str] = Counter(str(item.get("entity_id") or "") for item in mentions_by_clause.get(clause_id, []))
            matrix_row = [int(counter.get(entity_id, 0)) for entity_id in top_entity_ids]
            matrix_data.append(matrix_row)

        return JsonResponse(
            {
                "article_lengths": article_lengths[:80],
                "entity_density": entity_density[:80],
                "entity_matrix": {
                    "articles": matrix_articles,
                    "entities": top_entity_names,
                    "matrix": matrix_data,
                },
            }
        )
