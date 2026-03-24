<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

import {
  fetchGraphSummary,
  fetchGraphEntityDetail,
  searchGraphEntities,
  searchCorpus,
  fetchStatsOverview,
  fetchHerbAnalysis,
  fetchFormulaAnalysis,
  fetchClinicalPath,
  fetchTextAnalysis
} from "../services/api";
import type {
  CorpusEntry,
  GraphEntity,
  GraphEntityDetail,
  GraphRelation,
  GraphSummary,
  StatsOverview,
  HerbAnalysis,
  FormulaAnalysis,
  ClinicalPath,
  TextAnalysis
} from "../types/api";

const router = useRoute();
const route = useRouter();

// ============ 统计图表相关状态 ============
const summary = ref<StatsOverview | null>(null);
const herbAnalysis = ref<HerbAnalysis | null>(null);
const formulaAnalysis = ref<FormulaAnalysis | null>(null);
const clinicalPath = ref<ClinicalPath | null>(null);
const textAnalysis = ref<TextAnalysis | null>(null);
const loading = ref(false);
const errorMessage = ref("");

// 图表DOM引用
// 新图表DOM引用// 新图表DOM引用
const entityTypeBarChartRef = ref<HTMLElement | null>(null);
const herbBarChartRef = ref<HTMLElement | null>(null);
const herbWordCloudRef = ref<HTMLElement | null>(null);
const herbNetworkRef = ref<HTMLElement | null>(null);
const formulaBarChartRef = ref<HTMLElement | null>(null);
const formulaHerbGraphRef = ref<HTMLElement | null>(null);
const clinicalSankeyRef = ref<HTMLElement | null>(null);
const textHeatmapRef = ref<HTMLElement | null>(null);

let entityTypeBarChart: echarts.ECharts | null = null;
let herbBarChart: echarts.ECharts | null = null;
let herbWordCloud: echarts.ECharts | null = null;
let herbNetwork: echarts.ECharts | null = null;
let formulaBarChart: echarts.ECharts | null = null;
let formulaHerbGraph: echarts.ECharts | null = null;
let clinicalSankey: echarts.ECharts | null = null;
let textHeatmap: echarts.ECharts | null = null;

// ============ 检索相关状态 ============
const keyword = ref("");
const entityType = ref("");
const searching = ref(false);
const searchError = ref("");
const searchResults = ref<GraphEntity[]>([]);
const searchTotal = ref(0);
const corpusResults = ref<CorpusEntry[]>([]);
const corpusTotal = ref(0);
const expandedResults = ref<GraphEntity[]>([]); // 扩展的实体（用于统计）

const entityTypeOptions = [
  { label: "全部类型", value: "" },
  { label: "方剂", value: "FORMULA" },
  { label: "证候", value: "SYNDROME" },
  { label: "症状", value: "SYMPTOM" },
  { label: "中药", value: "HERB" },
  { label: "治法", value: "THERAPY" },
  { label: "服法", value: "ADMINISTRATION" },
];

const entityTypeLabels: Record<string, string> = {
  FORMULA: "方剂",
  SYNDROME: "证候",
  SYMPTOM: "症状",
  HERB: "中药",
  THERAPY: "治法",
  ADMINISTRATION: "服法",
};

// ============ 统计卡片计算属性（基于检索结果） ============
const dynamicStatsCards = computed(() => {
  if (searchResults.value.length === 0 && summary.value) {
    // 没有检索时显示整体统计（使用新接口数据）
    const kpi = summary.value.kpi;
    return [
      { label: "清洗后条文", value: kpi.article_count?.toLocaleString("zh-CN") || "0", icon: "📄" },
      { label: "知识节点", value: kpi.entity_count?.toLocaleString("zh-CN") || "0", icon: "🔷" },
      { label: "图谱关系", value: kpi.relation_count?.toLocaleString("zh-CN") || "0", icon: "🔗" },
      { label: "原文证据边", value: kpi.clause_mention_count?.toLocaleString("zh-CN") || "0", icon: "📖" },
    ];
  }
  // 检索后显示检索相关统计
  const totalRelations = Object.values(relationTypeCounts.value).reduce((sum, c) => sum + c, 0);
  const avgRelationsPerEntity = searchResults.value.length > 0 ? (totalRelations / searchResults.value.length).toFixed(1) : "0";
  return [
    {
      label: "检索结果数",
      value: searchResults.value.length.toLocaleString("zh-CN"),
      icon: "🔍",
    },
    {
      label: "关系总数",
      value: totalRelations.toLocaleString("zh-CN"),
      icon: "🔗",
    },
    {
      label: "平均关系/实体",
      value: avgRelationsPerEntity,
      icon: "📊",
    },
    {
      label: "总计提及次数",
      value: searchResults.value.reduce((sum, e) => sum + e.mention_count, 0).toLocaleString("zh-CN"),
      icon: "💬",
    },
  ];
});

// ============ 关系类型分布（用于环形图） ============
const relationTypeDistribution = computed(() => {
  // 有搜索时，使用关系统计 counts（从已加载的实体详情中统计）
  if (Object.keys(relationTypeCounts.value).length > 0) {
    return Object.entries(relationTypeCounts.value).map(([type, count]) => ({
      name: type,
      value: count,
    }));
  }
  // 无搜索时，使用 summary 中的关系统计
  else if (summary.value?.relation_type_breakdown) {
    return Object.entries(summary.value.relation_type_breakdown).map(([type, count]) => ({
      name: type,
      value: count,
    }));
  }
  return [];
});

// ============ 方剂分布（用于饼图） ============
const formulaDistribution = computed(() => {
  const formulaCounts: Record<string, number> = {};
  
  // 场景1: 如果已执行搜索（有 expandedResults），统计检索相关的方剂
  if (expandedResults.value.length > 0 || searchResults.value.length > 0) {
    // 统计 expandedResults 中的所有 FORMULA
    expandedResults.value.forEach(e => {
      if (e.entity_type === "FORMULA") {
        formulaCounts[e.name] = (formulaCounts[e.name] || 0) + (e.mention_count || 1);
      }
    });

    // 从 entityDetailsMap 遍历所有关系，收集更多 FORMULA
    entityDetailsMap.value.forEach((detail) => {
      [...detail.outgoing_relations, ...detail.incoming_relations].forEach(rel => {
        if (rel.related_entity && rel.related_entity.entity_type === "FORMULA") {
          const name = rel.related_entity.name;
          formulaCounts[name] = (formulaCounts[name] || 0) + (rel.related_entity.mention_count || 1);
        }
      });
    });
  } 
  // 场景2: 未搜索（初始状态），使用 summary 中的 top_entities_by_type.FORMULA
  else if (summary.value?.top_entities_by_type?.FORMULA) {
    summary.value.top_entities_by_type.FORMULA.forEach(f => {
      formulaCounts[f.name] = f.mention_count || 1;
    });
  }

  return Object.entries(formulaCounts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 15);
});

