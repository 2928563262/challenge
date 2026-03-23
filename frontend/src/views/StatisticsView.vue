<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

import { fetchGraphSummary } from "../services/api";
import type { GraphSummary } from "../types/api";

const router = useRouter();

const summary = ref<GraphSummary | null>(null);
const loading = ref(false);
const errorMessage = ref("");

// 图表DOM引用
const entityTypeChartRef = ref<HTMLElement | null>(null);
const topEntitiesChartRef = ref<HTMLElement | null>(null);
const relationTypeChartRef = ref<HTMLElement | null>(null);

let entityTypeChart: echarts.ECharts | null = null;
let topEntitiesChart: echarts.ECharts | null = null;
let relationTypeChart: echarts.ECharts | null = null;

const entityTypeLabels: Record<string, string> = {
  FORMULA: "方剂",
  SYNDROME: "证候",
  SYMPTOM: "症状",
  HERB: "中药",
  THERAPY: "治法",
  ADMINISTRATION: "服法",
};

// 统计卡片数据
const statsCards = computed(() => {
  if (!summary.value) return [];
  const s = summary.value;
  return [
    {
      label: "清洗后条文",
      value: s.input_record_count?.toLocaleString("zh-CN") || "0",
      icon: "📄",
    },
    {
      label: "知识节点",
      value: s.entity_node_count?.toLocaleString("zh-CN") || "0",
      icon: "🔷",
    },
    {
      label: "图谱关系",
      value: s.entity_relation_count?.toLocaleString("zh-CN") || "0",
      icon: "🔗",
    },
    {
      label: "原文证据边",
      value: s.clause_mention_count?.toLocaleString("zh-CN") || "0",
      icon: "📖",
    },
  ];
});

// 实体类型分布数据
const entityTypeData = computed(() => {
  if (!summary.value?.entity_type_breakdown) return [];
  return Object.entries(summary.value.entity_type_breakdown).map(([type, count]) => ({
    name: entityTypeLabels[type] || type,
    value: count,
  }));
});

// 关系类型分布数据
const relationTypeData = computed(() => {
  if (!summary.value?.relation_type_breakdown) return [];
  return Object.entries(summary.value.relation_type_breakdown)
    .map(([type, count]) => ({ name: type, value: count }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10); // 只展示前10种关系
});

// 高频实体数据
const topEntitiesData = computed(() => {
  if (!summary.value?.top_entities) return [];
  return summary.value.top_entities
    .map((entity) => ({
      name: entity.name,
      value: entity.mention_count,
      type: entityTypeLabels[entity.entity_type] || entity.entity_type,
    }))
    .slice(0, 10);
});

function initEntityTypeChart() {
  if (!entityTypeChartRef.value) return;
  entityTypeChart = echarts.init(entityTypeChartRef.value);
  const option: EChartsOption = {
    title: {
      text: "实体类型分布",
      left: "center",
      textStyle: { fontSize: 16 },
    },
    tooltip: {
      trigger: "item",
      formatter: "{a} <br/>{b}: {c} ({d}%)",
    },
    legend: {
      orient: "vertical",
      left: "left",
      top: "middle",
    },
    series: [
      {
        name: "实体类型",
        type: "pie",
        radius: ["40%", "70%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: "{b}: {d}%",
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: "bold",
          },
        },
        data: entityTypeData.value,
      },
    ],
  };
  entityTypeChart.setOption(option);
}

function initTopEntitiesChart() {
  if (!topEntitiesChartRef.value) return;
  topEntitiesChart = echarts.init(topEntitiesChartRef.value);
  const option: EChartsOption = {
    title: {
      text: "高频实体 TOP10",
      left: "center",
      textStyle: { fontSize: 16 },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
      formatter: (params: any) => {
        const item = params[0];
        return `${item.name} (${item.data.type})<br/>提及次数: ${item.value}`;
      },
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "3%",
      containLabel: true,
    },
    xAxis: {
      type: "value",
      name: "提及次数",
    },
    yAxis: {
      type: "category",
      data: topEntitiesData.value.map((item) => item.name),
      axisLabel: {
        interval: 0,
        fontSize: 12,
      },
    },
    series: [
      {
        name: "提及次数",
        type: "bar",
        data: topEntitiesData.value.map((item) => item.value),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: "#c41e3a" },
            { offset: 1, color: "#8b0000" },
          ]),
        },
        label: {
          show: true,
          position: "right",
          formatter: "{c}",
        },
      },
    ],
  };
  topEntitiesChart.setOption(option);
}

