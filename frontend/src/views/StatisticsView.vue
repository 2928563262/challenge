<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

import {
  fetchClinicalPath,
  fetchFormulaAnalysis,
  fetchHerbAnalysis,
  fetchStatsOverview,
  fetchTextAnalysis,
} from "../services/api";
import type { ClinicalPath, FormulaAnalysis, HerbAnalysis, StatsOverview, TextAnalysis } from "../types/api";

const loading = ref(false);
const refreshing = ref(false);
const errorMessage = ref("");

const overview = ref<StatsOverview | null>(null);
const herbAnalysis = ref<HerbAnalysis | null>(null);
const formulaAnalysis = ref<FormulaAnalysis | null>(null);
const clinicalPath = ref<ClinicalPath | null>(null);
const textAnalysis = ref<TextAnalysis | null>(null);

const entityTypeZh: Record<string, string> = {
  SYNDROME: "证候",
  SYMPTOM: "症状",
  FORMULA: "方剂",
  HERB: "中药",
  THERAPY: "治法",
  ADMINISTRATION: "服法",
};

const relationTypeZh: Record<string, string> = {
  SYNDROME_HAS_SYMPTOM: "证候具有症状",
  SYNDROME_TO_FORMULA: "证候对应方剂",
  FORMULA_CONTAINS_HERB: "方剂包含中药",
  FORMULA_HAS_ADMINISTRATION: "方剂具有服法",
  NO_RELATION: "无稳定关系",
  SYNDROME_TO_THERAPY: "证候采用治法",
};

const entityTypeChartRef = ref<HTMLElement | null>(null);
const relationTypeChartRef = ref<HTMLElement | null>(null);
const herbTopChartRef = ref<HTMLElement | null>(null);
const formulaTopChartRef = ref<HTMLElement | null>(null);
const formulaHerbChartRef = ref<HTMLElement | null>(null);
const clinicalPathChartRef = ref<HTMLElement | null>(null);
const clauseLengthChartRef = ref<HTMLElement | null>(null);
const entityMatrixChartRef = ref<HTMLElement | null>(null);

type ChartKey =
  | "entityType"
  | "relationType"
  | "herbTop"
  | "formulaTop"
  | "formulaHerb"
  | "clinicalPath"
  | "clauseLength"
  | "entityMatrix";

const chartRefs: Record<ChartKey, typeof entityTypeChartRef> = {
  entityType: entityTypeChartRef,
  relationType: relationTypeChartRef,
  herbTop: herbTopChartRef,
  formulaTop: formulaTopChartRef,
  formulaHerb: formulaHerbChartRef,
  clinicalPath: clinicalPathChartRef,
  clauseLength: clauseLengthChartRef,
  entityMatrix: entityMatrixChartRef,
};

const charts: Partial<Record<ChartKey, echarts.ECharts>> = {};

const kpiCards = computed(() => {
  const kpi = overview.value?.kpi;
  return [
    { label: "条文数量", value: kpi?.article_count ?? 0 },
    { label: "实体节点", value: kpi?.entity_count ?? 0 },
    { label: "关系数量", value: kpi?.relation_count ?? 0 },
    { label: "原文提及", value: kpi?.clause_mention_count ?? 0 },
  ];
});

function buildNoDataOption(title: string): EChartsOption {
  return {
    title: {
      text: title,
      left: "center",
      top: "middle",
      textStyle: {
        color: "#8c7a66",
        fontSize: 14,
        fontWeight: 500,
      },
    },
    xAxis: { show: false, type: "category" },
    yAxis: { show: false, type: "value" },
    series: [],
  };
}

function ensureChart(key: ChartKey): echarts.ECharts | null {
  const el = chartRefs[key].value;
  if (!el) return null;
  if (!charts[key]) {
    charts[key] = echarts.init(el);
  }
  return charts[key] ?? null;
}

function renderEntityTypeChart() {
  const chart = ensureChart("entityType");
  if (!chart) return;
  const breakdown = overview.value?.entity_type_breakdown ?? {};
  const rows = Object.entries(breakdown)
    .map(([key, value]) => ({ name: entityTypeZh[key] ?? key, value }))
    .sort((a, b) => b.value - a.value);

  if (!rows.length) {
    chart.setOption(buildNoDataOption("暂无实体类型统计"), true);
    return;
  }

  chart.setOption(
    {
      tooltip: { trigger: "axis" },
      grid: { left: 48, right: 16, top: 16, bottom: 40 },
      xAxis: {
        type: "category",
        axisLabel: { color: "#5d4a38", interval: 0 },
        data: rows.map((row) => row.name),
      },
      yAxis: { type: "value", axisLabel: { color: "#6c553f" } },
      series: [
        {
          type: "bar",
          data: rows.map((row) => row.value),
          itemStyle: { color: "#7d4f2b", borderRadius: [6, 6, 0, 0] },
        },
      ],
    },
    true,
  );
}

