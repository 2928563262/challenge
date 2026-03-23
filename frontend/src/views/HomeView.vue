<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import axios from "axios";

import { formatEntityTypeLabel } from "../i18n";
import { activateGraphVersion, fetchGraphRegistry, fetchGraphShowcase, fetchGraphSummary, fetchModelSummary, fetchOverview, refreshReviewedGraph } from "../services/api";
import type { CorpusOverview, GraphEntity, GraphRegistryStatus, GraphShowcaseCase, GraphSummary, GraphVersionRecord, ModelSummary } from "../types/api";

const router = useRouter();
const { t } = useI18n();

const overview = ref<CorpusOverview | null>(null);
const graphSummary = ref<GraphSummary | null>(null);
const showcaseCases = ref<GraphShowcaseCase[]>([]);
const graphRegistry = ref<GraphRegistryStatus | null>(null);
const modelSummary = ref<ModelSummary | null>(null);

const loadingOverview = ref(false);
const loadingGraphSummary = ref(false);
const loadingShowcase = ref(false);
const loadingGraphRegistry = ref(false);
const loadingModelSummary = ref(false);
const refreshingReviewedGraph = ref(false);
const activatingGraphId = ref("");

const overviewError = ref("");
const graphError = ref("");
const showcaseError = ref("");
const modelError = ref("");
const graphActionMessage = ref("");

const heroStats = computed(() => {
  if (!graphSummary.value || !overview.value) {
    return [];
  }

  return [
    { label: "清洗后条文", value: graphSummary.value.input_record_count.toLocaleString("zh-CN") },
    { label: "知识节点", value: graphSummary.value.entity_node_count.toLocaleString("zh-CN") },
    { label: "图谱关系", value: graphSummary.value.entity_relation_count.toLocaleString("zh-CN") },
    { label: "原文证据边", value: graphSummary.value.clause_mention_count.toLocaleString("zh-CN") },
  ];
});

const typeBreakdown = computed(() => Object.entries(graphSummary.value?.entity_type_breakdown ?? {}));
const topEntities = computed(() => graphSummary.value?.top_entities ?? []);
const formulaSamples = computed(() => overview.value?.formula_samples.slice(0, 6) ?? []);
const graphVersion = computed(() => graphSummary.value?.graph_version ?? null);
const graphVersions = computed(() => graphRegistry.value?.versions ?? []);
const systemStatusCards = computed(() => {
  if (!modelSummary.value || !graphVersion.value) {
    return [];
  }

  const acceptedCount = Number((modelSummary.value.accepted_pipeline.accepted_report.data as Record<string, any> | null)?.stats?.record_count ?? 0);
  const acceptedUpdatedAt = modelSummary.value.accepted_pipeline.accepted_report.updated_at;

  return [
    {
      label: "默认 NER 模型",
      value: modelSummary.value.registry.active.ner.run_name,
      meta: `${formatDatasetSource(modelSummary.value.registry.active.ner.dataset_source)} · ${formatModelMetric(modelSummary.value.registry.active.ner)}`,
    },
    {
      label: "默认 RE 模型",
      value: modelSummary.value.registry.active.relation.run_name,
      meta: `${formatDatasetSource(modelSummary.value.registry.active.relation.dataset_source)} · ${formatModelMetric(modelSummary.value.registry.active.relation)}`,
    },
    {
      label: "默认图谱版本",
      value: graphVersion.value.run_name,
      meta: `${formatGraphSource(graphVersion.value.source_type)} · ${formatGraphMetric(graphVersion.value)}`,
    },
    {
      label: "已采纳记录",
      value: `${acceptedCount} 条`,
      meta: `最近更新 ${formatUnixTimestamp(acceptedUpdatedAt)}`,
    },
  ];
});

function formatEntityType(entityTypeName: string) {
  return formatEntityTypeLabel(entityTypeName);
}

function formatGraphSource(sourceType: string) {
  if (sourceType === "accepted_reviewed") {
    return "已复核记录";
  }
  if (sourceType === "cleaned_silver") {
    return "清洗银标准";
  }
  return "自定义导出";
}

