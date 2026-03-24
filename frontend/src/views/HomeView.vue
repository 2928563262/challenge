<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import HoverHint from "../components/common/HoverHint.vue";
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
const { t } = useI18n();
const translate = t as unknown as (key: string, params?: Record<string, unknown>) => string;

function tf(key: string, params: Record<string, string | number>) {
  return String(translate(key, params));
}

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
    { label: t("home.stats.cleanedRecords"), value: graphSummary.value.input_record_count.toLocaleString("zh-CN") },
    { label: t("home.stats.entityNodes"), value: graphSummary.value.entity_node_count.toLocaleString("zh-CN") },
    { label: t("home.stats.entityRelations"), value: graphSummary.value.entity_relation_count.toLocaleString("zh-CN") },
    { label: t("home.stats.evidenceEdges"), value: graphSummary.value.clause_mention_count.toLocaleString("zh-CN") },
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
      label: t("home.system.defaultNerModel"),
      value: activeNer.run_name,
      meta: `${formatDatasetSource(activeNer.dataset_source)} · ${formatModelMetric(activeNer)}`,
    },
    {
      label: t("home.system.defaultRelationModel"),
      value: activeRelation.run_name,
      meta: `${formatDatasetSource(activeRelation.dataset_source)} · ${formatModelMetric(activeRelation)}`,
    },
    {
      label: t("home.system.currentGraphVersion"),
      value: graphSummary.value.graph_version.run_name,
      meta: `${formatGraphSource(graphSummary.value.graph_version.source_type)} · ${formatGraphMetric(graphSummary.value.graph_version)}`,
    },
    {
      label: t("home.system.acceptedRecords"),
      value: tf("home.system.acceptedRecordCount", { count: acceptedCount }),
      meta: tf("home.system.updatedAt", {
        time: formatUnixTimestamp(modelSummary.value.accepted_pipeline.accepted_report.updated_at),
      }),
    },
  ];
});

function formatNeo4jManualSummary(summary: Record<string, unknown>) {
  const total = Number(summary.manual_overrides ?? 0);
  const upserted = Number(summary.manual_relations_upserted ?? 0);
  const suppressed = Number(summary.manual_relations_suppressed ?? 0);
  if (!total && !upserted && !suppressed) {
    return t("home.sync.manualSummaryZero");
  }
  return tf("home.sync.manualSummary", { total, upserted, suppressed });
}

const graphSyncCard = computed(() => {
  const report = graphSyncStatus.value?.report;
  if (!report) {
    return null;
  }
  const summary = (report.summary ?? {}) as Record<string, unknown>;
  return {
    label: report.ok ? t("home.sync.latestSync") : t("home.sync.latestSyncFailed"),
    value:
      typeof (report.graph_version as Record<string, unknown>)?.run_name === "string"
        ? String((report.graph_version as Record<string, unknown>).run_name)
        : t("common.notRecorded"),
    meta: report.ok
      ? tf("home.sync.syncCardMeta", {
          entityNodes: Number(summary.entity_nodes ?? 0),
          entityRelations: Number(summary.entity_relations ?? 0),
          manualSummary: formatNeo4jManualSummary(summary),
          database: report.database,
        })
      : report.detail,
  };
});

const topEntities = computed(() => graphSummary.value?.top_entities ?? []);
const formulaSamples = computed(() => overview.value?.formula_samples.slice(0, 6) ?? []);