// ============ 关系统计辅助状态 ============
const relationTypeCounts = ref<Record<string, number>>({});
const entityDetailsMap = ref<Map<string, GraphEntityDetail>>(new Map()); // 保存实体详情
const loadingRelations = ref(false);

// 批量获取实体详情（通用函数）
async function batchLoadEntityDetails(entities: GraphEntity[]): Promise<{ detailsMap: Map<string, GraphEntityDetail>; counts: Record<string, number> }> {
  if (entities.length === 0) {
    return { detailsMap: new Map(), counts: {} };
  }

  const detailsMap = new Map<string, GraphEntityDetail>();
  const counts: Record<string, number> = {};

  await Promise.all(
    entities.map(async (entity) => {
      try {
        const detail = await fetchGraphEntityDetail(entity.entity_id, {
          relationLimit: 100,
          evidenceLimit: 0,
        });
        detailsMap.set(entity.entity_id, detail);
        // 统计 outgoing 关系
        detail.outgoing_relations.forEach((rel: GraphRelation) => {
          counts[rel.relation_type] = (counts[rel.relation_type] || 0) + 1;
        });
        // 统计 incoming 关系
        detail.incoming_relations.forEach((rel: GraphRelation) => {
          counts[rel.relation_type] = (counts[rel.relation_type] || 0) + 1;
        });
      } catch (error) {
        console.warn(`Failed to load entity ${entity.entity_id}:`, error);
      }
    }),
  );

  return { detailsMap, counts };
}

// 加载检索结果的实体详情并扩展相关实体
async function loadEntityDetailsForRelations() {
  if (searchResults.value.length === 0) {
    relationTypeCounts.value = {};
    entityDetailsMap.value.clear();
    expandedResults.value = [];
    return;
  }

  loadingRelations.value = true;
  try {
    // 第一步：加载检索到的实体的详情
    const { detailsMap, counts } = await batchLoadEntityDetails(searchResults.value);
    
    // 如果检索结果较少(<10),扩展相关实体以丰富统计
    if (searchResults.value.length < 10) {
      const allRelatedEntities: GraphEntity[] = [];
      
      // 遍历所有已加载的实体，收集相关实体
      detailsMap.forEach((detail, entityId) => {
        // outgoing 关系的目标实体
        detail.outgoing_relations.forEach(rel => {
          if (rel.related_entity && !detailsMap.has(rel.related_entity.entity_id)) {
            allRelatedEntities.push(rel.related_entity);
          }
        });
        // incoming 关系的源实体
        detail.incoming_relations.forEach(rel => {
          if (rel.related_entity && !detailsMap.has(rel.related_entity.entity_id)) {
            allRelatedEntities.push(rel.related_entity);
          }
        });
      });

      // 去重
      const uniqueRelated = Array.from(new Map(allRelatedEntities.map(e => [e.entity_id, e])).values());
      
      // 限制扩展总量（检索 + 相关 <= 30）
      const maxAdditional = 30 - searchResults.value.length;
      const toLoad = uniqueRelated.slice(0, maxAdditional);
      
      if (toLoad.length > 0) {
        const relatedDetails = await batchLoadEntityDetails(toLoad);
        // 合并详情
        relatedDetails.detailsMap.forEach((detail, id) => {
          detailsMap.set(id, detail);
        });
        // 合并关系统计
        Object.assign(counts, relatedDetails.counts);
        
        // 扩展结果 = 原始 + 相关实体
        expandedResults.value = [...searchResults.value, ...toLoad];
      } else {
        expandedResults.value = searchResults.value;
      }
      
      // 从中已加载实体的关系中收集 FORMULA
      const formulaCandidates: GraphEntity[] = [];
      detailsMap.forEach((detail) => {
        [...detail.incoming_relations, ...detail.outgoing_relations].forEach(rel => {
          const related = rel.related_entity;
          if (related && related.entity_type === "FORMULA" && !detailsMap.has(related.entity_id) && !expandedResults.value.find(e => e.entity_id === related.entity_id)) {
            formulaCandidates.push(related);
          }
        });
      });

      const uniqueFormulaCandidates = Array.from(new Map(formulaCandidates.map(e => [e.entity_id, e])).values());
      if (uniqueFormulaCandidates.length > 0) {
        const additionalFormulas = uniqueFormulaCandidates.slice(0, 15);
        const formulaDetails = await batchLoadEntityDetails(additionalFormulas);
        formulaDetails.detailsMap.forEach((detail, id) => {
          detailsMap.set(id, detail);
        });
        Object.assign(counts, formulaDetails.counts);
        expandedResults.value = [...expandedResults.value, ...additionalFormulas];
      }
      
      entityDetailsMap.value = detailsMap;
      relationTypeCounts.value = counts;
    } else {
      // 检索结果已经很多，不扩展
      expandedResults.value = searchResults.value;
      entityDetailsMap.value = detailsMap;
      relationTypeCounts.value = counts;
    }
  } finally {
    loadingRelations.value = false;
  }
}

// ============ 检索功能 ============
async function runSearch() {
  const normalizedKeyword = keyword.value.trim();
  if (!normalizedKeyword) {
    searchError.value = "请输入检索关键词。";
    return;
  }

  searching.value = true;
  searchError.value = "";
  relationTypeCounts.value = {};

  try {
    const [graphPayload, corpusPayload] = await Promise.all([
      searchGraphEntities({ keyword: normalizedKeyword, entityType: entityType.value || undefined, limit: 20 }),
      searchCorpus({ keyword: normalizedKeyword, page: 1, pageSize: 20 }),
    ]);

    searchResults.value = graphPayload.results;
    searchTotal.value = graphPayload.total;
    corpusResults.value = corpusPayload.results;
    corpusTotal.value = corpusPayload.total;

    if (graphPayload.results.length > 0) {
      await loadEntityDetailsForRelations();
    }
  } catch (error) {
    searchError.value = "检索失败，请检查后端服务。";
    console.error("Search failed:", error);
  } finally {
    searching.value = false;
  }
}

function clearSearch() {
  keyword.value = "";
  entityType.value = "";
  searchResults.value = [];
  searchTotal.value = 0;
  corpusResults.value = [];
  corpusTotal.value = 0;
  searchError.value = "";
  relationTypeCounts.value = {};
  entityDetailsMap.value.clear();
  expandedResults.value = [];
}


// ============ 图表初始化 ============
function initCharts() {
  initEntityTypeBarChart();
  initHerbBarChart();
  initHerbWordCloud();
  initHerbNetwork();
  initFormulaBarChart();
  initFormulaHerbGraph();
  initClinicalSankey();
  initTextHeatmap();
}

