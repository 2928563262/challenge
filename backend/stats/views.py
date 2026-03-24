from __future__ import annotations

from django.http import JsonResponse
from django.views import View
from typing import Any

from graph.services import build_graph_summary, load_graph_data
from corpus.services import build_overview_payload


class OverviewStatsView(View):
    """全局概览统计"""

    def get(self, request) -> JsonResponse:
        # 获取图谱摘要
        summary = build_graph_summary()
        
        # 获取语料概览
        try:
            overview = build_overview_payload()
            article_count = overview.get('stats', {}).get('entry_count', 0)
        except Exception:
            article_count = 0

        # 提取实体类型分布
        entity_type_breakdown = summary.get('entity_type_breakdown', {})
        
        # 提取关系统计
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

        return JsonResponse({
            'kpi': {
                'article_count': article_count,
                'entity_count': summary.get('entity_node_count', 0),
                'relation_count': summary.get('entity_relation_count', 0),
                'clause_mention_count': summary.get('clause_mention_count', 0),
            },
            'entity_type_breakdown': entity_type_breakdown,
            'relation_type_breakdown': relation_type_breakdown,
            'top_entities_by_type': top_entities_by_type
        })


class HerbAnalysisView(View):
    """中药分析"""

    def get(self, request) -> JsonResponse:
        limit = int(request.GET.get('limit', 20))
        
        # 从 graph service 获取数据
        data = load_graph_data()
        
        # 筛选所有中药实体
        all_herbs = [
            e for e in data['entities'].values() 
            if e['entity_type'] == 'HERB'
        ]
        # 按提及次数排序
        all_herbs.sort(key=lambda x: (-x['mention_count'], x['name']))
        
        # 取前 limit 个
        top_herbs = all_herbs[:limit]
        
        result_herbs = [
            {'name': h['name'], 'count': h['mention_count']}
            for h in top_herbs
        ]
        
        # 构建共现矩阵（基于共享的方剂）
        herb_names_list = [h['name'] for h in top_herbs]
        cooccurrence_matrix = {}
        
        # 找出所有包含 HERB 的 FORMULA
        formulas_with_herbs = []
        for entity in data['entities'].values():
            if entity['entity_type'] == 'FORMULA':
                outgoing = data['outgoing_relations'].get(entity['entity_id'], [])
                herb_ids = [rel['end_id'] for rel in outgoing if rel['relation_type'] == 'FORMULA_CONTAINS_HERB']
                herb_names = [data['entities'][hid]['name'] for hid in herb_ids if hid in data['entities']]
                formulas_with_herbs.append({
                    'name': entity['name'],
                    'herbs': herb_names
                })
        
        # 计算共现
        for i, herb1 in enumerate(herb_names_list):
            cooccurrence_matrix[herb1] = {}
            for herb2 in herb_names_list:
                if herb1 == herb2:
                    continue
                count = sum(1 for f in formulas_with_herbs if herb1 in f['herbs'] and herb2 in f['herbs'])
                if count > 0:
                    cooccurrence_matrix[herb1][herb2] = count

        return JsonResponse({
            'top_herbs': result_herbs,
            'cooccurrence_matrix': cooccurrence_matrix
        })


class FormulaAnalysisView(View):
    """方剂分析"""

    def get(self, request) -> JsonResponse:
        limit = int(request.GET.get('limit', 20))
        
        data = load_graph_data()
        
        # 筛选所有方剂
        all_formulas = [
            e for e in data['entities'].values() 
            if e['entity_type'] == 'FORMULA'
        ]
        all_formulas.sort(key=lambda x: (-x['mention_count'], x['name']))
        
        top_formulas = all_formulas[:limit]
        
        result_formulas = []
        formula_herb_network = {'nodes': [], 'edges': []}
        
        for f in top_formulas:
            # 统计方剂包含的中药数量
            outgoing = data['outgoing_relations'].get(f['entity_id'], [])
            herb_relations = [rel for rel in outgoing if rel['relation_type'] == 'FORMULA_CONTAINS_HERB']
            herb_count = len(herb_relations)
            
            result_formulas.append({
                'name': f['name'],
                'mention_count': f['mention_count'],
                'herb_count': herb_count
            })
            
            # 添加到网络图节点（方剂）
            formula_node_id = f['name']
            formula_herb_network['nodes'].append({
                'id': formula_node_id,
                'name': formula_node_id,
                'type': 'formula',
                'symbolSize': 20 + herb_count * 5
            })
            
            # 添加中药节点和边
            for rel in herb_relations:
                herb_id = rel['end_id']
                if herb_id not in data['entities']:
                    continue
                herb = data['entities'][herb_id]
                herb_name = herb['name']
                
                # 添加中药节点（如果还没添加）
                if not any(n['id'] == herb_name for n in formula_herb_network['nodes']):
                    formula_herb_network['nodes'].append({
                        'id': herb_name,
                        'name': herb_name,
                        'type': 'herb',
                        'symbolSize': 10
                    })
                
                # 添加边
                formula_herb_network['edges'].append({
                    'source': formula_node_id,
                    'target': herb_name
                })

        return JsonResponse({
            'top_formulas': result_formulas,
            'formula_herb_network': formula_herb_network
        })