function renderRelationTypeChart() {
  const chart = ensureChart("relationType");
  if (!chart) return;
  const breakdown = overview.value?.relation_type_breakdown ?? {};
  const rows = Object.entries(breakdown)
    .map(([key, value]) => ({ name: relationTypeZh[key] ?? key, value }))
    .sort((a, b) => b.value - a.value);

  if (!rows.length) {
    chart.setOption(buildNoDataOption("暂无关系类型统计"), true);
    return;
  }

  chart.setOption(
    {
      tooltip: { trigger: "item" },
      legend: {
        bottom: 0,
        textStyle: { color: "#5d4a38" },
      },
      series: [
        {
          type: "pie",
          radius: ["35%", "65%"],
          center: ["50%", "42%"],
          data: rows,
          label: { color: "#4f3d2b" },
        },
      ],
    },
    true,
  );
}

function renderHerbTopChart() {
  const chart = ensureChart("herbTop");
  if (!chart) return;
  const herbs = herbAnalysis.value?.top_herbs ?? [];
  if (!herbs.length) {
    chart.setOption(buildNoDataOption("暂无中药统计"), true);
    return;
  }
  const top = herbs.slice(0, 15);
  chart.setOption(
    {
      tooltip: { trigger: "axis" },
      grid: { left: 72, right: 16, top: 16, bottom: 24 },
      xAxis: { type: "value", axisLabel: { color: "#6c553f" } },
      yAxis: {
        type: "category",
        axisLabel: { color: "#5d4a38" },
        data: top.map((item) => item.name).reverse(),
      },
      series: [
        {
          type: "bar",
          data: top.map((item) => item.count).reverse(),
          itemStyle: { color: "#4f7c59", borderRadius: [0, 6, 6, 0] },
        },
      ],
    },
    true,
  );
}

function renderFormulaTopChart() {
  const chart = ensureChart("formulaTop");
  if (!chart) return;
  const formulas = formulaAnalysis.value?.top_formulas ?? [];
  if (!formulas.length) {
    chart.setOption(buildNoDataOption("暂无方剂统计"), true);
    return;
  }
  const top = formulas.slice(0, 12);
  chart.setOption(
    {
      tooltip: { trigger: "axis" },
      grid: { left: 52, right: 16, top: 16, bottom: 56 },
      xAxis: {
        type: "category",
        data: top.map((item) => item.name),
        axisLabel: { rotate: 25, color: "#5d4a38" },
      },
      yAxis: { type: "value", axisLabel: { color: "#6c553f" } },
      series: [
        {
          type: "bar",
          data: top.map((item) => item.mention_count),
          itemStyle: { color: "#9b6b34", borderRadius: [6, 6, 0, 0] },
        },
      ],
    },
    true,
  );
}

function renderFormulaHerbGraph() {
  const chart = ensureChart("formulaHerb");
  if (!chart) return;
  const network = formulaAnalysis.value?.formula_herb_network;
  if (!network || !network.nodes.length) {
    chart.setOption(buildNoDataOption("暂无方剂-药味网络"), true);
    return;
  }

  const nodes = network.nodes.map((node) => ({
    id: node.id,
    name: node.name,
    category: node.type === "formula" ? 0 : 1,
    symbolSize: node.type === "formula" ? 52 : 30,
    itemStyle: { color: node.type === "formula" ? "#8c5e34" : "#5b8c6a" },
  }));

  chart.setOption(
    {
      tooltip: { trigger: "item" },
      legend: [
        {
          bottom: 0,
          data: ["方剂", "中药"],
          textStyle: { color: "#5d4a38" },
        },
      ],
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          force: { repulsion: 240, edgeLength: [56, 140] },
          label: { show: true, color: "#2f2218", fontSize: 13 },
          data: nodes,
          links: network.edges.map((edge) => ({ source: edge.source, target: edge.target })),
          categories: [{ name: "方剂" }, { name: "中药" }],
          lineStyle: { opacity: 0.5, color: "#b89c7d" },
        },
      ],
    },
    true,
  );
}

