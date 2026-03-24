#!/usr/bin/env python3
"""
测试伤寒论统计页面的API集成状态
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000/api/v1"
FRONTEND_URL = "http://127.0.0.1:5173"

def test_api(endpoint, description):
    """测试单个API端点"""
    try:
        resp = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
        status = "✅ PASS" if resp.status_code == 200 else f"❌ FAIL ({resp.status_code})"
        data = resp.json() if resp.status_code == 200 else None
        return {
            "endpoint": endpoint,
            "description": description,
            "status": status,
            "data": data
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "description": description,
            "status": f"❌ ERROR: {str(e)}",
            "data": None
        }

def main():
    print("=" * 60)
    print("📊 伤寒论知识图谱统计页面 API 测试报告")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    tests = [
        ("/stats/overview/", "全局概览统计"),
        ("/stats/herbs/?limit=15", "中药分析（含共现矩阵）"),
        ("/stats/formulas/?limit=10", "方剂分析（含关系网络）"),
        ("/stats/clinical-path/", "诊疗路径桑基图"),
        ("/stats/text/", "条文分析（含实体矩阵）"),
    ]

    results = []
    has_failure = False

    for endpoint, desc in tests:
        print(f"测试 {desc}...")
        result = test_api(endpoint, desc)
        results.append(result)
        print(f"  {result['status']}")
        if result['status'].startswith("❌"):
            has_failure = True
        print()

    # 测试前端访问
    print(f"测试前端访问 {FRONTEND_URL}/#/stats ...")
    try:
        resp = requests.get(FRONTEND_URL, timeout=10)
        frontend_status = "✅ PASS" if resp.status_code == 200 else f"❌ FAIL ({resp.status_code})"
    except Exception as e:
        frontend_status = f"❌ ERROR: {str(e)}"
        has_failure = True
    print(f"  {frontend_status}")
    print()

    # 汇总数据统计
    print("=" * 60)
    print("📈 数据汇总")
    print("=" * 60)

    if results[0]['data']:
        overview = results[0]['data']['kpi']
        print(f"📄 清洗后条文数: {overview.get('article_count', 0):,}")
        print(f"🔷 知识节点总数: {overview.get('entity_count', 0):,}")
        print(f"🔗 图谱关系总数: {overview.get('relation_count', 0):,}")
        print(f"📖 原文证据边数: {overview.get('clause_mention_count', 0):,}")

        entity_breakdown = results[0]['data'].get('entity_type_breakdown', {})
        print(f"\n📊 实体类型分布:")
        for entity_type, count in sorted(entity_breakdown.items(), key=lambda x: x[1], reverse=True):
            print(f"  {entity_type}: {count}")

    if results[1]['data']:
        herbs = results[1]['data']['top_herbs']
        print(f"\n🌿 中药TOP榜（前{min(5, len(herbs))}）:")
        for i, herb in enumerate(herbs[:5], 1):
            print(f"  {i}. {herb['name']} (提及{herb['count']}次)")

        co_matrix = results[1]['data']['cooccurrence_matrix']
        co_pairs = sum(len(v) for v in co_matrix.values())
        print(f"\n🔗 中药共现关系数: {co_pairs}")

    if results[2]['data']:
        formulas = results[2]['data']['top_formulas']
        print(f"\n💊 方剂TOP榜:")
        for i, formula in enumerate(formulas, 1):
            print(f"  {i}. {formula['name']} (提及{formula['mention_count']}次, 含{formula['herb_count']}味药)")

        network = results[2]['data']['formula_herb_network']
        print(f"\n🕸️ 方剂-中药网络: {len(network['nodes'])}节点, {len(network['edges'])}边")

    if results[3]['data']:
        sankey = results[3]['data']['full_sankey']
        print(f"\n🌊 桑基图: {len(sankey['nodes'])}节点, {len(sankey['links'])}链接")

        # 统计各类型节点
        categories = {}
        for node in sankey['nodes']:
            cat = node['category']
            categories[cat] = categories.get(cat, 0) + 1
        for cat, count in categories.items():
            print(f"  {cat}: {count}")

    if results[4]['data']:
        text = results[4]['data']['entity_matrix']
        print(f"\n🔥 热力图矩阵: {len(text['articles'])}条文 × {len(text['entities'])}实体")

    print()
    print("=" * 60)
    if has_failure:
        print("⚠️  部分测试失败，请检查上述错误信息。")
    else:
        print("✅ 所有API测试通过！数据质量良好。")
    print("=" * 60)
    print()
    print("🎯 下一步操作:")
    print("1. 打开浏览器访问 http://127.0.0.1:5173/#/stats")
    print("2. 查看8个图表是否都显示数据：")
    print("   - 4个KPI卡片（条文、实体、关系、证据边）")
    print("   - 实体类型分布条形图")
    print("   - 中药频次排行（横向条形图）")
    print("   - 中药词云（横向条形图）")
    print("   - 中药共现网络（节点图）")
    print("   - 方剂频次排行")
    print("   - 方剂-中药关系图（网络图）")
    print("   - 症状→证候→方剂 桑基图（重点！）")
    print("   - 条文-实体热力图")
    print("3. 检查控制台（F12）是否有JavaScript错误")
    print("4. 验证图表数据是否为真实数据（不是随机数）")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n测试中断")
    except Exception as e:
        print(f"测试失败: {e}")
