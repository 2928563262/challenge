<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

import { fetchGraphSummary, fetchGraphEntityDetail, searchGraphEntities, searchCorpus, fetchStatsOverview } from "../services/api";
import type { CorpusEntry, GraphEntity, GraphEntityDetail, GraphRelation, GraphSummary, StatsOverview } from "../types/api";

const router = useRoute();
const route = useRouter();

// ============ 统计图表相关状态 ============
const summary = ref<StatsOverview | null>(null);
const loading = ref(false);
const errorMessage = ref("");

// 图表DOM引用
const relationPieChartRef = ref<HTMLElement | null>(null);
const strengthChartRef = ref<HTMLElement | null>(null);
const formulaPieChartRef = ref<HTMLElement | null>(null);
const wordCloudRef = ref<HTMLElement | null>(null);

let relationPieChart: echarts.ECharts | null = null;
let strengthChart: echarts.ECharts | null = null;
let formulaPieChart: echarts.ECharts | null = null;

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

// ============ 实体关系强度（堆叠柱状图数据） ============
const entityRelationStrength = computed(() => {
  // 有搜索时，使用 expandedResults 中的实体
  if (expandedResults.value.length > 0) {
    return expandedResults.value.slice(0, 15).map(entity => {
      const detail = entityDetailsMap.value.get(entity.entity_id);
      const outgoingCount = detail?.outgoing_relations.length || 0;
      const incomingCount = detail?.incoming_relations.length || 0;
      
      return {
        name: entity.name.length > 12 ? entity.name.substring(0, 12) + "..." : entity.name,
        type: entityTypeLabels[entity.entity_type] || entity.entity_type,
        outgoing: outgoingCount,
        incoming: incomingCount,
      };
    });
  }
  // 无搜索时，使用 summary.top_entities 的整体数据（但没有详情，无法知道出边/入边数量）
  // 这种情况下返回空，图表可以不显示
  return [];
});

