<script setup lang="ts">
import axios from "axios";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import StatePanel from "../components/common/StatePanel.vue";
import HoverHint from "../components/common/HoverHint.vue";
import { formatBioLabel, formatEntityTypeLabel, formatRelationTypeLabel, formatSplitName } from "../i18n";
import { activateModel, fetchModelSummary, fetchTrainingJobs, predictNer, predictRelation, refreshAcceptedPipeline, runSystemPipeline, startTrainingJob } from "../services/api";
import type {
  ArtifactReport,
  DatasetSplitSummary,
  ModelRegistryRecord,
  ModelSummary,
  NerPrediction,
  NerPredictionEntity,
  RelationPrediction,
  SystemPipelineRunResponse,
  TrainingJobsStatus,
} from "../types/api";

const { t } = useI18n();
const translate = t as unknown as (key: string, params?: Record<string, unknown>) => string;

function tf(key: string, params: Record<string, string | number>) {
  return String(translate(key, params));
}
const modelSummary = ref<ModelSummary | null>(null);
const prediction = ref<NerPrediction | null>(null);
const relationPrediction = ref<RelationPrediction | null>(null);
const trainingJobs = ref<TrainingJobsStatus | null>(null);

const inferenceText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationHeadText = ref("太阳病");
const relationHeadType = ref("SYNDROME");
const relationTailText = ref("桂枝汤");
const relationTailType = ref("FORMULA");

const loadingSummary = ref(false);
const refreshingPipeline = ref(false);
const predicting = ref(false);
const relationPredicting = ref(false);
const activatingTask = ref<"ner" | "relation" | "">("");
const startingTraining = ref(false);
const loadingTrainingJobs = ref(false);
const runningSystemPipeline = ref(false);
const summaryError = ref("");
const predictError = ref("");
const relationPredictError = ref("");
const pipelineMessage = ref("");
const trainingMessage = ref("");
const systemPipelineMessage = ref("");

const trainingTask = ref<"ner" | "relation">("ner");
const trainingDatasetSource = ref<"baseline" | "merged">("merged");
const trainingEpochs = ref(3);
const trainingBatchSize = ref(4);
const trainingActivate = ref(false);
const trainingRunName = ref("");
const systemPipelineSyncNeo4j = ref(false);
const systemPipelineStartTraining = ref<"none" | "ner" | "relation">("none");
const systemPipelineActivateTraining = ref(false);
const systemPipelineDatasetSource = ref<"baseline" | "merged">("merged");
const systemPipelineEpochs = ref(3);
const systemPipelineBatchSize = ref(4);
let trainingJobsTimer: number | null = null;

const nerSplitEntries = computed(() => Object.entries(modelSummary.value?.ner.dataset_summary ?? {}));
const relationSplitEntries = computed(() => Object.entries(modelSummary.value?.relation.dataset_summary ?? {}));
const acceptedPipeline = computed(() => modelSummary.value?.accepted_pipeline ?? null);
const activeNerModel = computed(() => modelSummary.value?.registry.active.ner ?? null);
const activeRelationModel = computed(() => modelSummary.value?.registry.active.relation ?? null);
const nerModelRuns = computed(() => modelSummary.value?.registry.ner ?? []);
const relationModelRuns = computed(() => modelSummary.value?.registry.relation ?? []);
const trainingJobList = computed(() => trainingJobs.value?.jobs ?? []);
const runningTrainingCount = computed(() => trainingJobs.value?.running_count ?? 0);

const entityTypeOptions = [
  { label: formatEntityTypeLabel("SYNDROME"), value: "SYNDROME" },
  { label: formatEntityTypeLabel("SYMPTOM"), value: "SYMPTOM" },
  { label: formatEntityTypeLabel("FORMULA"), value: "FORMULA" },
  { label: formatEntityTypeLabel("HERB"), value: "HERB" },
  { label: formatEntityTypeLabel("THERAPY"), value: "THERAPY" },
  { label: formatEntityTypeLabel("ADMINISTRATION"), value: "ADMINISTRATION" },
];

function formatBoolean(value: boolean) {
  return value ? t("common.ready") : t("common.notReady");
}