function renderClinicalPathChart() {
  const chart = ensureChart("clinicalPath");
  if (!chart) return;
  const sankey = clinicalPath.value?.full_sankey;
  if (!sankey || !sankey.nodes.length || !sankey.links.length) {
    chart.setOption(buildNoDataOption("暂无临床路径数据"), true);
    return;
  }
  chart.setOption(
    {
      tooltip: { trigger: "item" },
      series: [
        {
          type: "sankey",
          data: sankey.nodes.map((node) => ({ name: node.name })),
          links: sankey.links.map((link) => ({
            source: link.source,
            target: link.target,
            value: link.value,
          })),
          top: "8%",
          bottom: "8%",
          nodeWidth: 18,
          nodeGap: 10,
          lineStyle: { color: "source", curveness: 0.5, opacity: 0.4 },
          label: { color: "#2f2218", fontSize: 11 },
        },
      ],
    },
    true,
  );
}

function renderClauseLengthChart() {
  const chart = ensureChart("clauseLength");
  if (!chart) return;
  const rows = (textAnalysis.value?.article_lengths ?? []).slice(0, 40);
  if (!rows.length) {
    chart.setOption(buildNoDataOption("暂无条文长度统计"), true);
    return;
  }
  chart.setOption(
    {
      tooltip: { trigger: "axis" },
      grid: { left: 52, right: 16, top: 16, bottom: 44 },
      xAxis: {
        type: "category",
        data: rows.map((item, idx) => `${idx + 1}`),
        axisLabel: { color: "#6c553f" },
      },
      yAxis: { type: "value", axisLabel: { color: "#6c553f" } },
      series: [
        {
          name: "长度",
          type: "line",
          smooth: true,
          data: rows.map((item) => item.length),
          lineStyle: { color: "#7d4f2b", width: 2 },
          itemStyle: { color: "#7d4f2b" },
        },
      ],
    },
    true,
  );
}

function renderEntityMatrixChart() {
  const chart = ensureChart("entityMatrix");
  if (!chart) return;
  const matrix = textAnalysis.value?.entity_matrix;
  if (!matrix || !matrix.articles.length || !matrix.entities.length) {
    chart.setOption(buildNoDataOption("暂无条文-实体矩阵"), true);
    return;
  }

  const heatData: [number, number, number][] = [];
  matrix.matrix.forEach((row, y) => {
    row.forEach((value, x) => {
      heatData.push([x, y, value]);
    });
  });
  const maxValue = Math.max(1, ...heatData.map((item) => item[2]));

  chart.setOption(
    {
      tooltip: {
        position: "top",
        formatter: (params: any) => {
          const [x, y, val] = params.data as [number, number, number];
          return `条文 ${matrix.articles[y]}<br/>实体 ${matrix.entities[x]}<br/>提及 ${val} 次`;
        },
      },
      grid: { left: 84, right: 94, top: 18, bottom: 92 },
      xAxis: {
        type: "category",
        data: matrix.entities,
        axisLabel: {
          rotate: 38,
          margin: 14,
          color: "#5d4a38",
          interval: 0,
          width: 72,
          overflow: "truncate",
        },
      },
      yAxis: {
        type: "category",
        data: matrix.articles.map((_, idx) => `${idx + 1}`),
        axisLabel: { color: "#6c553f" },
      },
      visualMap: {
        min: 0,
        max: maxValue,
        orient: "vertical",
        right: 10,
        top: "middle",
        calculable: true,
        inRange: {
          color: ["#f7efe2", "#d6b894", "#8c5e34"],
        },
        textStyle: { color: "#6c553f" },
      },
      series: [
        {
          type: "heatmap",
          data: heatData,
          label: { show: false },
          emphasis: {
            itemStyle: {
              shadowBlur: 8,
              shadowColor: "rgba(0, 0, 0, 0.2)",
            },
          },
        },
      ],
    },
    true,
  );
}

function renderAllCharts() {
  renderEntityTypeChart();
  renderRelationTypeChart();
  renderHerbTopChart();
  renderFormulaTopChart();
  renderFormulaHerbGraph();
  renderClinicalPathChart();
  renderClauseLengthChart();
  renderEntityMatrixChart();
}

function resizeCharts() {
  (Object.values(charts) as echarts.ECharts[]).forEach((chart) => chart?.resize());
}