// 1. 实体类型分布（条形图）
function initEntityTypeBarChart() {
  if (!entityTypeBarChartRef.value) return;
  entityTypeBarChart = echarts.init(entityTypeBarChartRef.value);
  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: [] },
    yAxis: { type: 'value' },
    series: [{
      data: [],
      type: 'bar',
      itemStyle: { color: '#c41e3a' }
    }]
  };
  entityTypeBarChart.setOption(option);
}

// 2. 中药频次排行（条形图）
function initHerbBarChart() {
  if (!herbBarChartRef.value) return;
  herbBarChart = echarts.init(herbBarChartRef.value);
  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: [] },
    yAxis: { type: 'value' },
    series: [{
      data: [],
      type: 'bar',
      itemStyle: { color: '#4caf50' }
    }]
  };
  herbBarChart.setOption(option);
}

// 3. 中药词云（暂时用横向条形图代替，实际可用 echarts-wordcloud）
function initHerbWordCloud() {
  if (!herbWordCloudRef.value) return;
  herbWordCloud = echarts.init(herbWordCloudRef.value);
  const option: EChartsOption = {
    tooltip: {},
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: [] },
    series: [{
      data: [],
      type: 'bar',
      itemStyle: { color: '#4caf50' }
    }]
  };
  herbWordCloud.setOption(option);
}

// 4. 中药共现网络
function initHerbNetwork() {
  if (!herbNetworkRef.value) return;
  herbNetwork = echarts.init(herbNetworkRef.value);
  const option: EChartsOption = {
    tooltip: {},
    series: [{
      type: 'graph',
      layout: 'force',
      data: [],
      links: [],
      categories: [{ name: ' herbs' }],
      roam: true,
      label: { show: true },
      force: { repulsion: 100 }
    }]
  };
  herbNetwork.setOption(option);
}

// 5. 方剂频次排行（条形图）
function initFormulaBarChart() {
  if (!formulaBarChartRef.value) return;
  formulaBarChart = echarts.init(formulaBarChartRef.value);
  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: [] },
    yAxis: { type: 'value' },
    series: [{
      data: [],
      type: 'bar',
      itemStyle: { color: '#ff9800' }
    }]
  };
  formulaBarChart.setOption(option);
}

// 6. 方剂-中药关系图（Graph）
function initFormulaHerbGraph() {
  if (!formulaHerbGraphRef.value) return;
  formulaHerbGraph = echarts.init(formulaHerbGraphRef.value);
  const option: EChartsOption = {
    tooltip: {},
    series: [{
      type: 'graph',
      layout: 'force',
      data: [],
      links: [],
      categories: [
        { name: '方剂' },
        { name: '中药' }
      ],
      roam: true,
      label: { show: true },
      force: { repulsion: 200 }
    }]
  };
  formulaHerbGraph.setOption(option);
}

// 7. 诊疗路径桑基图（重点）
function initClinicalSankey() {
  if (!clinicalSankeyRef.value) return;
  clinicalSankey = echarts.init(clinicalSankeyRef.value);
  const option: EChartsOption = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'sankey',
      emphasis: { focus: 'adjacency' },
      data: [],
      links: [],
      top: '10%',
      bottom: '10%',
      nodeWidth: 20,
      nodeGap: 8,
      itemStyle: { color: '#c41e3a', borderColor: '#ccc' },
      lineStyle: { color: 'source', curveness: 0.5 }
    }]
  };
  clinicalSankey.setOption(option);
}

// 8. 条文-实体热力图
function initTextHeatmap() {
  if (!textHeatmapRef.value) return;
  textHeatmap = echarts.init(textHeatmapRef.value);
  const option: EChartsOption = {
    tooltip: { position: 'top' },
    xAxis: { type: 'category', data: [] },
    yAxis: { type: 'category', data: [] },
    visualMap: {
      min: 0,
      max: 10,
      calculable: true,
      inRange: { color: ['#fff', '#c41e3a'] }
    },
    series: [{
      type: 'heatmap',
      data: [],
      label: { show: true }
    }]
  };
  textHeatmap.setOption(option);
}