function formatDateTime(value: string) {
  if (!value) {
    return t("common.notRecorded");
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatTrainingStatus(status: string) {
  if (status === "running") {
    return t("common.running");
  }
  if (status === "succeeded") {
    return t("common.succeeded");
  }
  if (status === "failed") {
    return t("common.failed");
  }
  return status;
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

function readPrimaryMetric(record: ModelRegistryRecord) {
  if (record.task === "ner") {
    const f1 = record.validation_metrics.eval_f1 ?? record.validation_metrics.f1;
    return typeof f1 === "number" ? tf("home.metric.nerF1", { score: f1.toFixed(4) }) : t("home.metric.noRecord");
  }
  const macroF1 = record.validation_metrics.eval_macro_f1 ?? record.validation_metrics.macro_f1;
  return typeof macroF1 === "number" ? tf("home.metric.relationMacroF1", { score: macroF1.toFixed(4) }) : t("home.metric.noRecord");
}

function formatUpdatedAt(timestamp: number | null) {
  if (!timestamp) {
    return t("common.notGenerated");
  }
  return new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatNeo4jManualSummary(summary: Record<string, number>) {
  const total = Number(summary.manual_overrides ?? 0);
  const upserted = Number(summary.manual_relations_upserted ?? 0);
  const suppressed = Number(summary.manual_relations_suppressed ?? 0);
  if (!total && !upserted && !suppressed) {
    return t("home.sync.manualSummaryZero");
  }
  return tf("home.sync.manualSummary", { total, upserted, suppressed });
}

function readReportValue(report: ArtifactReport | null | undefined, path: string[]) {
  const payload = report?.data;
  if (!payload || typeof payload !== "object") {
    return null;
  }
  let current: unknown = payload;
  for (const key of path) {
    if (!current || typeof current !== "object" || !(key in current)) {
      return null;
    }
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

function formatEntityType(entityTypeName: string) {
  return formatEntityTypeLabel(entityTypeName);
}

function summarizeSplit(split: DatasetSplitSummary) {
  const parts: string[] = [];
  if (typeof split.record_count === "number") {
    parts.push(tf("models.splitRecordCount", { count: split.record_count }));
  }
  if (typeof split.example_count === "number") {
    parts.push(tf("models.splitExampleCount", { count: split.example_count }));
  }
  if (typeof split.token_count === "number") {
    parts.push(tf("models.splitTokenCount", { count: split.token_count }));
  }
  if (typeof split.positive_example_count === "number") {
    parts.push(tf("models.splitPositiveCount", { count: split.positive_example_count }));
  }
  if (typeof split.negative_example_count === "number") {
    parts.push(tf("models.splitNegativeCount", { count: split.negative_example_count }));
  }
  return parts.join(" · ");
}

function labelEntries(record: Record<string, number> | undefined) {
  return Object.entries(record ?? {});
}

function useEntityForRelation(role: "head" | "tail", entity: NerPredictionEntity) {
  relationText.value = prediction.value?.text || relationText.value;
  if (role === "head") {
    relationHeadText.value = entity.text;
    relationHeadType.value = entity.type;
  } else {
    relationTailText.value = entity.text;
    relationTailType.value = entity.type;
  }
}

async function loadModelSummary() {
  loadingSummary.value = true;
  summaryError.value = "";
  try {
    modelSummary.value = await fetchModelSummary();
    trainingJobs.value = modelSummary.value.training_jobs;
  } catch {
    summaryError.value = t("models.statusLoadFailed");
  } finally {
    loadingSummary.value = false;
  }
}

async function loadTrainingJobs() {
  loadingTrainingJobs.value = true;
  summaryError.value = "";
  try {
    trainingJobs.value = await fetchTrainingJobs(20);
  } catch {
    summaryError.value = t("models.trainingJobsLoadFailed");
  } finally {
    loadingTrainingJobs.value = false;
  }
}

function stopTrainingJobsPolling() {
  if (trainingJobsTimer !== null) {
    window.clearInterval(trainingJobsTimer);
    trainingJobsTimer = null;
  }
}

function startTrainingJobsPolling() {
  stopTrainingJobsPolling();
  trainingJobsTimer = window.setInterval(async () => {
    if (loadingTrainingJobs.value || startingTraining.value) {
      return;
    }
    await loadTrainingJobs();
  }, 10000);
}

async function runAcceptedPipelineRefresh() {
  refreshingPipeline.value = true;
  summaryError.value = "";
  pipelineMessage.value = "";
  try {
    const payload = await refreshAcceptedPipeline();
    if (modelSummary.value) {
      modelSummary.value = {
        ...modelSummary.value,
        accepted_pipeline: payload.status,
      };
    } else {
      await loadModelSummary();
    }
    const recordCount = Number((payload.export_report as Record<string, any>)?.stats?.record_count ?? 0);
    const addedCount = Number((payload.merge_report as Record<string, any>)?.stats?.ner?.added_count ?? 0);
    pipelineMessage.value = tf("models.acceptedRefreshDone", { recordCount, addedCount });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || t("models.acceptedRefreshFailed"));
    } else {
      summaryError.value = t("models.acceptedRefreshFailed");
    }
  } finally {
    refreshingPipeline.value = false;
  }
}

function summarizeSystemPipeline(payload: SystemPipelineRunResponse) {
  const parts: string[] = [];
  if (payload.accepted_pipeline) {
    const recordCount = Number((payload.accepted_pipeline.export_report as Record<string, any>)?.stats?.record_count ?? 0);
    parts.push(tf("models.acceptedBackflow", { count: recordCount }));
  }
  if (payload.graph_refresh) {
    const graphSummary = payload.graph_refresh.graph_summary;
    parts.push(tf("models.graphRefreshSummary", { nodes: graphSummary.entity_node_count, relations: graphSummary.entity_relation_count }));
    if (payload.graph_refresh.neo4j_sync?.ok) {
      const summary = payload.graph_refresh.neo4j_sync.summary ?? {};
      parts.push(
        tf("models.neo4jSyncSummary", {
          nodes: Number(summary.entity_nodes ?? 0),
          relations: Number(summary.entity_relations ?? 0),
          manualSummary: formatNeo4jManualSummary(summary),
        }),
      );
    }
  } else if (payload.neo4j_sync?.ok) {
    const summary = payload.neo4j_sync.summary ?? {};
    parts.push(
      tf("models.neo4jSyncSummary", {
        nodes: Number(summary.entity_nodes ?? 0),
        relations: Number(summary.entity_relations ?? 0),
        manualSummary: formatNeo4jManualSummary(summary),
      }),
    );
  }
  if (payload.training_jobs_started.length) {
    parts.push(tf("models.startedTrainingSummary", { runName: payload.training_jobs_started[0].run_name }));
  }
  return parts.join("；");
}

async function runSystemPipelineAction() {
  if (systemPipelineEpochs.value <= 0 || systemPipelineBatchSize.value <= 0) {
    summaryError.value = t("models.systemPipelineConfigInvalid");
    return;
  }

  runningSystemPipeline.value = true;
  summaryError.value = "";
  systemPipelineMessage.value = "";
  pipelineMessage.value = "";
  trainingMessage.value = "";
  try {
    const payload = await runSystemPipeline({
      refreshAccepted: true,
      refreshGraph: true,
      syncNeo4j: systemPipelineSyncNeo4j.value,
      startNerTraining: systemPipelineStartTraining.value === "ner",
      startRelationTraining: systemPipelineStartTraining.value === "relation",
      trainingDatasetSource: systemPipelineDatasetSource.value,
      trainingEpochs: systemPipelineEpochs.value,
      trainingBatchSize: systemPipelineBatchSize.value,
      activateTraining: systemPipelineActivateTraining.value,
    });

    modelSummary.value = payload.model_summary;
    trainingJobs.value = payload.training_jobs_status;
    systemPipelineMessage.value = summarizeSystemPipeline(payload) || t("models.systemPipelineDone");
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || t("models.systemPipelineFailed"));
    } else {
      summaryError.value = t("models.systemPipelineFailed");
    }
  } finally {
    runningSystemPipeline.value = false;
  }
}

async function runModelActivation(task: "ner" | "relation", modelId: string) {
  activatingTask.value = task;
  summaryError.value = "";
  pipelineMessage.value = "";
  try {
    const payload = await activateModel({ task, modelId });
    await loadModelSummary();
    pipelineMessage.value = tf("models.modelSwitchDone", {
      task: task.toUpperCase(),
      runName: payload.record.run_name,
    });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || t("models.modelSwitchFailed"));
    } else {
      summaryError.value = t("models.modelSwitchFailed");
    }
  } finally {
    activatingTask.value = "";
  }
}