function formatDateTime(value: string) {
  if (!value) {
    return "未记录";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatUnixTimestamp(value: number | null) {
  if (!value) {
    return "未记录";
  }
  return new Date(value * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatDatasetSource(source: string) {
  if (source === "merged") {
    return "合并训练集";
  }
  if (source === "incremental") {
    return "增量数据";
  }
  return "基础训练集";
}

function formatModelMetric(record: ModelSummary["registry"]["active"]["ner"] | ModelSummary["registry"]["active"]["relation"]) {
  if (record.task === "ner") {
    const f1 = record.validation_metrics.eval_f1 ?? record.validation_metrics.f1;
    return typeof f1 === "number" ? `验证 F1 ${f1.toFixed(4)}` : "验证指标未记录";
  }
  const macroF1 = record.validation_metrics.eval_macro_f1 ?? record.validation_metrics.macro_f1;
  return typeof macroF1 === "number" ? `验证 Macro-F1 ${macroF1.toFixed(4)}` : "验证指标未记录";
}

function formatGraphMetric(record: GraphVersionRecord) {
  const entityCount = Number(record.stats.entity_node_count ?? 0);
  const relationCount = Number(record.stats.entity_relation_count ?? 0);
  return `节点 ${entityCount} · 关系 ${relationCount}`;
}

function openExplorer(entity: GraphEntity) {
  router.push({
    name: "explore",
    query: {
      keyword: entity.name,
      entityType: entity.entity_type,
      entityId: entity.entity_id,
    },
  });
}

function openCase(caseItem: GraphShowcaseCase) {
  openExplorer(caseItem.entity);
}

async function loadOverview() {
  loadingOverview.value = true;
  overviewError.value = "";
  try {
    overview.value = await fetchOverview();
  } catch {
    overviewError.value = "文本概览加载失败，请确认 Django 服务已经启动。";
  } finally {
    loadingOverview.value = false;
  }
}

async function loadGraphSummary() {
  loadingGraphSummary.value = true;
  graphError.value = "";
  try {
    graphSummary.value = await fetchGraphSummary();
  } catch {
    graphError.value = "图谱摘要加载失败，请确认图谱接口可访问。";
  } finally {
    loadingGraphSummary.value = false;
  }
}

async function loadGraphRegistry() {
  loadingGraphRegistry.value = true;
  try {
    graphRegistry.value = await fetchGraphRegistry();
  } catch {
    graphError.value = "图谱版本列表加载失败，请确认图谱接口可访问。";
  } finally {
    loadingGraphRegistry.value = false;
  }
}

async function loadModelSummary() {
  loadingModelSummary.value = true;
  modelError.value = "";
  try {
    modelSummary.value = await fetchModelSummary();
  } catch {
    modelError.value = "模型状态加载失败，请确认模型接口可访问。";
  } finally {
    loadingModelSummary.value = false;
  }
}

async function runReviewedGraphRefresh() {
  refreshingReviewedGraph.value = true;
  graphError.value = "";
  graphActionMessage.value = "";
  try {
    const payload = await refreshReviewedGraph();
    graphSummary.value = payload.graph_summary;
    graphRegistry.value = payload.registry;
    graphActionMessage.value = `已根据复核记录刷新图谱，当前版本：${payload.registry.active.run_name}`;
    await loadShowcase();
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      graphError.value = String(error.response?.data?.detail || "复核图谱刷新失败。");
    } else {
      graphError.value = "复核图谱刷新失败。";
    }
  } finally {
    refreshingReviewedGraph.value = false;
  }
}

async function runGraphActivation(graphId: string) {
  activatingGraphId.value = graphId;
  graphError.value = "";
  graphActionMessage.value = "";
  try {
    const payload = await activateGraphVersion(graphId);
    graphRegistry.value = payload.registry;
    await Promise.all([loadGraphSummary(), loadShowcase()]);
    graphActionMessage.value = `已切换当前图谱版本：${payload.record.run_name}`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      graphError.value = String(error.response?.data?.detail || "图谱版本切换失败。");
    } else {
      graphError.value = "图谱版本切换失败。";
    }
  } finally {
    activatingGraphId.value = "";
  }
}

async function loadShowcase() {
  loadingShowcase.value = true;
  showcaseError.value = "";
  try {
    const payload = await fetchGraphShowcase();
    showcaseCases.value = payload.cases;
  } catch {
    showcaseError.value = "典型案例加载失败，请检查图谱接口。";
  } finally {
    loadingShowcase.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadOverview(), loadGraphSummary(), loadShowcase(), loadGraphRegistry(), loadModelSummary()]);
});
</script>