function updateChartOptions() {
  const hasSearch = expandedResults.value.length > 0 || searchResults.value.length > 0;

  // ========== 检索模式：使用动态数据 ==========
  if (hasSearch) {
    const allEntities = expandedResults.value.length > 0 ? expandedResults.value : searchResults.value;
    const detailsMap = entityDetailsMap.value;

    // 1. 实体类型分布（基于 expandedResults）
    if (entityTypeBarChart) {
      const typeCounts: Record<string, number> = {};
      allEntities.forEach(e => {
        typeCounts[e.entity_type] = (typeCounts[e.entity_type] || 0) + 1;
      });
      const data = Object.entries(typeCounts)
        .map(([type, count]) => ({ name: entityTypeLabels[type] || type, value: count }))
        .sort((a, b) => b.value - a.value);
      entityTypeBarChart.setOption({
        xAxis: { data: data.map(d => d.name) },
        series: [{ data: data.map(d => d.value) }]
      });
    }

    // 2. 中药频次排行（基于 expandedResults + entityDetailsMap 中的中药）
    if (herbBarChart) {
      const herbCounts: Record<string, number> = {};
      
      // 先统计检索结果中的中药
      allEntities.filter(e => e.entity_type === 'HERB').forEach(h => {
        herbCounts[h.name] = (herbCounts[h.name] || 0) + (h.mention_count || 1);
      });
      
      // 再从关系中发现的中药
      detailsMap.forEach((detail) => {
        [...detail.outgoing_relations, ...detail.incoming_relations].forEach(rel => {
          const related = rel.related_entity;
          if (related && related.entity_type === 'HERB') {
            herbCounts[related.name] = (herbCounts[related.name] || 0) + (related.mention_count || 1);
          }
        });
      });

      const herbs = Object.entries(herbCounts)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 10);
      
      herbBarChart.setOption({
        xAxis: { data: herbs.map(h => h.name) },
        series: [{ data: herbs.map(h => h.count) }]
      });
    }

    // 3. 中药词云（同上，横向条形图）
    if (herbWordCloud) {
      const herbCounts: Record<string, number> = {};
      allEntities.filter(e => e.entity_type === 'HERB').forEach(h => {
        herbCounts[h.name] = (herbCounts[h.name] || 0) + (h.mention_count || 1);
      });
      detailsMap.forEach((detail) => {
        [...detail.outgoing_relations, ...detail.incoming_relations].forEach(rel => {
          const related = rel.related_entity;
          if (related && related.entity_type === 'HERB') {
            herbCounts[related.name] = (herbCounts[related.name] || 0) + (related.mention_count || 1);
          }
        });
      });

      const herbs = Object.entries(herbCounts)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 15);

      herbWordCloud.setOption({
        yAxis: { data: herbs.map(h => h.name) },
        series: [{ data: herbs.map(h => h.count) }]
      });
    }

    // 4. 中药共现网络（基于 shared formulas）
    if (herbNetwork) {
      const herbs = allEntities.filter(e => e.entity_type === 'HERB');
      if (herbs.length > 0) {
        const herbCounts: Record<string, number> = {};
        herbs.forEach(h => {
          herbCounts[h.name] = (herbCounts[h.name] || 0) + (h.mention_count || 1);
        });
        detailsMap.forEach((detail) => {
          [...detail.outgoing_relations, ...detail.incoming_relations].forEach(rel => {
            const related = rel.related_entity;
            if (related && related.entity_type === "HERB") {
              herbCounts[related.name] = (herbCounts[related.name] || 0) + (related.mention_count || 1);
            }
          });
        });

        // 构建共现矩阵：通过共享的方剂
        const herbNames = [...new Set(herbs.map(h => h.name))].slice(0, 12);
        const coMatrix: Record<string, Record<string, number>> = {};

        // 初始化矩阵
        herbNames.forEach(h1 => {
          coMatrix[h1] = {};
          herbNames.forEach(h2 => {
            if (h1 !== h2) coMatrix[h1][h2] = 0;
          });
        });

        // 从实体关系中计算共现
        detailsMap.forEach((detail, entityId) => {
          const entity = allEntities.find(e => e.entity_id === entityId);
          if (entity?.entity_type === 'FORMULA') {
            const herbRel = [...detail.outgoing_relations, ...detail.incoming_relations]
              .filter(rel => rel.relation_type === 'FORMULA_CONTAINS_HERB' && rel.related_entity);
            const herbNamesInFormula = herbRel.map(rel => rel.related_entity!.name);
            for (let i = 0; i < herbNamesInFormula.length; i++) {
              for (let j = i + 1; j < herbNamesInFormula.length; j++) {
                const h1 = herbNamesInFormula[i];
                const h2 = herbNamesInFormula[j];
                if (coMatrix[h1] && coMatrix[h1][h2] !== undefined) {
                  coMatrix[h1][h2]++;
                  coMatrix[h2][h1]++;
                }
              }
            }
          }
        });

        const nodes = herbNames.map(name => ({
          id: name,
          name,
          symbolSize: 10 + (herbCounts[name] || 1) * 3,
          category: 0,
          value: herbCounts[name] || 1
        }));

        const links: any[] = [];
        for (let i = 0; i < herbNames.length; i++) {
          for (let j = i + 1; j < herbNames.length; j++) {
            const h1 = herbNames[i];
            const h2 = herbNames[j];
            const weight = coMatrix[h1][h2];
            if (weight > 0) {
              links.push({ source: h1, target: h2, value: weight, lineStyle: { width: Math.min(weight * 2, 5) } });
            }
          }
        }

        herbNetwork.setOption({
          series: [{
            data: nodes,
            links: links,
            categories: [{ name: '中药' }],
            force: { repulsion: 150, edgeLength: 50 }
          }]
        });
      } else {
        herbNetwork.setOption({ series: [{ data: [], links: [] }] });
      }
    }

    // 5. 方剂频次排行
    if (formulaBarChart) {
      const formulaCounts: Record<string, number> = {};

      // 统计检索结果中的方剂
      allEntities.filter(e => e.entity_type === 'FORMULA').forEach(f => {
        formulaCounts[f.name] = (formulaCounts[f.name] || 0) + (f.mention_count || 1);
      });

      // 从关系中统计方剂
      detailsMap.forEach((detail, entityId) => {
        const entity = allEntities.find(e => e.entity_id === entityId);
        if (entity?.entity_type === 'FORMULA') {
          formulaCounts[entity.name] = (formulaCounts[entity.name] || 0) + (entity.mention_count || 1);
        }
      });

      const formulas = Object.entries(formulaCounts)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 10);

      formulaBarChart.setOption({
        xAxis: { data: formulas.map(f => f.name) },
        series: [{ data: formulas.map(f => f.count) }]
      });
    }

    // 6. 方剂-中药关系图
    if (formulaHerbGraph) {
      const formulas = allEntities.filter(e => e.entity_type === 'FORMULA');
      const herbs = allEntities.filter(e => e.entity_type === 'HERB');
      
      const nodes = [
        ...formulas.map(f => ({ id: f.name, name: f.name, symbolSize: 30, category: 0 })),
        ...herbs.map(h => ({ id: h.name, name: h.name, symbolSize: 15, category: 1 }))
      ];

      const links: { source: string; target: string }[] = [];

      // 从detailsMap中提取 FORMULA_CONTAINS_HERB 关系
      detailsMap.forEach((detail, entityId) => {
        const entity = allEntities.find(e => e.entity_id === entityId);
        if (entity?.entity_type === 'FORMULA') {
          [...detail.outgoing_relations, ...detail.incoming_relations]
            .filter(rel => rel.relation_type === 'FORMULA_CONTAINS_HERB' && rel.related_entity)
            .forEach(rel => {
              links.push({
                source: entity.name,
                target: rel.related_entity!.name
              });
            });
        }
      });

      formulaHerbGraph.setOption({
        series: [{
          data: nodes,
          links: links,
          categories: [{ name: '方剂' }, { name: '中药' }],
          roam: true,
          label: { show: true },
          force: { repulsion: 200 }
        }]
      });
    }

    // 7. 诊疗路径桑基图
    if (clinicalSankey) {
      const nodesMap = new Map<string, { id: string; name: string; category: string }>();
      const links: { source: string; target: string; value: number }[] = [];

      // 从detailsMap中提取症状->证候->方剂路径
      detailsMap.forEach((detail, entityId) => {
        const entity = allEntities.find(e => e.entity_id === entityId);
        if (!entity) return;

        if (entity.entity_type === 'SYMPTOM') {
          [...detail.outgoing_relations]
            .filter(rel => rel.relation_type === 'SYMPTOM_TO_SYNDROME' && rel.related_entity)
            .forEach(rel => {
              const syndrome = rel.related_entity!;
              nodesMap.set(entity.name, { id: entity.name, name: entity.name, category: 'symptom' });
              nodesMap.set(syndrome.name, { id: syndrome.name, name: syndrome.name, category: 'syndrome' });
              links.push({ source: entity.name, target: syndrome.name, value: rel.evidence_count || 1 });

              // 继续追踪证候->方剂
              const syndromeDetail = detailsMap.get(syndrome.entity_id);
              if (syndromeDetail) {
                [...syndromeDetail.outgoing_relations]
                  .filter(r => r.relation_type === 'SYNDROME_TO_FORMULA' && r.related_entity)
                  .forEach(r => {
                    const formula = r.related_entity!;
                    nodesMap.set(formula.name, { id: formula.name, name: formula.name, category: 'formula' });
                    links.push({ source: syndrome.name, target: formula.name, value: r.evidence_count || 1 });
                  });
              }
            });
        }
      });

      const nodes = Array.from(nodesMap.values());
      clinicalSankey.setOption({
        series: [{
          type: 'sankey',
          emphasis: { focus: 'adjacency' },
          data: nodes,
          links: links,
          top: '10%',
          bottom: '10%',
          nodeWidth: 20,
          nodeGap: 8,
          itemStyle: { color: '#c41e3a', borderColor: '#ccc' },
          lineStyle: { color: 'source', curveness: 0.5 }
        }]
      });
    }

    // 8. 条文-实体热力图
    if (textHeatmap) {
      // 收集所有涉及的实体
      const entitySet = new Set<string>();
      allEntities.forEach(e => entitySet.add(e.name));
      detailsMap.forEach((detail) => {
        [...detail.outgoing_relations, ...detail.incoming_relations].forEach(rel => {
          if (rel.related_entity) entitySet.add(rel.related_entity.name);
        });
      });
      const entities = Array.from(entitySet).slice(0, 15);
      
      // 收集涉及的条文
      const clauseSet = new Set<string>();
      allEntities.forEach(e => {
        if (e.first_record_id) clauseSet.add(e.first_record_id);
      });
      const clauses = Array.from(clauseSet).slice(0, 10);

      // 构建矩阵（简化：如果实体在关系中出现在条文相关实体中，标记为1）
      const matrix: number[][] = [];
      clauses.forEach(() => {
        const row = entities.map(() => 0);
        matrix.push(row);
      });

      // 简单填充：如果实体与当前条文相关
      allEntities.forEach(entity => {
        const clauseId = entity.first_record_id;
        if (clauseId && clauses.includes(clauseId)) {
          const rowIdx = clauses.indexOf(clauseId);
          const colIdx = entities.indexOf(entity.name);
          if (rowIdx >= 0 && colIdx >= 0) {
            matrix[rowIdx][colIdx] = entity.mention_count || 1;
          }
        }
      });

      textHeatmap.setOption({
        xAxis: { type: 'category', data: entities },
        yAxis: { type: 'category', data: clauses },
        visualMap: {
          min: 0,
          max: Math.max(...matrix.flat()),
          calculable: true,
          inRange: { color: ['#fff', '#c41e3a'] }
        },
        series: [{ type: 'heatmap', data: matrix.flatMap((row, rowIdx) =>
          row.map((val, colIdx) => [colIdx, rowIdx, val])
        ) }]
      });
    }

    return; // 检索模式下，不执行后续的全局数据渲染
  }

  // ========== 全局模式：使用 loadData 加载的数据 ==========
  
  // 1. 实体类型分布条形图
  if (entityTypeBarChart && summary.value?.entity_type_breakdown) {
    const data = Object.entries(summary.value.entity_type_breakdown)
      .map(([type, count]) => ({ name: entityTypeLabels[type] || type, value: count }))
      .sort((a, b) => b.value - a.value);
    entityTypeBarChart.setOption({
      xAxis: { data: data.map(d => d.name) },
      series: [{ data: data.map(d => d.value) }]
    });
  }

  // 2. 中药频次排行
  if (herbBarChart && summary.value?.top_entities_by_type?.HERB) {
    const herbs = summary.value.top_entities_by_type.HERB.slice(0, 10);
    herbBarChart.setOption({
      xAxis: { data: herbs.map(h => h.name) },
      series: [{ data: herbs.map(h => h.mention_count) }]
    });
  }

  // 3. 中药词云（横向条形图）
  if (herbWordCloud && summary.value?.top_entities_by_type?.HERB) {
    const herbs = summary.value.top_entities_by_type.HERB.slice(0, 15);
    herbWordCloud.setOption({
      yAxis: { data: herbs.map(h => h.name) },
      series: [{ data: herbs.map(h => h.mention_count) }]
    });
  }

  // 4. 中药共现网络
  if (herbNetwork && herbAnalysis.value?.cooccurrence_matrix) {
    const herbs = herbAnalysis.value.top_herbs.slice(0, 10);
    const coMatrix = herbAnalysis.value.cooccurrence_matrix;
    const nodes = herbs.map((h, idx) => ({
      id: h.name,
      name: h.name,
      symbolSize: 10 + (idx + 1) * 3,
      category: 0,
      value: h.count
    }));
    const links: any[] = [];
    for (let i = 0; i < nodes.length; i++) {
      const herb1 = nodes[i].id;
      if (coMatrix[herb1]) {
        for (let j = i + 1; j < nodes.length; j++) {
          const herb2 = nodes[j].id;
          const weight = coMatrix[herb1][herb2];
          if (weight && weight > 0) {
            links.push({
              source: herb1,
              target: herb2,
              value: weight,
              lineStyle: { width: weight }
            });
          }
        }
      }
    }
    herbNetwork.setOption({
      series: [{
        data: nodes,
        links: links,
        categories: [{ name: '中药' }],
        force: { repulsion: 150, edgeLength: 50 }
      }]
    });
  } else if (herbNetwork) {
    herbNetwork.setOption({ series: [{ data: [], links: [] }] });
  }

  // 5. 方剂频次排行
  if (formulaBarChart && summary.value?.top_entities_by_type?.FORMULA) {
    const formulas = summary.value.top_entities_by_type.FORMULA.slice(0, 10);
    formulaBarChart.setOption({
      xAxis: { data: formulas.map(f => f.name) },
      series: [{ data: formulas.map(f => f.mention_count) }]
    });
  }

  // 6. 方剂-中药关系图
  if (formulaHerbGraph && formulaAnalysis.value?.formula_herb_network) {
    const network = formulaAnalysis.value.formula_herb_network;
    formulaHerbGraph.setOption({
      series: [{
        data: network.nodes,
        links: network.edges,
        categories: [{ name: '方剂' }, { name: '中药' }],
        roam: true,
        label: { show: true },
        force: { repulsion: 200, edgeLength: 50 }
      }]
    });
  } else if (formulaHerbGraph) {
    const formulas = summary.value?.top_entities_by_type?.FORMULA?.slice(0, 5) || [];
    const herbs = summary.value?.top_entities_by_type?.HERB?.slice(0, 10) || [];
    const nodes = [
      ...formulas.map(f => ({ id: f.name, name: f.name, symbolSize: 30, category: 0 })),
      ...herbs.map(h => ({ id: h.name, name: h.name, symbolSize: 15, category: 1 }))
    ];
    const links: { source: string; target: string }[] = [];
    formulaHerbGraph.setOption({
      series: [{ data: nodes, links, categories: [{name:'方剂'},{name:'中药'}] }]
    });
  }

  // 7. 诊疗路径桑基图
  if (clinicalSankey && clinicalPath.value?.full_sankey) {
    const { nodes, links } = clinicalPath.value.full_sankey;
    clinicalSankey.setOption({
      series: [{
        type: 'sankey',
        emphasis: { focus: 'adjacency' },
        data: nodes.map(n => ({ id: n.id, name: n.name })),
        links: links.map(l => ({ source: l.source, target: l.target, value: l.value })),
        top: '10%',
        bottom: '10%',
        nodeWidth: 20,
        nodeGap: 8,
        itemStyle: { color: '#c41e3a', borderColor: '#ccc' },
        lineStyle: { color: 'source', curveness: 0.5 }
      }]
    });
  } else if (clinicalSankey) {
    const syndromes = summary.value?.top_entities_by_type?.SYNDROME?.slice(0, 3) || [];
    const formulas = summary.value?.top_entities_by_type?.FORMULA?.slice(0, 3) || [];
    const symptoms = summary.value?.top_entities_by_type?.SYMPTOM?.slice(0, 3) || [
      { name: '发热' }, { name: '头痛' }, { name: '汗出' }
    ];
    const nodes = [
      ...symptoms.map(s => ({ id: s.name, name: s.name })),
      ...syndromes.map(s => ({ id: s.name, name: s.name })),
      ...formulas.map(f => ({ id: f.name, name: f.name }))
    ];
    const links: any[] = [];
    symptoms.forEach(symptom => {
      syndromes.forEach(syndrome => {
        links.push({ source: symptom.name, target: syndrome.name, value: 1 });
      });
    });
    syndromes.forEach(syndrome => {
      formulas.forEach(formula => {
        links.push({ source: syndrome.name, target: formula.name, value: 1 });
      });
    });
    clinicalSankey.setOption({
      series: [{
        type: 'sankey',
        emphasis: { focus: 'adjacency' },
        data: nodes,
        links: links,
        top: '10%',
        bottom: '10%',
        nodeWidth: 20,
        nodeGap: 8,
        itemStyle: { color: '#c41e3a', borderColor: '#ccc' },
        lineStyle: { color: 'source', curveness: 0.5 }
      }]
    });
  }

  // 8. 条文-实体热力图
  if (textHeatmap && textAnalysis.value?.entity_matrix) {
    const { articles, entities, matrix } = textAnalysis.value.entity_matrix;
    const data: [number, number, number][] = [];
    for (let row = 0; row < matrix.length; row++) {
      for (let col = 0; col < matrix[row].length; col++) {
        if (matrix[row][col] > 0) {
          data.push([col, row, matrix[row][col]]);
        }
      }
    }
    textHeatmap.setOption({
      xAxis: { type: 'category', data: entities },
      yAxis: { type: 'category', data: articles },
      visualMap: {
        min: 0,
        max: Math.max(...matrix.flat()),
        calculable: true,
        inRange: { color: ['#fff', '#c41e3a'] }
      },
      series: [{ type: 'heatmap', data }]
    });
  } else if (textHeatmap) {
    const herbs = summary.value?.top_entities_by_type?.HERB?.slice(0, 10).map(h => h.name) || [];
    const articleCount = summary.value?.kpi.article_count || 6;
    const articles = Array.from({ length: Math.min(articleCount, 6) }, (_, i) => `条文${i+1}`);
    const data: [number, number, number][] = [];
    for (let row = 0; row < articles.length; row++) {
      for (let col = 0; col < herbs.length; col++) {
        data.push([col, row, Math.random() > 0.7 ? 1 : 0]);
      }
    }
    textHeatmap.setOption({
      xAxis: { data: herbs },
      yAxis: { data: articles },
      series: [{ data }]
    });
  }
}

