<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import StatePanel from "../components/common/StatePanel.vue";
import { formatEntityTypeLabel } from "../i18n";
import {
  fetchGraphNeo4jSyncStatus,
  fetchGraphShowcase,
  fetchGraphSummary,
  fetchModelSummary,
  fetchOverview,
  syncGraphToNeo4j,
} from "../services/api";
import type {
  CorpusOverview,
  GraphEntity,
  GraphNeo4jSyncStatus,
  GraphShowcaseCase,
  GraphSummary,
  GraphVersionRecord,
  ModelSummary,
} from "../types/api";

const router = useRouter();

const overview = ref<CorpusOverview | null>(null);
const graphSummary = ref<GraphSummary | null>(null);
const showcaseCases = ref<GraphShowcaseCase[]>([]);
const modelSummary = ref<ModelSummary | null>(null);
const graphSyncStatus = ref<GraphNeo4jSyncStatus | null>(null);

const loadingOverview = ref(false);
const loadingGraphSummary = ref(false);
const loadingShowcase = ref(false);
const loadingModelSummary = ref(false);
const loadingGraphSyncStatus = ref(false);
const syncingGraph = ref(false);

const overviewError = ref("");
const graphError = ref("");
const showcaseError = ref("");
const modelError = ref("");
const graphSyncError = ref("");
const graphSyncMessage = ref("");

const heroStats = computed(() => {
  if (!graphSummary.value) {
    return [];
  }
  return [
    { label: "清洗后条文", value: graphSummary.value.input_record_count.toLocaleString("zh-CN") },
    { label: "知识节点", value: graphSummary.value.entity_node_count.toLocaleString("zh-CN") },
    { label: "实体关系", value: graphSummary.value.entity_relation_count.toLocaleString("zh-CN") },
    { label: "原文证据边", value: graphSummary.value.clause_mention_count.toLocaleString("zh-CN") },
  ];
});

const systemStatusCards = computed(() => {
  if (!modelSummary.value || !graphSummary.value?.graph_version) {
    return [];
  }

  const activeNer = modelSummary.value.registry.active.ner;
  const activeRelation = modelSummary.value.registry.active.relation;
  const acceptedReportData = modelSummary.value.accepted_pipeline.accepted_report.data as Record<string, unknown> | null;
  const acceptedStats = (acceptedReportData?.stats ?? null) as Record<string, unknown> | null;
  const acceptedCount = Number(acceptedStats?.record_count ?? 0);

  return [
    {
      label: "默认实体识别模型",
      value: activeNer.run_name,
      meta: `${formatDatasetSource(activeNer.dataset_source)} · ${formatModelMetric(activeNer)}`,
    },
    {
      label: "默认关系抽取模型",
      value: activeRelation.run_name,
      meta: `${formatDatasetSource(activeRelation.dataset_source)} · ${formatModelMetric(activeRelation)}`,
    },
    {
      label: "当前图谱版本",
      value: graphSummary.value.graph_version.run_name,
      meta: `${formatGraphSource(graphSummary.value.graph_version.source_type)} · ${formatGraphMetric(graphSummary.value.graph_version)}`,
    },
    {
      label: "已采纳记录",
      value: `${acceptedCount} 条`,
      meta: `最近更新：${formatUnixTimestamp(modelSummary.value.accepted_pipeline.accepted_report.updated_at)}`,
    },
  ];
});

const graphSyncCard = computed(() => {
  const report = graphSyncStatus.value?.report;
  if (!report) {
    return null;
  }
  const summary = report.summary ?? {};
  return {
    label: report.ok ? "最近一次 Neo4j 同步" : "Neo4j 同步失败",
    value: typeof (report.graph_version as Record<string, unknown>)?.run_name === "string"
      ? String((report.graph_version as Record<string, unknown>).run_name)
      : "未记录",
    meta: report.ok
      ? `节点 ${summary.entity_nodes ?? 0} · 关系 ${summary.entity_relations ?? 0} · 数据库 ${report.database}`
      : report.detail,
  };
});

const topEntities = computed(() => graphSummary.value?.top_entities ?? []);
const formulaSamples = computed(() => overview.value?.formula_samples.slice(0, 6) ?? []);

function formatEntityType(entityTypeName: string) {
  return formatEntityTypeLabel(entityTypeName);
}