function initRelationTypeChart() {
  if (!relationTypeChartRef.value) return;
  relationTypeChart = echarts.init(relationTypeChartRef.value);
  const option: EChartsOption = {
    title: {
      text: "关系类型分布 (TOP10)",
      left: "center",
      textStyle: { fontSize: 16 },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "15%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: relationTypeData.value.map((item) => item.name),
      axisLabel: {
        rotate: 45,
        fontSize: 11,
      },
    },
    yAxis: {
      type: "value",
      name: "关系数量",
    },
    series: [
      {
        name: "关系数量",
        type: "bar",
        data: relationTypeData.value.map((item) => item.value),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "#4a7c59" },
            { offset: 1, color: "#2d4a3a" },
          ]),
        },
        label: {
          show: true,
          position: "top",
          formatter: "{c}",
        },
      },
    ],
  };
  relationTypeChart.setOption(option);
}

function initCharts() {
  initEntityTypeChart();
  initTopEntitiesChart();
  initRelationTypeChart();
}

function resizeCharts() {
  entityTypeChart?.resize();
  topEntitiesChart?.resize();
  relationTypeChart?.resize();
}

async function loadData() {
  loading.value = true;
  errorMessage.value = "";
  try {
    summary.value = await fetchGraphSummary();
  } catch (error) {
    errorMessage.value = "加载统计数据失败，请确认后端服务已启动。";
    console.error("Failed to load graph summary:", error);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadData();
  // 等待DOM更新后初始化图表
  setTimeout(() => {
    initCharts();
    window.addEventListener("resize", resizeCharts);
  }, 100);
});
</script>

<template>
  <main class="page-shell statistics-page">
    <section class="page-header">
      <h1>数据统计分析</h1>
      <p class="subtitle">基于《伤寒论》知识图谱的定量数据展示</p>
    </section>

    <!-- 统计卡片 -->
    <section class="stats-cards-grid">
      <div v-for="card in statsCards" :key="card.label" class="stat-card">
        <span class="stat-icon">{{ card.icon }}</span>
        <div class="stat-content">
          <span class="stat-label">{{ card.label }}</span>
          <strong class="stat-value">{{ card.value }}</strong>
        </div>
      </div>
    </section>

    <!-- 错误提示 -->
    <div v-if="errorMessage" class="error-message">
      {{ errorMessage }}
      <button @click="loadData" class="retry-button">重试</button>
    </div>

    <!-- 加载状态 -->
    <div v-else-if="loading" class="loading-state">
      正在加载数据...
    </div>

    <!-- 图表区域 -->
    <div v-else class="charts-grid">
      <!-- 实体类型分布 -->
      <article class="chart-card">
        <div ref="entityTypeChartRef" class="chart-container"></div>
      </article>

      <!-- 高频实体 TOP10 -->
      <article class="chart-card">
        <div ref="topEntitiesChartRef" class="chart-container"></div>
      </article>

      <!-- 关系类型分布 -->
      <article class="chart-card full-width">
        <div ref="relationTypeChartRef" class="chart-container" style="height: 400px;"></div>
      </article>
    </div>
  </main>
</template>

<style scoped>
.statistics-page {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 2rem;
  text-align: center;
}

.page-header h1 {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  color: #2d2d2d;
}

.subtitle {
  color: #666;
  font-size: 1rem;
}

.stats-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
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
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  font-size: 2.5rem;
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
  color: #2d2d2d;
  font-weight: 600;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
  gap: 1.5rem;
}

.chart-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.chart-card.full-width {
  grid-column: 1 / -1;
}

.chart-container {
  width: 100%;
  min-height: 350px;
}

.loading-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #666;
  font-size: 1.1rem;
}

.error-message {
  background: #fee;
  border: 1px solid #fcc;
  color: #c33;
  padding: 1rem;
  border-radius: 8px;
  text-align: center;
  margin: 2rem 0;
}

.retry-button {
  margin-left: 1rem;
  padding: 0.5rem 1.5rem;
  background: #c41e3a;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}

.retry-button:hover {
  background: #a01830;
}

@media (max-width: 768px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
  
  .stats-cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