class ClinicalPathView(View):
    """诊疗路径分析（症状→证候→方剂）"""

    def get(self, request) -> JsonResponse:
        data = load_graph_data()
        
        # 收集三类实体
        symptoms = [e for e in data['entities'].values() if e['entity_type'] == 'SYMPTOM']
        syndromes = [e for e in data['entities'].values() if e['entity_type'] == 'SYNDROME']
        formulas = [e for e in data['entities'].values() if e['entity_type'] == 'FORMULA']
        
        # 构建症状->证候关系
        symptom_to_syndrome = []
        for symptom in symptoms:
            outgoing = data['outgoing_relations'].get(symptom['entity_id'], [])
            for rel in outgoing:
                if rel['relation_type'] == 'SYMPTOM_TO_SYNDROME':
                    target_id = rel['end_id']
                    if target_id in data['entities']:
                        target = data['entities'][target_id]
                        if target['entity_type'] == 'SYNDROME':
                            symptom_to_syndrome.append({
                                'from': symptom['name'],
                                'to': target['name'],
                                'weight': rel.get('evidence_count', 1)
                            })
        
        # 构建证候->方剂关系
        syndrome_to_formula = []
        for syndrome in syndromes:
            outgoing = data['outgoing_relations'].get(syndrome['entity_id'], [])
            for rel in outgoing:
                if rel['relation_type'] == 'SYNDROME_TO_FORMULA':
                    target_id = rel['end_id']
                    if target_id in data['entities']:
                        target = data['entities'][target_id]
                        if target['entity_type'] == 'FORMULA':
                            syndrome_to_formula.append({
                                'from': syndrome['name'],
                                'to': target['name'],
                                'weight': rel.get('evidence_count', 1)
                            })
        
        # 构建全链路桑基图 nodes 和 links
        nodes = []
        links = []
        
        # 添加症状节点
        for s in symptoms[:10]:  # 限制数量
            nodes.append({'id': s['name'], 'name': s['name'], 'category': 'symptom'})
        
        # 添加证候节点
        for s in syndromes[:10]:
            nodes.append({'id': s['name'], 'name': s['name'], 'category': 'syndrome'})
        
        # 添加方剂节点
        for f in formulas[:10]:
            nodes.append({'id': f['name'], 'name': f['name'], 'category': 'formula'})
        
        # 添加症状->证候链接
        for link in symptom_to_syndrome:
            if any(n['id'] == link['from'] for n in nodes) and any(n['id'] == link['to'] for n in nodes):
                links.append({
                    'source': link['from'],
                    'target': link['to'],
                    'value': link['weight']
                })
        
        # 添加证候->方剂链接
        for link in syndrome_to_formula:
            if any(n['id'] == link['from'] for n in nodes) and any(n['id'] == link['to'] for n in nodes):
                links.append({
                    'source': link['from'],
                    'target': link['to'],
                    'value': link['weight']
                })
        
        return JsonResponse({
            'symptom_to_syndrome': symptom_to_syndrome,
            'syndrome_to_formula': syndrome_to_formula,
            'full_sankey': {
                'nodes': nodes,
                'links': links
            }
        })


class TextAnalysisView(View):
    """条文分析"""

    def get(self, request) -> JsonResponse:
        data = load_graph_data()
        
        # 获取所有条文（clause_node）
        clauses = data.get('clauses', {}).values() if 'clauses' in data else []
        
        # 如果有条文数据，计算每条文的长度和实体数
        article_lengths = []
        entity_matrix = {'articles': [], 'entities': [], 'matrix': []}
        
        if clauses:
            # 提取所有实体名称作为矩阵列
            all_entity_names = [e['name'] for e in data['entities'].values()][:20]  # 限制20个
            
            for clause in clauses:
                clause_id = clause.get('clause_id', '')
                text = clause.get('text', '')
                article_lengths.append({
                    'id': clause_id,
                    'length': len(text),
                    'entities': 0  # TODO: 从 mentions 计算
                })
                
                # 构建矩阵行（该条文包含哪些实体）
                row = []
                clause_mentions = data.get('mentions_by_clause', {}).get(clause_id, [])
                mentioned_entity_ids = set(m['entity_id'] for m in clause_mentions)
                
                for entity_name in all_entity_names:
                    # 找到对应 entity_id
                    entity = next((e for e in data['entities'].values() if e['name'] == entity_name), None)
                    if entity and entity['entity_id'] in mentioned_entity_ids:
                        row.append(1)
                    else:
                        row.append(0)
                
                entity_matrix['matrix'].append(row)
            
            entity_matrix['articles'] = [a['id'] for a in article_lengths]
            entity_matrix['entities'] = all_entity_names
        
        return JsonResponse({
            'article_lengths': article_lengths[:50],  # 限制条数
            'entity_density': [],  # TODO
            'entity_matrix': entity_matrix
        })