function formatGraphSource(sourceType: string) {
  if (sourceType === "accepted_reviewed") {
    return "复核图谱";
  }
  if (sourceType === "cleaned_silver") {
    return "银标准图谱";
  }
  return "自定义图谱";
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

function formatUnixTimestamp(value: number | null) {
  if (!value) {
    return "未记录";
  }
  return new Date(value * 1000).toLocaleString("zh-CN", { hour12: false });
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
    overviewError.value = "文本概览加载失败，请确认后端服务已启动。";
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

async function loadGraphSyncStatus() {
  loadingGraphSyncStatus.value = true;
  graphSyncError.value = "";
  try {
    graphSyncStatus.value = await fetchGraphNeo4jSyncStatus();
  } catch {
    graphSyncError.value = "Neo4j 同步状态加载失败，请确认图谱接口可访问。";
  } finally {
    loadingGraphSyncStatus.value = false;
  }
}

async function runNeo4jSync() {
  syncingGraph.value = true;
  graphSyncError.value = "";
  graphSyncMessage.value = "";
  try {
    const payload = await syncGraphToNeo4j();
    graphSyncStatus.value = payload.status;
    const summary = payload.sync.summary ?? {};
    graphSyncMessage.value = `已同步到 Neo4j：节点 ${summary.entity_nodes ?? 0}，关系 ${summary.entity_relations ?? 0}。`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      graphSyncError.value = String(error.response?.data?.detail || "Neo4j 同步失败。");
      if (error.response?.data?.status) {
        graphSyncStatus.value = error.response.data.status as GraphNeo4jSyncStatus;
      }
    } else {
      graphSyncError.value = "Neo4j 同步失败。";
    }
  } finally {
    syncingGraph.value = false;
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
  await Promise.all([loadOverview(), loadGraphSummary(), loadShowcase(), loadModelSummary(), loadGraphSyncStatus()]);
});
</script>

<template>
  <main class="page-shell knowledge-page home-dashboard">
    <section class="hero-panel hero-grid">
      <div class="hero-copy">
        <p class="eyebrow">伤寒论知识图谱系统</p>
        <h1>《伤寒论》知识图谱与抽取系统</h1>
        <p class="hero-description">面向《伤寒论》文本的知识抽取、图谱检索、候选复核与模型回流一体化原型。</p>
        <div class="cta-row">
          <RouterLink to="/explore" class="primary-link-button">进入图谱浏览</RouterLink>
          <RouterLink to="/annotations" class="ghost-link">进入候选复核</RouterLink>
        </div>
      </div>
    </section>

    <section class="stats-grid hero-stats">
      <StatePanel v-if="graphError" tone="error">
        <p>{{ graphError }}</p>
      </StatePanel>
      <StatePanel v-else-if="loadingGraphSummary" tone="info">
        <p>正在加载图谱统计...</p>
      </StatePanel>
      <template v-else>
        <article v-for="item in heroStats" :key="item.label" class="stat-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </template>
    </section>

    <section class="panel showcase-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">系统状态</p>
          <h2>当前运行总览</h2>
        </div>
      </div>

      <StatePanel v-if="modelError" tone="error">
        <p>{{ modelError }}</p>
      </StatePanel>
      <StatePanel v-else-if="loadingModelSummary" tone="info">
        <p>正在加载系统状态...</p>
      </StatePanel>
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
          <p class="panel-kicker">图谱同步</p>
          <h2>Neo4j 同步状态</h2>
        </div>
        <button class="ghost-button" type="button" :disabled="syncingGraph" @click="runNeo4jSync">
          {{ syncingGraph ? "同步中..." : "同步当前图谱到 Neo4j" }}
        </button>
      </div>

      <StatePanel v-if="graphSyncError" tone="error">
        <p>{{ graphSyncError }}</p>
      </StatePanel>
      <StatePanel v-else-if="graphSyncMessage" tone="success">
        <p>{{ graphSyncMessage }}</p>
      </StatePanel>
      <StatePanel v-else-if="loadingGraphSyncStatus" tone="info">
        <p>正在加载 Neo4j 同步状态...</p>
      </StatePanel>
      <div v-else-if="graphSyncCard" class="dataset-split-grid">
        <article class="dataset-split-card">
          <span>{{ graphSyncCard.label }}</span>
          <strong>{{ graphSyncCard.value }}</strong>
          <p>{{ graphSyncCard.meta }}</p>
        </article>
      </div>
      <StatePanel v-else tone="warning">
        <p>当前还没有 Neo4j 同步记录。</p>
      </StatePanel>
    </section>

    <section class="content-grid dashboard-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">典型案例</p>
            <h2>答辩演示入口</h2>
          </div>
          <RouterLink to="/explore" class="ghost-link">查看图谱细节</RouterLink>
        </div>

        <StatePanel v-if="showcaseError" tone="error">
          <p>{{ showcaseError }}</p>
        </StatePanel>
        <StatePanel v-else-if="loadingShowcase" tone="info">
          <p>正在加载典型案例...</p>
        </StatePanel>
        <div v-else class="showcase-grid">
          <button v-for="caseItem in showcaseCases" :key="caseItem.slug" type="button" class="showcase-case-card" @click="openCase(caseItem)">
            <div class="showcase-case-head">
              <div>
                <p class="entity-type-tag">{{ caseItem.focus }}</p>
                <h3>{{ caseItem.title }}</h3>
              </div>
              <span>{{ caseItem.entity.name }}</span>
            </div>
            <p>{{ caseItem.description }}</p>
          </button>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">高频节点</p>
            <h2>图谱核心实体</h2>
          </div>
        </div>

        <div class="top-entity-grid">
          <button v-for="entity in topEntities" :key="entity.entity_id" class="top-entity-card" type="button" @click="openExplorer(entity)">
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
            <p class="panel-kicker">文本样本</p>
            <h2>方剂相关条文</h2>
          </div>
        </div>

        <StatePanel v-if="overviewError" tone="error">
          <p>{{ overviewError }}</p>
        </StatePanel>
        <StatePanel v-else-if="loadingOverview" tone="info">
          <p>正在加载文本概览...</p>
        </StatePanel>
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

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">下一步</p>
            <h2>系统操作建议</h2>
          </div>
        </div>
        <div class="narrative-list">
          <div class="narrative-item">
            <strong>1. 候选复核</strong>
            <p>先在“候选复核”页补充并采纳记录，确保增量数据质量。</p>
          </div>
          <div class="narrative-item">
            <strong>2. 模型回流</strong>
            <p>在“模型工作台”刷新已采纳回流，然后启动新一轮 NER/RE 训练任务。</p>
          </div>
          <div class="narrative-item">
            <strong>3. 图谱同步</strong>
            <p>完成复核图谱刷新后，把当前图谱同步到 Neo4j，用于检索展示与答辩演示。</p>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>