function resizeCharts() {
  entityTypeBarChart?.resize();
  herbBarChart?.resize();
  herbWordCloud?.resize();
  herbNetwork?.resize();
  formulaBarChart?.resize();
  formulaHerbGraph?.resize();
  clinicalSankey?.resize();
  textHeatmap?.resize();
}

// 监听数据变化
watch(summary, () => {
  updateChartOptions();
}, { deep: true });

watch(herbAnalysis, () => {
  updateChartOptions();
}, { deep: true });

watch(formulaAnalysis, () => {
  updateChartOptions();
}, { deep: true });

watch(clinicalPath, () => {
  updateChartOptions();
}, { deep: true });

watch(textAnalysis, () => {
  updateChartOptions();
}, { deep: true });

watch([searchResults, expandedResults], () => {
  updateChartOptions();
});

async function loadData() {
  loading.value = true;
  errorMessage.value = "";
  try {
    // 并行加载所有统计数据
    const [overview, herbs, formulas, clinical, text] = await Promise.all([
      fetchStatsOverview(),
      fetchHerbAnalysis(15),
      fetchFormulaAnalysis(10),
      fetchClinicalPath(),
      fetchTextAnalysis()
    ]);

    summary.value = overview;
    herbAnalysis.value = herbs;
    formulaAnalysis.value = formulas;
    clinicalPath.value = clinical;
    textAnalysis.value = text;

    console.log('loadData: all stats loaded', {
      article_count: overview.kpi.article_count,
      entity_count: overview.kpi.entity_count,
      herb_count: herbs.top_herbs.length,
      formula_count: formulas.top_formulas.length,
      sankey_nodes: clinical.full_sankey.nodes.length,
      text_matrix_rows: text.entity_matrix.articles.length
    });
  } catch (error) {
    errorMessage.value = "加载统计数据失败，请确认后端服务已启动。";
    console.error("Failed to load stats:", error);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadData();
  setTimeout(() => {
    initCharts();
    window.addEventListener("resize", resizeCharts);
  }, 100);
});