function getMentionCount(value: unknown) {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatEntityType(entityTypeName: string) {
  return formatEntityTypeLabel(entityTypeName);
}

function formatGraphSource(sourceType: string) {
  if (sourceType === "accepted_reviewed") {
    return t("home.graphSource.reviewed");
  }
  if (sourceType === "cleaned_silver") {
    return t("home.graphSource.cleanedSilver");
  }
  return t("home.graphSource.custom");
}

function formatDatasetSource(source: string) {
  if (source === "merged") {
    return t("home.datasetSource.merged");
  }
  if (source === "incremental") {
    return t("home.datasetSource.incremental");
  }
  return t("home.datasetSource.baseline");
}

function formatModelMetric(record: ModelSummary["registry"]["active"]["ner"] | ModelSummary["registry"]["active"]["relation"]) {
  if (record.task === "ner") {
    const f1 = record.validation_metrics.eval_f1 ?? record.validation_metrics.f1;
    return typeof f1 === "number" ? tf("home.metric.nerF1", { score: f1.toFixed(4) }) : t("home.metric.noRecord");
  }
  const macroF1 = record.validation_metrics.eval_macro_f1 ?? record.validation_metrics.macro_f1;
  return typeof macroF1 === "number"
    ? tf("home.metric.relationMacroF1", { score: macroF1.toFixed(4) })
    : t("home.metric.noRecord");
}

function formatGraphMetric(record: GraphVersionRecord) {
  const entityCount = Number(record.stats.entity_node_count ?? 0);
  const relationCount = Number(record.stats.entity_relation_count ?? 0);
  return tf("home.graphMetric", { entityCount, relationCount });
}

function formatUnixTimestamp(value: number | null) {
  if (!value) {
    return t("common.notRecorded");
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
    overviewError.value = t("home.errors.overviewLoadFailed");
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
    graphError.value = t("home.errors.graphSummaryLoadFailed");
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
    modelError.value = t("home.errors.modelSummaryLoadFailed");
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
    graphSyncError.value = t("home.errors.graphSyncStatusLoadFailed");
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
    const summary = (payload.sync.summary ?? {}) as Record<string, unknown>;
    graphSyncMessage.value = tf("home.sync.successMessage", {
      entityNodes: Number(summary.entity_nodes ?? 0),
      entityRelations: Number(summary.entity_relations ?? 0),
      manualSummary: formatNeo4jManualSummary(summary),
    });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      graphSyncError.value = String(error.response?.data?.detail || t("home.errors.graphSyncFailed"));
      if (error.response?.data?.status) {
        graphSyncStatus.value = error.response.data.status as GraphNeo4jSyncStatus;
      }
    } else {
      graphSyncError.value = t("home.errors.graphSyncFailed");
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
    showcaseError.value = t("home.errors.showcaseLoadFailed");
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
        <p class="eyebrow">{{ t("home.hero.eyebrow") }}</p>
        <h1>{{ t("home.hero.title") }}</h1>
        <p class="hero-description">{{ t("home.hero.description") }}</p>
        <div class="cta-row">
          <RouterLink to="/explore" class="primary-link-button">{{ t("home.hero.enterExplore") }}</RouterLink>
          <RouterLink to="/annotations" class="ghost-link">{{ t("home.hero.enterAnnotations") }}</RouterLink>
        </div>
      </div>
    </section>

    <section class="stats-grid hero-stats">
      <StatePanel v-if="graphError" tone="error">
        <p>{{ graphError }}</p>
      </StatePanel>
      <StatePanel v-else-if="loadingGraphSummary" tone="info">
        <p>{{ t("home.loading.graphStats") }}</p>
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
          <p class="panel-kicker">{{ t("home.panels.systemKicker") }}</p>
          <h2>{{ t("home.panels.systemTitle") }}</h2>
        </div>
      </div>

      <StatePanel v-if="modelError" tone="error">
        <p>{{ modelError }}</p>
      </StatePanel>
      <StatePanel v-else-if="loadingModelSummary" tone="info">
        <p>{{ t("home.loading.systemStatus") }}</p>
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
          <p class="panel-kicker">{{ t("home.panels.syncKicker") }}</p>
          <h2>{{ t("home.panels.syncTitle") }}</h2>
        </div>
        <button class="ghost-button" type="button" :disabled="syncingGraph" @click="runNeo4jSync">
          {{ syncingGraph ? t("home.sync.syncing") : t("home.sync.syncAction") }}
        </button>
      </div>

      <StatePanel v-if="graphSyncError" tone="error">
        <p>{{ graphSyncError }}</p>
      </StatePanel>
      <StatePanel v-else-if="graphSyncMessage" tone="success">
        <p>{{ graphSyncMessage }}</p>
      </StatePanel>
      <StatePanel v-else-if="loadingGraphSyncStatus" tone="info">
        <p>{{ t("home.loading.syncStatus") }}</p>
      </StatePanel>
      <div v-else-if="graphSyncCard" class="dataset-split-grid">
        <article class="dataset-split-card">
          <span>{{ graphSyncCard.label }}</span>
          <strong>{{ graphSyncCard.value }}</strong>
          <p>{{ graphSyncCard.meta }}</p>
        </article>
      </div>
      <div v-else class="inline-hint-row">
        <HoverHint :text="t('home.sync.noSyncRecord')" :aria-label="t('home.panels.syncTitle')" />
      </div>
    </section>

    <section class="content-grid dashboard-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("home.panels.showcaseKicker") }}</p>
          </div>
          <RouterLink to="/explore" class="ghost-link">{{ t("home.actions.viewGraphDetail") }}</RouterLink>
        </div>

        <StatePanel v-if="showcaseError" tone="error">
          <p>{{ showcaseError }}</p>
        </StatePanel>
        <StatePanel v-else-if="loadingShowcase" tone="info">
          <p>{{ t("home.loading.showcase") }}</p>
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
            <p class="panel-kicker">{{ t("home.panels.topEntityKicker") }}</p>
            <h2>{{ t("home.panels.topEntityTitle") }}</h2>
          </div>
        </div>

        <div class="top-entity-grid">
          <button v-for="entity in topEntities" :key="entity.entity_id" class="top-entity-card" type="button" @click="openExplorer(entity)">
            <span>{{ formatEntityType(entity.entity_type) }}</span>
            <strong>{{ entity.name }}</strong>
            <p>{{ tf("home.entityMentionCount", { count: getMentionCount(entity.mention_count) }) }}</p>
          </button>
        </div>
      </article>
    </section>

    <section class="content-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("home.panels.sampleKicker") }}</p>
            <h2>{{ t("home.panels.sampleTitle") }}</h2>
          </div>
        </div>

        <StatePanel v-if="overviewError" tone="error">
          <p>{{ overviewError }}</p>
        </StatePanel>
        <StatePanel v-else-if="loadingOverview" tone="info">
          <p>{{ t("home.loading.overview") }}</p>
        </StatePanel>
        <div v-else class="sample-feed">
          <article v-for="entry in formulaSamples" :key="entry.id" class="sample-card">
            <div class="result-meta">
              <span>{{ tf("home.recordLabel", { id: entry.id }) }}</span>
              <span v-if="entry.formula_name">{{ entry.formula_name }}</span>
            </div>
            <p>{{ entry.text }}</p>
          </article>
        </div>
      </article>
    </section>
  </main>
</template>