// ============ 词云数据 ============
const wordCloudData = computed(() => {
  if (expandedResults.value.length === 0) return [];
  const maxMention = Math.max(...expandedResults.value.map(e => e.mention_count), 1);
  return expandedResults.value.map(entity => ({
    name: entity.name,
    value: entity.mention_count,
    // 字体大小范围 14-40
    fontSize: 14 + ((entity.mention_count / maxMention) * 26),
  }));
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
      searchCorpus({ keyword: normalizedKeyword }),
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
function initRelationPieChart() {
  if (!relationPieChartRef.value) return;
  relationPieChart = echarts.init(relationPieChartRef.value);
  const option: EChartsOption = {
    title: { text: "关系类型分布", left: "center", textStyle: { fontSize: 16 } },
    tooltip: { trigger: "item", formatter: "{a} <br/>{b}: {c} ({d}%)" },
    legend: { 
      orient: "horizontal", 
      bottom: 0,
      left: "center",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { fontSize: 11 },
    },
    series: [
      {
        name: "关系类型",
        type: "pie",
        radius: ["30%", "60%"],
        center: ["50%", "45%"],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: "#fff", borderWidth: 2 },
        label: { show: true, formatter: "{b}: {d}%", fontSize: 11 },
        emphasis: { label: { show: true, fontSize: 13, fontWeight: "bold" } },
        data: [],
      },
    ],
  };
  relationPieChart.setOption(option);
}

function initStrengthChart() {
  if (!strengthChartRef.value) return;
  strengthChart = echarts.init(strengthChartRef.value);
  const option: EChartsOption = {
    title: { text: "实体关系强度", left: "center", textStyle: { fontSize: 16 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { data: ["出边", "入边"], top: "bottom" },
    grid: { left: "3%", right: "4%", bottom: "15%", containLabel: true },
    xAxis: { type: "category", data: [], axisLabel: { rotate: 45, fontSize: 11 } },
    yAxis: { type: "value", name: "关系数量" },
    series: [
      { name: "出边", type: "bar", stack: "total", itemStyle: { color: "#c41e3a" }, data: [] },
      { name: "入边", type: "bar", stack: "total", itemStyle: { color: "#4a7c59" }, data: [] },
    ],
  };
  strengthChart.setOption(option);
}


function initFormulaPieChart() {
  if (!formulaPieChartRef.value) return;
  formulaPieChart = echarts.init(formulaPieChartRef.value);
  const option: EChartsOption = {
    title: { text: "关联方剂分布", left: "center", textStyle: { fontSize: 16 } },
    tooltip: { trigger: "item", formatter: "{a} <br/>{b}: {c} 条原文 ({d}%)" },
    legend: {
      orient: "horizontal",
      bottom: 0,
      left: "center",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { fontSize: 11 },
    },
    series: [
      {
        name: "方剂",
        type: "pie",
        radius: ["30%", "60%"],
        center: ["50%", "45%"],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: "#fff", borderWidth: 2 },
        label: { show: true, formatter: "{b}: {d}%", fontSize: 11 },
        emphasis: { label: { show: true, fontSize: 13, fontWeight: "bold" } },
        data: [],
      },
    ],
  };
  formulaPieChart.setOption(option);
}

function initCharts() {
  initFormulaPieChart();
  initRelationPieChart();
  initStrengthChart();
}

function updateChartOptions() {
  console.log('updateChartOptions called', {
    relationTypeDistribution: relationTypeDistribution.value.length,
    entityRelationStrength: entityRelationStrength.value.length,
    formulaDistribution: formulaDistribution.value.length
  });
  
  // 更新环形图（关系类型分布）
  if (relationPieChart) {
    relationPieChart.setOption({
      series: [{ data: relationTypeDistribution.value }],
    });
    console.log('relationPieChart updated with', relationTypeDistribution.value.length, 'items');
  }

  // 更新堆叠柱状图（实体关系强度）
  if (strengthChart) {
    strengthChart.setOption({
      xAxis: { data: entityRelationStrength.value.map((item) => item.name) },
      series: [
        { data: entityRelationStrength.value.map((item) => item.outgoing) },
        { data: entityRelationStrength.value.map((item) => item.incoming) },
      ],
    });
    console.log('strengthChart updated with', entityRelationStrength.value.length, 'items');
  }

  // 更新饼图（方剂分布）
  if (formulaPieChart) {
    formulaPieChart.setOption({
      series: [{ data: formulaDistribution.value }],
    });
    console.log('formulaPieChart updated with', formulaDistribution.value.length, 'items');
  }
}

function resizeCharts() {
  relationPieChart?.resize();
  strengthChart?.resize();
  formulaPieChart?.resize();
}

// 监听数据变化
watch([relationTypeDistribution, entityRelationStrength, formulaDistribution], () => {
  updateChartOptions();
}, { deep: true });

async function loadData() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const data = await fetchStatsOverview();
    summary.value = data;
    console.log('loadData: stats overview loaded', {
      article_count: data.kpi.article_count,
      entity_count: data.kpi.entity_count,
      relation_count: data.kpi.relation_count,
      top_formulas: data.top_entities_by_type?.FORMULA?.map((f: any) => f.name) || []
    });
  } catch (error) {
    errorMessage.value = "加载统计数据失败，请确认后端服务已启动。";
    console.error("Failed to load stats overview:", error);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    await loadData();
    setTimeout(() => {
      try {
        initCharts();
      } catch (e) {
        console.error("initCharts failed:", e);
        errorMessage.value = "图表初始化失败: " + e;
      }
      window.addEventListener("resize", resizeCharts);
    }, 100);
  } catch (e) {
    console.error("StatisticsView onMounted failed:", e);
    errorMessage.value = "页面加载失败: " + e;
  }
});

onUnmounted(() => {
  window.removeEventListener("resize", resizeCharts);
  relationPieChart?.dispose();
  strengthChart?.dispose();
  formulaPieChart?.dispose();
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

        <!-- 图表网格 -->
        <div v-else class="charts-grid-enhanced">
          <!-- 关系类型分布（环形图） -->
          <article class="chart-card">
            <div ref="relationPieChartRef" class="chart-container"></div>
          </article>

          <!-- 实体关系强度（堆叠柱状图） -->
          <article class="chart-card">
            <div ref="strengthChartRef" class="chart-container"></div>
          </article>

          <!-- 实体词云 -->

          <!-- 关联方剂分布 -->
          <article class="chart-card">
            <div ref="formulaPieChartRef" class="chart-container"></div>
          </article>


          <article class="chart-card full-width wordcloud-card">
            <h3 class="cloud-title">实体词云（按提及次数）</h3>
            <div ref="wordCloudRef" class="wordcloud-container">
              <div v-if="wordCloudData.length === 0" class="empty-tip">暂无数据</div>
              <div v-else class="wordcloud-content">
                <span
                  v-for="item in wordCloudData"
                  :key="item.name"
                  class="wordcloud-item"
                  :style="{ fontSize: item.fontSize + 'px' }"
                  :title="`${item.name}: ${item.value}次提及`"
                >
                  {{ item.name }}
                </span>
              </div>
            </div>
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