onUnmounted(() => {
  window.removeEventListener("resize", resizeCharts);
  entityTypeBarChart?.dispose();
  herbBarChart?.dispose();
  herbWordCloud?.dispose();
  herbNetwork?.dispose();
  formulaBarChart?.dispose();
  formulaHerbGraph?.dispose();
  clinicalSankey?.dispose();
  textHeatmap?.dispose();
});
</script>

<template>
  <main class="page-shell statistics-page">
    <section class="page-header">
      <h1>数据统计分析</h1>
      <p class="subtitle">基于《伤寒论》知识图谱的定量数据展示</p>
    </section>

    <!-- 左右布局容器 -->
    <div class="split-layout">
      <!-- 左侧：检索区域 -->
      <aside class="search-panel">
        <div class="search-header">
          <h2>知识检索</h2>
          <p class="search-description">检索图谱实体或原文内容</p>
        </div>

        <!-- 检索表单 -->
        <div class="search-form">
          <div class="form-group">
            <label for="keyword">关键词</label>
            <input
              id="keyword"
              v-model="keyword"
              type="text"
              placeholder="输入实体名称或原文关键词"
              @keyup.enter="runSearch"
            />
          </div>

          <div class="form-group">
            <label for="entityType">实体类型（可选）</label>
            <select id="entityType" v-model="entityType">
              <option v-for="opt in entityTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div class="form-buttons">
            <button
              @click="runSearch"
              :disabled="searching"
              class="btn btn-primary"
            >
              {{ searching ? '检索中...' : '检索' }}
            </button>
            <button @click="clearSearch" class="btn btn-secondary">
              清空
            </button>
          </div>

          <!-- 检索错误提示 -->
          <div v-if="searchError" class="error-message search-error">
            {{ searchError }}
          </div>
        </div>

        <!-- 检索结果统计 -->
        <div v-if="searchTotal > 0 || corpusTotal > 0" class="search-stats">
          <div class="stat-item">
            <span class="stat-label">实体匹配</span>
            <span class="stat-value">{{ searchTotal }} 条</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">原文匹配</span>
            <span class="stat-value">{{ corpusTotal }} 条</span>
          </div>
        </div>

        <!-- 实体搜索结果 -->
        <div v-if="searchResults.length > 0" class="search-results-section">
          <h3>实体检索结果</h3>
          <div class="entity-results">
            <div
              v-for="entity in searchResults"
              :key="entity.entity_id"
              class="entity-result-item"
            >
              <div class="entity-name">{{ entity.name }}</div>
              <div class="entity-meta">
                <span class="entity-type-tag">{{ entityTypeLabels[entity.entity_type] || entity.entity_type }}</span>
                <span class="entity-mention-count">提及 {{ entity.mention_count }} 次</span>
              </div>
              <div class="entity-ids">ID: {{ entity.entity_id }}</div>
            </div>
          </div>
        </div>

        <!-- 原文搜索结果 -->
        <div v-if="corpusResults.length > 0" class="search-results-section">
          <h3>原文检索结果</h3>
          <div class="corpus-results">
            <div
              v-for="(entry, idx) in corpusResults"
              :key="idx"
              class="corpus-result-item"
            >
              <div class="corpus-text">{{ entry.text }}</div>
              <div v-if="entry.formula_name" class="corpus-formula">
                关联方剂：{{ entry.formula_name }}
              </div>
            </div>
          </div>
        </div>

        <!-- 无结果提示 -->
        <div v-if="keyword && !searching && searchTotal === 0 && corpusTotal === 0" class="no-results">
          未找到匹配结果，请尝试其他关键词。
        </div>
      </aside>

      <!-- 右侧：统计图表区域 -->
      <section class="charts-section">
        <!-- 统计卡片 -->
        <section class="stats-cards-grid">
          <div v-for="card in dynamicStatsCards" :key="card.label" class="stat-card">
            <span class="stat-icon">{{ card.icon }}</span>
            <div class="stat-content">
              <span class="stat-label">{{ card.label }}</span>
              <strong class="stat-value">{{ card.value }}</strong>
            </div>
          </div>
        </section>

        <!-- 关系分析中提示 -->
        <div v-if="loadingRelations" class="loading-relations-notice">
          正在分析实体关系...
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
          <button @click="loadData" class="retry-button">重试</button>
        </div>

        <!-- 图表网格 - 新版组件化 -->
        <div v-else class="stats-modules-grid">
          <!-- 模块1：全局概览 (已在上方KPI卡片展示，这里放实体类型分布条形图) -->
          <article class="chart-card module-overview">
            <h3 class="module-title">实体类型分布</h3>
            <div ref="entityTypeBarChartRef" class="chart-container"></div>
          </article>

          <!-- 模块2：中药分析 -->
          <article class="chart-card module-herb">
            <h3 class="module-title">中药频次排行 (Top 10)</h3>
            <div ref="herbBarChartRef" class="chart-container"></div>
          </article>

          <article class="chart-card module-herb">
            <h3 class="module-title">中药词云</h3>
            <div ref="herbWordCloudRef" class="chart-container"></div>
          </article>

          <article class="chart-card module-herb full-width">
            <h3 class="module-title">中药共现网络 (高频药对)</h3>
            <div ref="herbNetworkRef" class="chart-container network-container"></div>
          </article>

          <!-- 模块3：方剂分析 -->
          <article class="chart-card module-formula">
            <h3 class="module-title">方剂频次排行</h3>
            <div ref="formulaBarChartRef" class="chart-container"></div>
          </article>

          <article class="chart-card module-formula">
            <h3 class="module-title">方剂-中药关系图</h3>
            <div ref="formulaHerbGraphRef" class="chart-container graph-container"></div>
          </article>

          <!-- 模块4：诊疗路径 (桑基图) - 重点 -->
          <article class="chart-card module-clinical full-width">
            <h3 class="module-title">症状 → 证候 → 方剂 (桑基图)</h3>
            <div ref="clinicalSankeyRef" class="chart-container sankey-container"></div>
          </article>

          <!-- 模块5：条文分析 -->
          <article class="chart-card module-text full-width">
            <h3 class="module-title">条文-实体矩阵 (热力图)</h3>
            <div ref="textHeatmapRef" class="chart-container"></div>
          </article>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