<template>
  <main class="page-shell knowledge-page home-dashboard">
    <section class="hero-panel hero-grid">
      <div class="hero-copy">
        <p class="eyebrow">{{ t("home.heroKicker") }}</p>
        <h1>围绕《伤寒论》做一个可检索、可建图、可展示、可答辩的最小闭环系统。</h1>
        <p class="hero-description">
          首页负责给出项目全貌、核心统计和典型案例入口；图谱浏览页负责实体检索、关系网络概览和原文证据回溯。
        </p>
        <div class="cta-row">
          <RouterLink to="/explore" class="primary-link-button">进入图谱浏览</RouterLink>
          <button class="ghost-button" type="button" @click="loadGraphSummary" :disabled="loadingGraphSummary">
            {{ loadingGraphSummary ? t("common.refreshing") : t("common.refreshGraphSummary") }}
          </button>
          <button class="ghost-button" type="button" @click="runReviewedGraphRefresh" :disabled="refreshingReviewedGraph">
            {{ refreshingReviewedGraph ? "刷新复核图谱中..." : "用复核记录刷新图谱" }}
          </button>
        </div>
      </div>

      <div class="hero-side showcase-card">
        <div class="showcase-block">
          <span>当前主线</span>
          <strong>文本清洗 → 图谱导入 → 查询展示</strong>
          <p>这一版优先把系统主链路跑稳，再继续扩展模型训练和更复杂的语义抽取。</p>
        </div>
        <div v-if="graphVersion" class="showcase-block">
          <span>当前图谱版本</span>
          <strong>{{ graphVersion.run_name }}</strong>
          <p>{{ formatGraphSource(graphVersion.source_type) }} · 更新时间 {{ formatDateTime(graphVersion.updated_at) }}</p>
        </div>
      </div>
    </section>

    <p v-if="graphActionMessage" class="status-text">{{ graphActionMessage }}</p>

    <section class="stats-grid hero-stats">
      <article v-for="item in heroStats" :key="item.label" class="stat-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <section class="panel showcase-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">系统状态</p>
          <h2>当前运行总览</h2>
        </div>
      </div>

      <p v-if="modelError" class="status-text error">{{ modelError }}</p>
      <p v-else-if="loadingModelSummary" class="status-text">正在加载系统状态...</p>
      <div v-else class="stats-grid hero-stats system-status-grid">
        <article v-for="item in systemStatusCards" :key="item.label" class="stat-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <p>{{ item.meta }}</p>
        </article>
      </div>
    </section>

    <section class="panel showcase-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">{{ t("home.showcaseKicker") }}</p>
          <h2>典型案例入口</h2>
        </div>
        <RouterLink to="/explore" class="ghost-link">查看全部图谱细节</RouterLink>
      </div>

      <p v-if="showcaseError" class="status-text error">{{ showcaseError }}</p>
      <p v-else-if="loadingShowcase" class="status-text">正在加载典型案例...</p>
      <div v-else class="showcase-grid">
        <button
          v-for="caseItem in showcaseCases"
          :key="caseItem.slug"
          type="button"
          class="showcase-case-card"
          @click="openCase(caseItem)"
        >
          <div class="showcase-case-head">
            <div>
              <p class="entity-type-tag">{{ caseItem.focus }}</p>
              <h3>{{ caseItem.title }}</h3>
            </div>
            <span>{{ caseItem.entity.name }}</span>
          </div>
          <p>{{ caseItem.description }}</p>
          <div class="case-highlight-list">
            <div v-for="highlight in caseItem.highlights" :key="highlight" class="case-highlight-item">
              {{ highlight }}
            </div>
          </div>
        </button>
      </div>
    </section>

    <section class="content-grid dashboard-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("home.snapshotKicker") }}</p>
            <h2>图谱类型分布</h2>
          </div>
        </div>

        <p v-if="graphError" class="status-text error">{{ graphError }}</p>
        <div v-else class="breakdown-list">
          <div v-for="([type, count]) in typeBreakdown" :key="type" class="breakdown-item">
            <span>{{ formatEntityType(type) }}</span>
            <strong>{{ count }}</strong>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("home.topEntitiesKicker") }}</p>
            <h2>高频知识节点</h2>
          </div>
        </div>

        <div class="top-entity-grid">
          <button
            v-for="entity in topEntities"
            :key="entity.entity_id"
            class="top-entity-card"
            type="button"
            @click="openExplorer(entity)"
          >
            <span>{{ formatEntityType(entity.entity_type) }}</span>
            <strong>{{ entity.name }}</strong>
            <p>提及 {{ entity.mention_count }} 次</p>
          </button>
        </div>
      </article>
    </section>

    <section class="content-grid dashboard-grid secondary-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("home.formulaPreviewKicker") }}</p>
            <h2>方剂相关条文样本</h2>
          </div>
        </div>

        <p v-if="overviewError" class="status-text error">{{ overviewError }}</p>
        <p v-else-if="loadingOverview" class="status-text">正在加载文本概览...</p>
        <div v-else class="sample-feed">
          <article v-for="entry in formulaSamples" :key="entry.id" class="sample-card">
            <div class="result-meta">
              <span>条文 #{{ entry.id }}</span>
              <span v-if="entry.formula_name">{{ entry.formula_name }}</span>
            </div>
            <p>{{ entry.text }}</p>
          </article>
        </div>
      </article>

      <article class="panel narrative-panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("home.focusKicker") }}</p>
            <h2>当前系统能做什么</h2>
          </div>
        </div>

        <div class="narrative-list">
          <div class="narrative-item">
            <strong>关键词检索</strong>
            <p>按方剂、证候、症状、中药等入口快速定位核心知识节点。</p>
          </div>
          <div class="narrative-item">
            <strong>关系网络概览</strong>
            <p>从一个实体出发查看主要入边和出边，快速讲清“谁和谁相关”。</p>
          </div>
          <div class="narrative-item">
            <strong>原文证据回溯</strong>
            <p>所有实体都能回到条文片段，避免图谱展示脱离原文来源。</p>
          </div>
          <div class="narrative-item">
            <strong>候选复核闭环</strong>
            <p>抽取结果可以提交为候选记录，经过复核后继续回流到训练数据。</p>
          </div>
        </div>
      </article>
    </section>

    <section class="panel showcase-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">图谱版本</p>
          <h2>图谱版本管理</h2>
        </div>
      </div>

      <p v-if="loadingGraphRegistry" class="status-text">正在加载图谱版本...</p>
      <div v-else class="dataset-split-grid model-registry-grid">
        <article class="dataset-split-card">
          <span>当前默认图谱</span>
          <strong>{{ graphRegistry?.active.run_name || "未记录" }}</strong>
          <p v-if="graphRegistry?.active">
            {{ formatGraphSource(graphRegistry.active.source_type) }} · {{ formatGraphMetric(graphRegistry.active) }}
          </p>
          <p v-if="graphRegistry?.active">更新时间：{{ formatDateTime(graphRegistry.active.updated_at) }}</p>
        </article>

        <article class="dataset-split-card">
          <span>可切换版本</span>
          <div v-if="graphVersions.length" class="registry-list">
            <div v-for="record in graphVersions" :key="record.id" class="registry-row">
              <div>
                <strong>{{ record.run_name }}</strong>
                <p>{{ formatGraphSource(record.source_type) }} · {{ formatGraphMetric(record) }}</p>
                <p>更新时间：{{ formatDateTime(record.updated_at) }}</p>
              </div>
              <button
                class="ghost-button mini-button"
                type="button"
                :disabled="record.is_active || activatingGraphId === record.id"
                @click="runGraphActivation(record.id)"
              >
                {{ record.is_active ? "当前默认" : activatingGraphId === record.id ? "切换中..." : "设为默认" }}
              </button>
            </div>
          </div>
          <p v-else class="status-text">暂无已登记的图谱版本。</p>
        </article>
      </div>
    </section>
  </main>
</template>