async function loadAllStats(showLoading = true) {
  if (showLoading) loading.value = true;
  errorMessage.value = "";
  try {
    const [overviewPayload, herbPayload, formulaPayload, clinicalPayload, textPayload] = await Promise.all([
      fetchStatsOverview(),
      fetchHerbAnalysis(24),
      fetchFormulaAnalysis(24),
      fetchClinicalPath(),
      fetchTextAnalysis(),
    ]);
    overview.value = overviewPayload;
    herbAnalysis.value = herbPayload;
    formulaAnalysis.value = formulaPayload;
    clinicalPath.value = clinicalPayload;
    textAnalysis.value = textPayload;

    await nextTick();
    renderAllCharts();
  } catch (error) {
    console.error("Failed to load statistics:", error);
    errorMessage.value = "统计数据加载失败，请确认后端服务与图谱数据已就绪。";
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function refreshData() {
  refreshing.value = true;
  await loadAllStats(false);
}

onMounted(async () => {
  await loadAllStats(true);
  window.addEventListener("resize", resizeCharts);
});

onUnmounted(() => {
  window.removeEventListener("resize", resizeCharts);
  (Object.values(charts) as echarts.ECharts[]).forEach((chart) => chart?.dispose());
});
</script>

<template>
  <main class="page-shell statistics-page">
    <section class="panel stats-header">
      <div>
        <p class="panel-kicker">Statistics</p>
        <h1>图谱统计分析</h1>
        <p class="stats-subtitle">按当前激活图谱版本生成：实体、关系、路径和条文矩阵。</p>
      </div>
      <button class="ghost-button" :disabled="refreshing || loading" @click="refreshData">
        {{ refreshing ? "刷新中..." : "刷新统计" }}
      </button>
    </section>

    <p v-if="errorMessage" class="status-text error state-inline">{{ errorMessage }}</p>
    <p v-else-if="loading" class="status-text state-inline">正在加载统计图...</p>

    <section class="stats-kpi-grid">
      <article v-for="item in kpiCards" :key="item.label" class="kpi-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value.toLocaleString("zh-CN") }}</strong>
      </article>
    </section>

    <section class="stats-grid">
      <article class="panel chart-panel">
        <h3>实体类型分布</h3>
        <div ref="entityTypeChartRef" class="chart-host"></div>
      </article>
      <article class="panel chart-panel">
        <h3>关系类型分布</h3>
        <div ref="relationTypeChartRef" class="chart-host"></div>
      </article>
      <article class="panel chart-panel">
        <h3>中药频次 Top 15</h3>
        <div ref="herbTopChartRef" class="chart-host"></div>
      </article>
      <article class="panel chart-panel">
        <h3>方剂频次 Top 12</h3>
        <div ref="formulaTopChartRef" class="chart-host"></div>
      </article>
      <article class="panel chart-panel chart-panel-wide">
        <h3>方剂-药味网络</h3>
        <div ref="formulaHerbChartRef" class="chart-host chart-host-large"></div>
      </article>
      <article class="panel chart-panel chart-panel-wide">
        <h3>临床路径（症状 -> 证候 -> 方剂）</h3>
        <div ref="clinicalPathChartRef" class="chart-host chart-host-large"></div>
      </article>
      <article class="panel chart-panel">
        <h3>条文长度趋势</h3>
        <div ref="clauseLengthChartRef" class="chart-host"></div>
      </article>
      <article class="panel chart-panel">
        <h3>条文-实体热力矩阵</h3>
        <div ref="entityMatrixChartRef" class="chart-host chart-host-matrix"></div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.statistics-page {
  display: grid;
  gap: 16px;
}

.stats-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.stats-header h1 {
  margin: 4px 0 0;
}

.stats-subtitle {
  margin: 8px 0 0;
  color: #5d4a38;
}

.state-inline {
  margin: 0;
}

.stats-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi-card {
  border: 1px solid rgba(104, 76, 49, 0.12);
  background: rgba(255, 250, 243, 0.84);
  border-radius: 18px;
  padding: 14px 16px;
}

.kpi-card span {
  display: block;
  font-size: 0.8rem;
  color: #8c5e34;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.kpi-card strong {
  display: block;
  margin-top: 8px;
  font-size: 1.68rem;
  color: #2f2218;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.chart-panel {
  padding: 16px;
}

.chart-panel h3 {
  margin: 0 0 10px;
  font-size: 1.04rem;
}

.chart-panel-wide {
  grid-column: 1 / -1;
}

.chart-host {
  width: 100%;
  min-height: 320px;
}

.chart-host-large {
  min-height: 420px;
}

.chart-host-matrix {
  min-height: 380px;
}

@media (max-width: 1080px) {
  .stats-header {
    flex-direction: column;
  }

  .stats-kpi-grid,
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .chart-host-large {
    min-height: 360px;
  }

  .chart-host-matrix {
    min-height: 340px;
  }
}
</style>
