from __future__ import annotations

from django.http import JsonResponse
from django.views import View
from typing import Any

from graph.services import build_graph_summary
from corpus.services import build_overview_payload


class OverviewStatsView(View):
    """全局概览统计"""

    def get(self, request) -> JsonResponse:
        # 获取图谱摘要（包含实体总数、关系统计、top_entities）
        summary = build_graph_summary()
        
        # 获取语料概览
        try:
            overview = build_overview_payload()
            article_count = overview.get('stats', {}).get('entry_count', 0)
        except Exception:
            article_count = 0

        # 提取实体类型分布
        entity_type_breakdown = summary.get('entity_type_breakdown', {})
        
        # 提取关系统计（需要从 relation_type_breakdown 聚合）
        relation_type_breakdown = summary.get('relation_type_breakdown', {})

        # 按类型分组 top_entities
        top_entities_by_type = {
            'FORMULA': [],
            'HERB': [],
            'SYNDROME': [],
            'SYMPTOM': [],
            'THERAPY': [],
            'ADMINISTRATION': []
        }
        for entity in summary.get('top_entities', []):
            entity_type = entity.get('entity_type')
            if entity_type in top_entities_by_type:
                top_entities_by_type[entity_type].append({
                    'name': entity.get('name'),
                    'mention_count': entity.get('mention_count', 0)
                })

        data = {
            'kpi': {
                'article_count': article_count,
                'entity_count': summary.get('entity_node_count', 0),
                'relation_count': summary.get('entity_relation_count', 0),
                'clause_mention_count': summary.get('clause_mention_count', 0),
            },
            'entity_type_breakdown': entity_type_breakdown,
            'relation_type_breakdown': relation_type_breakdown,
            'top_entities_by_type': top_entities_by_type
        }

        return JsonResponse(data)


class HerbAnalysisView(View):
    """中药分析"""

    def get(self, request) -> JsonResponse:
        limit = int(request.GET.get('limit', 20))
        
        # 从 summary 中提取高频中药
        from graph.services import build_graph_summary
        summary = build_graph_summary()
        top_entities = summary.get('top_entities', [])
        
        # 筛选中药
        herbs = [
            {'name': e['name'], 'count': e['mention_count']}
            for e in top_entities if e['entity_type'] == 'HERB'
        ][:limit]
        
        # 共现矩阵暂时为空（需要更复杂的查询）
        cooccurrence_matrix = {}

        return JsonResponse({
            'top_herbs': herbs,
            'cooccurrence_matrix': cooccurrence_matrix
        })


class FormulaAnalysisView(View):
    """方剂分析"""

    def get(self, request) -> JsonResponse:
        limit = int(request.GET.get('limit', 20))
        
        # 从 summary 中提取方剂
        from graph.services import build_graph_summary
        summary = build_graph_summary()
        top_entities = summary.get('top_entities', [])
        
        formulas = []
        for e in top_entities:
            if e['entity_type'] == 'FORMULA':
                # TODO: 查询方剂包含的中药数量（需要额外查询）
                formulas.append({
                    'name': e['name'],
                    'mention_count': e['mention_count'],
                    'herb_count': 0  # 待实现
                })
        
        # 网络图暂时用空数据
        network = {'nodes': [], 'edges': []}

        return JsonResponse({
            'top_formulas': formulas[:limit],
            'formula_herb_network': network
        })


class ClinicalPathView(View):
    """诊疗路径分析（症状→证候→方剂）"""

    def get(self, request) -> JsonResponse:
        # TODO: 从 Neo4j 查询完整的诊疗路径
        # 暂时返回空数据
        return JsonResponse({
            'symptom_to_syndrome': [],
            'syndrome_to_formula': [],
            'full_sankey': {
                'nodes': [],
                'links': []
            }
        })


class TextAnalysisView(View):
    """条文分析"""

    def get(self, request) -> JsonResponse:
        # TODO: 实现条文统计
        return JsonResponse({
            'article_lengths': [],
            'entity_density': [],
            'entity_matrix': {
                'articles': [],
                'entities': [],
                'matrix': []
            }
        })