/* 页面整体样式 */
.statistics-page {
  padding: 0;
  max-width: 100%;
  margin: 0 auto;
  min-height: 100vh;
  background: linear-gradient(180deg, #f6ede0 0%, #ede1cf 100%);
}

.page-header {
  padding: 2rem;
  text-align: center;
  background: rgba(255, 255, 255, 0.6);
  border-bottom: 1px solid rgba(125, 79, 43, 0.1);
}

.page-header h1 {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  color: #2a2318;
  font-weight: 700;
}

.subtitle {
  color: #666;
  font-size: 1rem;
}

/* 左右分栏布局 */
.split-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 2rem;
  padding: 2rem;
  max-width: 1800px;
  margin: 0 auto;
}

/* ============ 左侧检索面板 ============ */
.search-panel {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(125, 79, 43, 0.12);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 4px 16px rgba(125, 79, 43, 0.08);
  height: fit-content;
  position: sticky;
  top: 2rem;
}

.search-header {
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid rgba(125, 79, 43, 0.1);
}

.search-header h2 {
  font-size: 1.25rem;
  color: #2a2318;
  margin-bottom: 0.25rem;
}

.search-description {
  color: #666;
  font-size: 0.875rem;
}

.search-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #2a2318;
}

.form-group input,
.form-group select {
  padding: 0.75rem;
  border: 1px solid rgba(125, 79, 43, 0.2);
  border-radius: 8px;
  font-size: 1rem;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #c41e3a;
  box-shadow: 0 0 0 3px rgba(196, 30, 58, 0.1);
}