async function runTrainingStart() {
  if (trainingEpochs.value <= 0 || trainingBatchSize.value <= 0) {
    summaryError.value = t("models.trainingConfigInvalid");
    return;
  }

  startingTraining.value = true;
  summaryError.value = "";
  trainingMessage.value = "";
  try {
    const payload = await startTrainingJob({
      task: trainingTask.value,
      datasetSource: trainingDatasetSource.value,
      epochs: trainingEpochs.value,
      batchSize: trainingBatchSize.value,
      runName: trainingRunName.value.trim() || undefined,
      activate: trainingActivate.value,
    });
    trainingJobs.value = payload.jobs;
    await loadModelSummary();
    trainingMessage.value = tf("models.trainingStartDone", {
      task: trainingTask.value.toUpperCase(),
      runName: payload.job.run_name,
    });
    trainingRunName.value = "";
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || t("models.trainingStartFailed"));
    } else {
      summaryError.value = t("models.trainingStartFailed");
    }
  } finally {
    startingTraining.value = false;
  }
}

async function runPrediction() {
  const text = inferenceText.value.trim();
  if (!text) {
    predictError.value = t("models.nerInputRequired");
    return;
  }

  predicting.value = true;
  predictError.value = "";
  prediction.value = null;

  try {
    prediction.value = await predictNer(text);
    relationText.value = text;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      predictError.value = String(error.response?.data?.detail || t("models.nerPredictFailedWithCheckpoint"));
    } else {
      predictError.value = t("models.nerPredictFailed");
    }
  } finally {
    predicting.value = false;
  }
}