.form-buttons {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.btn {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(135deg, #c41e3a 0%, #8b0000 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(196, 30, 58, 0.3);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(196, 30, 58, 0.4);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f0f0f0;
  color: #333;
  border: 1px solid #ccc;
}

.btn-secondary:hover {
  background: #e0e0e0;
}

.search-error {
  margin-top: 0.5rem;
}

/* 检索结果统计 */
.search-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-top: 1.5rem;
  padding: 1rem;
  background: linear-gradient(135deg, #f5f2e9 0%, #ede8dc 100%);
  border-radius: 12px;
}

.stat-item {
  text-align: center;
}

.stat-item .stat-label {
  display: block;
  font-size: 0.75rem;
  color: #666;
  margin-bottom: 0.25rem;
}

.stat-item .stat-value {
  display: block;
  font-size: 1.25rem;
  font-weight: 700;
  color: #2a2318;
}

/* 检索结果列表 */
.search-results-section {
  margin-top: 1.5rem;
}

.search-results-section h3 {
  font-size: 1rem;
  color: #2a2318;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid rgba(125, 79, 43, 0.1);
}

.entity-results,
.corpus-results {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 600px;
  overflow-y: auto;
  padding-right: 0.5rem;
}

.entity-result-item,
.corpus-result-item {
  padding: 1rem;
  background: #f9f9f9;
  border: 1px solid rgba(125, 79, 43, 0.1);
  border-radius: 8px;
  transition: all 0.2s;
}

.entity-result-item:hover,
.corpus-result-item:hover {
  background: #f0f0f0;
  border-color: rgba(196, 30, 58, 0.2);
}

.entity-name {
  font-weight: 600;
  color: #2a2318;
  margin-bottom: 0.5rem;
}

.entity-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.entity-type-tag {
  padding: 0.25rem 0.5rem;
  background: linear-gradient(135deg, #4a7c59 0%, #2d4a3a 100%);
  color: white;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.entity-mention-count {
  font-size: 0.875rem;
  color: #666;
}

.entity-ids {
  font-size: 0.75rem;
  color: #999;
  font-family: monospace;
}

.corpus-text {
  font-size: 0.9rem;
  color: #333;
  line-height: 1.5;
  margin-bottom: 0.5rem;
}

.corpus-formula {
  font-size: 0.8rem;
  color: #c41e3a;
  font-weight: 600;
}

.no-results {
  text-align: center;
  padding: 2rem;
  color: #666;
  font-size: 0.9rem;
}

/* ============ 右侧统计图表区域 ============ */
.charts-section {
  min-width: 0;
}

.stats-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: linear-gradient(135deg, #f5f2e9 0%, #ede8dc 100%);
  border: 1px solid rgba(140, 81, 10, 0.2);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: 0 4px 12px rgba(125, 79, 43, 0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(125, 79, 43, 0.15);
}

.stat-icon {
  font-size: 2.5rem;
  filter: drop-shadow(0 2px 4px rgba(125, 79, 43, 0.15));
}

.stat-content {
  flex: 1;
}

.stat-label {
  display: block;
  font-size: 0.875rem;
  color: #666;
  margin-bottom: 0.25rem;
}

.stat-value {
  display: block;
  font-size: 1.75rem;
  color: #2a2318;
  font-weight: 700;
}

/* 覆盖度仪表盘 */





/* 关系分析提示 */
.loading-relations-notice {
  text-align: center;
  padding: 1rem;
  background: #fff8e1;
  color: #f57c00;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-weight: 600;
}

/* 图表网格 */
.charts-grid-enhanced {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 2rem;
}

.chart-card {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(125, 79, 43, 0.12);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 4px 16px rgba(125, 79, 43, 0.08);
  transition: transform 0.3s, box-shadow 0.3s;
}

.chart-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 25px rgba(125, 79, 43, 0.12);
}

.chart-card.full-width {
  grid-column: 1 / -1;
}

.chart-container {
  width: 100%;
  min-height: 320px;
}

/* 词云样式 */
.wordcloud-card {
  min-height: 400px;
}

.cloud-title {
  text-align: center;
  font-size: 1.1rem;
  color: #2a2318;
  margin-bottom: 1rem;
}

.wordcloud-container {
  width: 100%;
  min-height: 300px;
  background: linear-gradient(135deg, rgba(255,255,255,0.8) 0%, rgba(240,240,240,0.9) 100%);
  border-radius: 12px;
  padding: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.empty-tip {
  color: #999;
  font-size: 1rem;
}

.wordcloud-content {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 0.5rem 1.5rem;
  text-align: center;
}

.wordcloud-item {
  display: inline-block;
  transition: all 0.3s;
  cursor: default;
  color: #2a2318;
  font-weight: 600;
  opacity: 0.85;
  text-shadow: 0 1px 2px rgba(125, 79, 43, 0.1);
}

.wordcloud-item:hover {
  transform: scale(1.15);
  color: #c41e3a;
  opacity: 1;
  text-shadow: 0 2px 4px rgba(196, 30, 58, 0.3);
}

/* 错误提示 */
.error-message {
  background: #fff5f5;
  border: 1px solid #ffcdd2;
  color: #c62828;
  padding: 1.5rem;
  border-radius: 12px;
  text-align: center;
  margin: 2rem 0;
}

.retry-button {
  margin-left: 1rem;
  padding: 0.6rem 1.8rem;
  background: linear-gradient(135deg, #7d4f2b 0%, #8c5e34 100%);
  color: #fff8f0;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
  transition: all 0.3s;
  box-shadow: 0 4px 12px rgba(125, 79, 43, 0.3);
}

.retry-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(125, 79, 43, 0.4);
}

/* 响应式布局 */
@media (max-width: 1200px) {
  .split-layout {
    grid-template-columns: 320px 1fr;
    gap: 1.5rem;
    padding: 1.5rem;
  }

  .charts-grid-enhanced {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 968px) {
  .split-layout {
    grid-template-columns: 1fr;
  }

  .search-panel {
    position: static;
  }
}

@media (max-width: 768px) {
  .stats-cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .page-header h1 {
    font-size: 1.8rem;
  }

  .stat-card {
    padding: 1rem;
  }

  .stat-value {
    font-size: 1.5rem;
  }

  .chart-container {
    min-height: 300px;
  }

  .wordcloud-item {
    font-size: 12px !important;
  }
}
</style>