async function runRelationPrediction() {
  const text = relationText.value.trim();
  if (!text) {
    relationPredictError.value = t("models.relationInputRequired");
    return;
  }
  if (!relationHeadText.value.trim() || !relationTailText.value.trim()) {
    relationPredictError.value = t("models.relationEntityRequired");
    return;
  }

  relationPredicting.value = true;
  relationPredictError.value = "";
  relationPrediction.value = null;

  try {
    relationPrediction.value = await predictRelation({
      text,
      head: {
        text: relationHeadText.value.trim(),
        type: relationHeadType.value,
      },
      tail: {
        text: relationTailText.value.trim(),
        type: relationTailType.value,
      },
    });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      relationPredictError.value = String(error.response?.data?.detail || t("models.relationPredictFailedWithCheckpoint"));
    } else {
      relationPredictError.value = t("models.relationPredictFailed");
    }
  } finally {
    relationPredicting.value = false;
  }
}

onMounted(async () => {
  await loadModelSummary();
  startTrainingJobsPolling();
});

onBeforeUnmount(() => {
  stopTrainingJobsPolling();
});
</script>

<template>
  <main class="page-shell knowledge-page model-page">
    <section class="panel explorer-hero">
      <div class="panel-header explorer-header">
        <div>
          <p class="panel-kicker">{{ t("models.heroKicker") }}</p>
          <h1>{{ t("models.heroTitle") }}</h1>
          <p class="hero-description explorer-description">{{ t("models.heroDescription") }}</p>
        </div>
        <div class="explorer-actions model-actions">
          <button class="ghost-button" type="button" @click="loadModelSummary" :disabled="loadingSummary">
            {{ loadingSummary ? t("common.refreshing") : t("common.refreshModelSummary") }}
          </button>
          <RouterLink to="/explore" class="ghost-link">{{ t("common.backToExplorer") }}</RouterLink>
        </div>
      </div>
    </section>

    <StatePanel v-if="summaryError" tone="error">
      <p>{{ summaryError }}</p>
    </StatePanel>
    <StatePanel v-else-if="systemPipelineMessage" tone="success">
      <p>{{ systemPipelineMessage }}</p>
    </StatePanel>
    <StatePanel v-else-if="pipelineMessage" tone="success">
      <p>{{ pipelineMessage }}</p>
    </StatePanel>
    <StatePanel v-else-if="trainingMessage" tone="success">
      <p>{{ trainingMessage }}</p>
    </StatePanel>

    <section class="content-grid model-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.nerBaselineKicker") }}</p>
            <h2>{{ t("models.nerStatusTitle") }}</h2>
          </div>
        </div>

        <div v-if="modelSummary" class="model-status-list">
          <div class="breakdown-item"><span>{{ t("models.baseModel") }}</span><strong>{{ modelSummary.ner.base_model_name }}</strong></div>
          <div class="breakdown-item"><span>{{ t("models.checkpoint") }}</span><strong>{{ formatBoolean(modelSummary.ner.checkpoint_exists) }}</strong></div>
          <div class="breakdown-item"><span>{{ t("models.datasetManifest") }}</span><strong>{{ formatBoolean(modelSummary.ner.dataset_manifest_exists) }}</strong></div>
          <div class="breakdown-item"><span>{{ t("models.runningStatus") }}</span><strong>{{ formatBoolean(modelSummary.ner.ready) }}</strong></div>
        </div>

        <div v-if="modelSummary?.ner.missing_dependencies.length" class="muted-list">
          <strong>{{ t("models.missingDependencies") }}</strong>
          <p>{{ modelSummary.ner.missing_dependencies.join("、") }}</p>
        </div>

        <div v-if="modelSummary?.ner.label_list.length" class="muted-list">
          <strong>{{ t("models.labelSpace") }}</strong>
          <p>{{ modelSummary.ner.label_list.map((label) => formatBioLabel(label)).join(" / ") }}</p>
        </div>

        <div class="dataset-split-grid">
          <article v-for="([name, split]) in nerSplitEntries" :key="name" class="dataset-split-card">
            <span>{{ formatSplitName(name) }}</span>
            <strong>{{ summarizeSplit(split) }}</strong>
            <p v-if="labelEntries(split.entity_count_by_type).length">
              {{ labelEntries(split.entity_count_by_type).map(([key, value]) => `${formatEntityType(key)} ${value}`).join(" · ") }}
            </p>
          </article>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.relationBaselineKicker") }}</p>
            <h2>{{ t("models.relationStatusTitle") }}</h2>
          </div>
        </div>

        <div v-if="modelSummary" class="model-status-list">
          <div class="breakdown-item"><span>{{ t("models.baseModel") }}</span><strong>{{ modelSummary.relation.base_model_name }}</strong></div>
          <div class="breakdown-item"><span>{{ t("models.checkpoint") }}</span><strong>{{ formatBoolean(modelSummary.relation.checkpoint_exists) }}</strong></div>
          <div class="breakdown-item"><span>{{ t("models.datasetManifest") }}</span><strong>{{ formatBoolean(modelSummary.relation.dataset_manifest_exists) }}</strong></div>
          <div class="breakdown-item"><span>{{ t("models.runningStatus") }}</span><strong>{{ formatBoolean(modelSummary.relation.ready) }}</strong></div>
        </div>

        <div v-if="modelSummary?.relation.missing_dependencies.length" class="muted-list">
          <strong>{{ t("models.missingDependencies") }}</strong>
          <p>{{ modelSummary.relation.missing_dependencies.join("、") }}</p>
        </div>

        <div v-if="modelSummary?.relation.label_list.length" class="muted-list">
          <strong>{{ t("models.relationLabels") }}</strong>
          <p>{{ modelSummary.relation.label_list.map((label) => formatRelationTypeLabel(label)).join(" / ") }}</p>
        </div>

        <div class="dataset-split-grid">
          <article v-for="([name, split]) in relationSplitEntries" :key="name" class="dataset-split-card">
            <span>{{ formatSplitName(name) }}</span>
            <strong>{{ summarizeSplit(split) }}</strong>
            <p v-if="labelEntries(split.label_count_by_type).length">
              {{ labelEntries(split.label_count_by_type).map(([key, value]) => `${formatRelationTypeLabel(key)} ${value}`).join(" · ") }}
            </p>
          </article>
        </div>
      </article>
    </section>

    <section class="content-grid model-grid secondary-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.oneClickLoopKicker") }}</p>
            <h2>{{ t("models.oneClickLoopTitle") }}</h2>
          </div>
          <button class="primary-button" type="button" :disabled="runningSystemPipeline" @click="runSystemPipelineAction">
            {{ runningSystemPipeline ? t("models.oneClickLoopRunning") : t("models.oneClickLoopRun") }}
          </button>
        </div>

        <form class="model-form" @submit.prevent>
          <div class="relation-form-grid">
            <div class="relation-form-block">
              <label>{{ t("models.optionalTrainingTask") }}</label>
              <select v-model="systemPipelineStartTraining">
                <option value="none">{{ t("models.noTraining") }}</option>
                <option value="ner">{{ t("models.startNerTraining") }}</option>
                <option value="relation">{{ t("models.startRelationTraining") }}</option>
              </select>
              <label>{{ t("models.trainingDataSource") }}</label>
              <select v-model="systemPipelineDatasetSource">
                <option value="merged">{{ t("models.mergedDataset") }}</option>
                <option value="baseline">{{ t("models.baselineDataset") }}</option>
              </select>
            </div>

            <div class="relation-form-block">
              <label>{{ t("models.trainingEpochs") }}</label>
              <input v-model.number="systemPipelineEpochs" type="number" min="1" />
              <label>{{ t("models.trainingBatchSize") }}</label>
              <input v-model.number="systemPipelineBatchSize" type="number" min="1" />
            </div>
          </div>

          <label class="selection-strip">
            <input v-model="systemPipelineSyncNeo4j" type="checkbox" />
            {{ t("models.syncNeo4jAfterLoop") }}
          </label>
          <label class="selection-strip">
            <input v-model="systemPipelineActivateTraining" type="checkbox" />
            {{ t("models.activateAfterTraining") }}
          </label>
        </form>

        <div class="inline-hint-row">
          <HoverHint :text="t('models.loopHint')" :aria-label="t('models.oneClickLoopTitle')" />
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.trainingJobsKicker") }}</p>
            <h2>{{ t("models.trainingJobsTitle") }}</h2>
          </div>
          <button class="ghost-button" type="button" :disabled="loadingTrainingJobs" @click="loadTrainingJobs">
            {{ loadingTrainingJobs ? t("models.refreshingJobs") : t("models.refreshJobs") }}
          </button>
        </div>

        <form class="model-form" @submit.prevent="runTrainingStart">
          <div class="relation-form-grid">
            <div class="relation-form-block">
              <label>{{ t("models.trainingTask") }}</label>
              <select v-model="trainingTask">
                <option value="ner">NER</option>
                <option value="relation">RE</option>
              </select>
              <label>{{ t("models.dataSource") }}</label>
              <select v-model="trainingDatasetSource">
                <option value="merged">{{ t("models.mergedDataset") }}</option>
                <option value="baseline">{{ t("models.baselineDataset") }}</option>
              </select>
            </div>

            <div class="relation-form-block">
              <label>{{ t("models.trainingEpochs") }}</label>
              <input v-model.number="trainingEpochs" type="number" min="1" />
              <label>{{ t("models.trainingBatchSize") }}</label>
              <input v-model.number="trainingBatchSize" type="number" min="1" />
            </div>
          </div>

          <div class="relation-form-block">
            <label>{{ t("models.runNameOptional") }}</label>
            <input v-model="trainingRunName" type="text" :placeholder="t('models.runNamePlaceholder')" />
          </div>

          <label class="selection-strip">
            <input v-model="trainingActivate" type="checkbox" />
            {{ t("models.activateWhenDone") }}
          </label>

          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="startingTraining">
              {{ startingTraining ? t("models.trainingStarting") : t("models.startTraining") }}
            </button>
          </div>
        </form>

        <div class="dataset-split-grid">
          <article class="dataset-split-card">
            <span>{{ t("models.runningTaskCount") }}</span>
            <strong>{{ runningTrainingCount }}</strong>
            <p>{{ t("models.trainingStatusHint") }}</p>
          </article>
        </div>

        <div v-if="trainingJobList.length" class="registry-list">
          <div v-for="job in trainingJobList" :key="job.id" class="registry-row">
            <div>
              <strong>{{ job.run_name }}</strong>
              <p>{{ job.task.toUpperCase() }} · {{ job.dataset_source === "merged" ? t("models.mergedDataset") : t("models.baselineDataset") }} · {{ formatTrainingStatus(job.status) }}</p>
              <p>{{ tf("models.trainingParams", { epochs: job.epochs, batchSize: job.batch_size, activateText: job.activate ? t("models.activateEnabled") : t("models.activateDisabled") }) }}</p>
              <p>{{ tf("models.createdAt", { time: formatDateTime(job.created_at) }) }}</p>
              <p v-if="job.finished_at">{{ tf("models.finishedAt", { time: formatDateTime(job.finished_at) }) }}</p>
              <p>{{ tf("models.logPath", { path: job.log_path }) }}</p>
              <p v-if="job.error_message">{{ tf("models.failedReason", { reason: job.error_message }) }}</p>
            </div>
          </div>
        </div>
        <div v-else class="inline-hint-row">
          <HoverHint :text="t('models.noTrainingJobs')" :aria-label="t('models.trainingTaskTitle')" />
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.defaultModelKicker") }}</p>
            <h2>{{ t("models.defaultModelTitle") }}</h2>
          </div>
        </div>

        <div class="dataset-split-grid">
          <article v-if="activeNerModel" class="dataset-split-card">
            <span>{{ t("models.defaultNerModel") }}</span>
            <strong>{{ activeNerModel.run_name }}</strong>
            <p>{{ formatDatasetSource(activeNerModel.dataset_source) }} · {{ readPrimaryMetric(activeNerModel) }}</p>
            <p>{{ tf("models.updatedAt", { time: formatDateTime(activeNerModel.updated_at) }) }}</p>
          </article>
          <article v-if="activeRelationModel" class="dataset-split-card">
            <span>{{ t("models.defaultRelationModel") }}</span>
            <strong>{{ activeRelationModel.run_name }}</strong>
            <p>{{ formatDatasetSource(activeRelationModel.dataset_source) }} · {{ readPrimaryMetric(activeRelationModel) }}</p>
            <p>{{ tf("models.updatedAt", { time: formatDateTime(activeRelationModel.updated_at) }) }}</p>
          </article>
        </div>

        <div class="dataset-split-grid model-registry-grid">
          <article class="dataset-split-card">
            <span>{{ t("models.selectableNerRuns") }}</span>
            <div v-if="nerModelRuns.length" class="registry-list">
              <div v-for="record in nerModelRuns" :key="record.id" class="registry-row">
                <div>
                  <strong>{{ record.run_name }}</strong>
                  <p>{{ formatDatasetSource(record.dataset_source) }} · {{ readPrimaryMetric(record) }}</p>
                </div>
                <button
                  class="ghost-button mini-button"
                  type="button"
                  :disabled="record.is_active || activatingTask === 'ner'"
                  @click="runModelActivation('ner', record.id)"
                >
                  {{ record.is_active ? t("models.currentDefault") : activatingTask === "ner" ? t("models.switching") : t("models.setDefault") }}
                </button>
              </div>
            </div>
            <div v-else class="inline-hint-row">
              <HoverHint :text="t('models.noNerRuns')" :aria-label="t('models.selectableNerRuns')" />
            </div>
          </article>

          <article class="dataset-split-card">
            <span>{{ t("models.selectableRelationRuns") }}</span>
            <div v-if="relationModelRuns.length" class="registry-list">
              <div v-for="record in relationModelRuns" :key="record.id" class="registry-row">
                <div>
                  <strong>{{ record.run_name }}</strong>
                  <p>{{ formatDatasetSource(record.dataset_source) }} · {{ readPrimaryMetric(record) }}</p>
                </div>
                <button
                  class="ghost-button mini-button"
                  type="button"
                  :disabled="record.is_active || activatingTask === 'relation'"
                  @click="runModelActivation('relation', record.id)"
                >
                  {{ record.is_active ? t("models.currentDefault") : activatingTask === "relation" ? t("models.switching") : t("models.setDefault") }}
                </button>
              </div>
            </div>
            <div v-else class="inline-hint-row">
              <HoverHint :text="t('models.noRelationRuns')" :aria-label="t('models.selectableRelationRuns')" />
            </div>
          </article>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.acceptedLoopKicker") }}</p>
            <h2>{{ t("models.acceptedLoopTitle") }}</h2>
          </div>
          <button class="primary-button" type="button" :disabled="refreshingPipeline" @click="runAcceptedPipelineRefresh">
            {{ refreshingPipeline ? t("models.acceptedRefreshing") : t("models.acceptedRefresh") }}
          </button>
        </div>

        <div v-if="acceptedPipeline" class="dataset-split-grid">
          <article class="dataset-split-card">
            <span>{{ t("models.acceptedExport") }}</span>
            <strong>{{ tf("models.acceptedExportCount", { count: Number(readReportValue(acceptedPipeline.accepted_report, ["stats", "record_count"]) ?? 0) }) }}</strong>
            <p>{{ tf("models.updatedAt", { time: formatUpdatedAt(acceptedPipeline.accepted_report.updated_at) }) }}</p>
          </article>
          <article class="dataset-split-card">
            <span>{{ t("models.incrementalDataset") }}</span>
            <strong>
              NER {{ readReportValue(acceptedPipeline.incremental_report, ["stats", "ner", "record_count"]) ?? 0 }}
              · RE {{ readReportValue(acceptedPipeline.incremental_report, ["stats", "relation", "example_count"]) ?? 0 }}
            </strong>
            <p>{{ tf("models.updatedAt", { time: formatUpdatedAt(acceptedPipeline.incremental_report.updated_at) }) }}</p>
          </article>
          <article class="dataset-split-card">
            <span>{{ t("models.mergedTrainset") }}</span>
            <strong>
              NER +{{ readReportValue(acceptedPipeline.merge_report, ["stats", "ner", "added_count"]) ?? 0 }}
              · RE +{{ readReportValue(acceptedPipeline.merge_report, ["stats", "relation", "added_count"]) ?? 0 }}
            </strong>
            <p>{{ tf("models.updatedAt", { time: formatUpdatedAt(acceptedPipeline.merge_report.updated_at) }) }}</p>
          </article>
        </div>

      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.inferenceKicker") }}</p>
            <h2>{{ t("models.nerOnlinePredictTitle") }}</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runPrediction">
          <textarea
            v-model="inferenceText"
            rows="6"
            :placeholder="t('models.nerInputPlaceholder')"
          />
          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="predicting">
              {{ predicting ? t("models.predicting") : t("models.predictStart") }}
            </button>
          </div>
        </form>

        <StatePanel v-if="predictError" tone="error">
          <p>{{ predictError }}</p>
        </StatePanel>
        <div v-else-if="!prediction" class="inline-hint-row">
          <HoverHint :text="t('models.nerHint')" :aria-label="t('models.nerOnlinePredictTitle')" />
        </div>

        <template v-else>
          <div class="entity-chip-list">
            <div v-for="entity in prediction.entities" :key="`${entity.start}-${entity.end}-${entity.type}`" class="entity-chip">
              <strong>{{ entity.text }}</strong>
              <span>{{ formatEntityType(entity.type) }}</span>
              <small>{{ entity.start }}-{{ entity.end }}</small>
              <div class="entity-chip-actions">
                <button class="ghost-button mini-button" type="button" @click="useEntityForRelation('head', entity)">{{ t("models.setAsHead") }}</button>
                <button class="ghost-button mini-button" type="button" @click="useEntityForRelation('tail', entity)">{{ t("models.setAsTail") }}</button>
              </div>
            </div>
          </div>

          <div class="token-grid">
            <div v-for="(token, index) in prediction.tokens" :key="`${token}-${index}`" class="token-chip">
              <strong>{{ token }}</strong>
              <span>{{ formatBioLabel(prediction.labels[index]) }}</span>
            </div>
          </div>
        </template>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.relationInferenceKicker") }}</p>
            <h2>{{ t("models.relationPredictTitle") }}</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runRelationPrediction">
          <textarea
            v-model="relationText"
            rows="5"
            :placeholder="t('models.relationInputPlaceholder')"
          />

          <div class="relation-form-grid">
            <div class="relation-form-block">
              <label>{{ t("models.headEntityText") }}</label>
              <input v-model="relationHeadText" type="text" :placeholder="t('models.headExample')" />
              <label>{{ t("models.headEntityType") }}</label>
              <select v-model="relationHeadType">
                <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>

            <div class="relation-form-block">
              <label>{{ t("models.tailEntityText") }}</label>
              <input v-model="relationTailText" type="text" :placeholder="t('models.tailExample')" />
              <label>{{ t("models.tailEntityType") }}</label>
              <select v-model="relationTailType">
                <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
          </div>

          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="relationPredicting">
              {{ relationPredicting ? t("models.predicting") : t("models.startRelationPredict") }}
            </button>
          </div>
        </form>

        <StatePanel v-if="relationPredictError" tone="error">
          <p>{{ relationPredictError }}</p>
        </StatePanel>
        <div v-else-if="!relationPrediction" class="inline-hint-row">
          <HoverHint :text="t('models.relationHint')" :aria-label="t('models.relationPredictTitle')" />
        </div>

        <template v-else>
          <div class="relation-result-card">
            <div class="breakdown-item"><span>{{ t("models.predictedRelation") }}</span><strong>{{ formatRelationTypeLabel(relationPrediction.label) }}</strong></div>
            <div class="breakdown-item"><span>{{ t("models.confidence") }}</span><strong>{{ relationPrediction.confidence.toFixed(4) }}</strong></div>
            <div class="breakdown-item"><span>{{ t("models.headEntity") }}</span><strong>{{ relationPrediction.head.text }} / {{ formatEntityType(relationPrediction.head.type) }}</strong></div>
            <div class="breakdown-item"><span>{{ t("models.tailEntity") }}</span><strong>{{ relationPrediction.tail.text }} / {{ formatEntityType(relationPrediction.tail.type) }}</strong></div>
          </div>

          <div class="dataset-split-grid relation-score-grid">
            <article v-for="item in relationPrediction.top_predictions" :key="item.label" class="dataset-split-card">
              <span>{{ formatRelationTypeLabel(item.label) }}</span>
              <strong>{{ item.score.toFixed(4) }}</strong>
            </article>
          </div>
        </template>
      </article>
    </section>

  </main>
</template>
