<script setup lang="ts">
import axios from "axios";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import StatePanel from "../components/common/StatePanel.vue";
import { formatBioLabel, formatEntityTypeLabel, formatRelationTypeLabel, formatSplitName } from "../i18n";
import { activateModel, fetchModelSummary, fetchTrainingJobs, predictNer, predictRelation, refreshAcceptedPipeline, startTrainingJob } from "../services/api";
import type {
  ArtifactReport,
  DatasetSplitSummary,
  ModelRegistryRecord,
  ModelSummary,
  NerPrediction,
  NerPredictionEntity,
  RelationPrediction,
  TrainingJobsStatus,
} from "../types/api";

const { t } = useI18n();
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
const summaryError = ref("");
const predictError = ref("");
const relationPredictError = ref("");
const pipelineMessage = ref("");
const trainingMessage = ref("");

const trainingTask = ref<"ner" | "relation">("ner");
const trainingDatasetSource = ref<"baseline" | "merged">("merged");
const trainingEpochs = ref(3);
const trainingBatchSize = ref(4);
const trainingActivate = ref(false);
const trainingRunName = ref("");
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
  return value ? "已就绪" : "未就绪";
}

function formatDateTime(value: string) {
  if (!value) {
    return "未记录";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatTrainingStatus(status: string) {
  if (status === "running") {
    return "运行中";
  }
  if (status === "succeeded") {
    return "已完成";
  }
  if (status === "failed") {
    return "失败";
  }
  return status;
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

function readPrimaryMetric(record: ModelRegistryRecord) {
  if (record.task === "ner") {
    const f1 = record.validation_metrics.eval_f1 ?? record.validation_metrics.f1;
    return typeof f1 === "number" ? `验证 F1 ${f1.toFixed(4)}` : "验证指标未记录";
  }
  const macroF1 = record.validation_metrics.eval_macro_f1 ?? record.validation_metrics.macro_f1;
  return typeof macroF1 === "number" ? `验证 Macro-F1 ${macroF1.toFixed(4)}` : "验证指标未记录";
}

function formatUpdatedAt(timestamp: number | null) {
  if (!timestamp) {
    return "未生成";
  }
  return new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false });
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
    parts.push(`记录 ${split.record_count}`);
  }
  if (typeof split.example_count === "number") {
    parts.push(`样本 ${split.example_count}`);
  }
  if (typeof split.token_count === "number") {
    parts.push(`字符 ${split.token_count}`);
  }
  if (typeof split.positive_example_count === "number") {
    parts.push(`正例 ${split.positive_example_count}`);
  }
  if (typeof split.negative_example_count === "number") {
    parts.push(`负例 ${split.negative_example_count}`);
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
    summaryError.value = "模型摘要加载失败，请确认 Django 服务已经启动。";
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
    summaryError.value = "训练任务列表加载失败，请确认后端服务正常。";
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
    pipelineMessage.value = `已完成已采纳数据回流：导出 ${recordCount} 条记录，NER 合并训练集新增 ${addedCount} 条样本。`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || "accepted 数据回流失败。");
    } else {
      summaryError.value = "accepted 数据回流失败。";
    }
  } finally {
    refreshingPipeline.value = false;
  }
}

async function runModelActivation(task: "ner" | "relation", modelId: string) {
  activatingTask.value = task;
  summaryError.value = "";
  pipelineMessage.value = "";
  try {
    const payload = await activateModel({ task, modelId });
    await loadModelSummary();
    pipelineMessage.value = `已切换当前默认${task === "ner" ? "NER" : "RE"}模型：${payload.record.run_name}`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || "默认模型切换失败。");
    } else {
      summaryError.value = "默认模型切换失败。";
    }
  } finally {
    activatingTask.value = "";
  }
}

async function runTrainingStart() {
  if (trainingEpochs.value <= 0 || trainingBatchSize.value <= 0) {
    summaryError.value = "训练轮数和批大小必须大于 0。";
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
    trainingMessage.value = `已启动${trainingTask.value.toUpperCase()}训练任务：${payload.job.run_name}`;
    trainingRunName.value = "";
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      summaryError.value = String(error.response?.data?.detail || "启动训练任务失败。");
    } else {
      summaryError.value = "启动训练任务失败。";
    }
  } finally {
    startingTraining.value = false;
  }
}

async function runPrediction() {
  const text = inferenceText.value.trim();
  if (!text) {
    predictError.value = "请输入待预测文本。";
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
      predictError.value = String(error.response?.data?.detail || "NER 预测失败，请先训练并导出模型检查点。");
    } else {
      predictError.value = "NER 预测失败，请稍后重试。";
    }
  } finally {
    predicting.value = false;
  }
}

async function runRelationPrediction() {
  const text = relationText.value.trim();
  if (!text) {
    relationPredictError.value = "请输入关系预测文本。";
    return;
  }
  if (!relationHeadText.value.trim() || !relationTailText.value.trim()) {
    relationPredictError.value = "请输入头实体和尾实体。";
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
      relationPredictError.value = String(error.response?.data?.detail || "关系预测失败，请先训练并导出关系模型检查点。");
    } else {
      relationPredictError.value = "关系预测失败，请稍后重试。";
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
          <h1>模型工作台</h1>
          <p class="hero-description explorer-description">
            这一页只关心模型层：查看 NER 与关系基线的数据准备、检查点和依赖状态，并直接在前端发起 NER / RE 预测。
          </p>
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
            <h2>命名实体识别状态</h2>
          </div>
        </div>

        <div v-if="modelSummary" class="model-status-list">
          <div class="breakdown-item"><span>基座模型</span><strong>{{ modelSummary.ner.base_model_name }}</strong></div>
          <div class="breakdown-item"><span>模型检查点</span><strong>{{ formatBoolean(modelSummary.ner.checkpoint_exists) }}</strong></div>
          <div class="breakdown-item"><span>数据集清单</span><strong>{{ formatBoolean(modelSummary.ner.dataset_manifest_exists) }}</strong></div>
          <div class="breakdown-item"><span>运行状态</span><strong>{{ formatBoolean(modelSummary.ner.ready) }}</strong></div>
        </div>

        <div v-if="modelSummary?.ner.missing_dependencies.length" class="muted-list">
          <strong>缺失依赖</strong>
          <p>{{ modelSummary.ner.missing_dependencies.join("、") }}</p>
        </div>

        <div v-if="modelSummary?.ner.label_list.length" class="muted-list">
          <strong>标签空间</strong>
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
            <h2>关系抽取状态</h2>
          </div>
        </div>

        <div v-if="modelSummary" class="model-status-list">
          <div class="breakdown-item"><span>基座模型</span><strong>{{ modelSummary.relation.base_model_name }}</strong></div>
          <div class="breakdown-item"><span>模型检查点</span><strong>{{ formatBoolean(modelSummary.relation.checkpoint_exists) }}</strong></div>
          <div class="breakdown-item"><span>数据集清单</span><strong>{{ formatBoolean(modelSummary.relation.dataset_manifest_exists) }}</strong></div>
          <div class="breakdown-item"><span>运行状态</span><strong>{{ formatBoolean(modelSummary.relation.ready) }}</strong></div>
        </div>

        <div v-if="modelSummary?.relation.missing_dependencies.length" class="muted-list">
          <strong>缺失依赖</strong>
          <p>{{ modelSummary.relation.missing_dependencies.join("、") }}</p>
        </div>

        <div v-if="modelSummary?.relation.label_list.length" class="muted-list">
          <strong>关系标签</strong>
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
            <p class="panel-kicker">训练任务</p>
            <h2>一键启动与状态跟踪</h2>
          </div>
          <button class="ghost-button" type="button" :disabled="loadingTrainingJobs" @click="loadTrainingJobs">
            {{ loadingTrainingJobs ? "刷新中..." : "刷新任务状态" }}
          </button>
        </div>

        <form class="model-form" @submit.prevent="runTrainingStart">
          <div class="relation-form-grid">
            <div class="relation-form-block">
              <label>训练任务</label>
              <select v-model="trainingTask">
                <option value="ner">NER</option>
                <option value="relation">RE</option>
              </select>
              <label>数据来源</label>
              <select v-model="trainingDatasetSource">
                <option value="merged">合并训练集</option>
                <option value="baseline">基础训练集</option>
              </select>
            </div>

            <div class="relation-form-block">
              <label>训练轮数</label>
              <input v-model.number="trainingEpochs" type="number" min="1" />
              <label>批大小</label>
              <input v-model.number="trainingBatchSize" type="number" min="1" />
            </div>
          </div>

          <div class="relation-form-block">
            <label>运行名称（可选）</label>
            <input v-model="trainingRunName" type="text" placeholder="留空则自动生成 run_name" />
          </div>

          <label class="selection-strip">
            <input v-model="trainingActivate" type="checkbox" />
            训练完成后自动设为默认模型
          </label>

          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="startingTraining">
              {{ startingTraining ? "启动中..." : "启动训练任务" }}
            </button>
          </div>
        </form>

        <div class="dataset-split-grid">
          <article class="dataset-split-card">
            <span>运行中任务数</span>
            <strong>{{ runningTrainingCount }}</strong>
            <p>任务状态会在刷新后更新。</p>
          </article>
        </div>

        <div v-if="trainingJobList.length" class="registry-list">
          <div v-for="job in trainingJobList" :key="job.id" class="registry-row">
            <div>
              <strong>{{ job.run_name }}</strong>
              <p>{{ job.task.toUpperCase() }} · {{ job.dataset_source === "merged" ? "合并训练集" : "基础训练集" }} · {{ formatTrainingStatus(job.status) }}</p>
              <p>参数：{{ job.epochs }} epoch · batch {{ job.batch_size }} · {{ job.activate ? "完成后激活" : "不自动激活" }}</p>
              <p>创建时间：{{ formatDateTime(job.created_at) }}</p>
              <p v-if="job.finished_at">完成时间：{{ formatDateTime(job.finished_at) }}</p>
              <p>日志文件：{{ job.log_path }}</p>
              <p v-if="job.error_message">失败原因：{{ job.error_message }}</p>
            </div>
          </div>
        </div>
        <StatePanel v-else tone="info">
          <p>当前没有训练任务记录。</p>
        </StatePanel>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">默认模型</p>
            <h2>当前生效版本</h2>
          </div>
        </div>

        <div class="dataset-split-grid">
          <article v-if="activeNerModel" class="dataset-split-card">
            <span>NER 默认模型</span>
            <strong>{{ activeNerModel.run_name }}</strong>
            <p>{{ formatDatasetSource(activeNerModel.dataset_source) }} · {{ readPrimaryMetric(activeNerModel) }}</p>
            <p>更新时间：{{ formatDateTime(activeNerModel.updated_at) }}</p>
          </article>
          <article v-if="activeRelationModel" class="dataset-split-card">
            <span>RE 默认模型</span>
            <strong>{{ activeRelationModel.run_name }}</strong>
            <p>{{ formatDatasetSource(activeRelationModel.dataset_source) }} · {{ readPrimaryMetric(activeRelationModel) }}</p>
            <p>更新时间：{{ formatDateTime(activeRelationModel.updated_at) }}</p>
          </article>
        </div>

        <div class="dataset-split-grid model-registry-grid">
          <article class="dataset-split-card">
            <span>可选 NER 运行记录</span>
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
                  {{ record.is_active ? "当前默认" : activatingTask === "ner" ? "切换中..." : "设为默认" }}
                </button>
              </div>
            </div>
            <StatePanel v-else tone="warning">
              <p>暂无已注册的 NER 训练记录。</p>
            </StatePanel>
          </article>

          <article class="dataset-split-card">
            <span>可选 RE 运行记录</span>
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
                  {{ record.is_active ? "当前默认" : activatingTask === "relation" ? "切换中..." : "设为默认" }}
                </button>
              </div>
            </div>
            <StatePanel v-else tone="warning">
              <p>暂无已注册的 RE 训练记录。</p>
            </StatePanel>
          </article>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.acceptedLoopKicker") }}</p>
            <h2>已采纳数据回流</h2>
          </div>
          <button class="primary-button" type="button" :disabled="refreshingPipeline" @click="runAcceptedPipelineRefresh">
            {{ refreshingPipeline ? t("models.acceptedRefreshing") : t("models.acceptedRefresh") }}
          </button>
        </div>

        <div v-if="acceptedPipeline" class="dataset-split-grid">
          <article class="dataset-split-card">
            <span>已采纳导出</span>
            <strong>{{ readReportValue(acceptedPipeline.accepted_report, ["stats", "record_count"]) ?? 0 }} 条记录</strong>
            <p>更新时间：{{ formatUpdatedAt(acceptedPipeline.accepted_report.updated_at) }}</p>
          </article>
          <article class="dataset-split-card">
            <span>增量 NER/RE</span>
            <strong>
              NER {{ readReportValue(acceptedPipeline.incremental_report, ["stats", "ner", "record_count"]) ?? 0 }}
              · RE {{ readReportValue(acceptedPipeline.incremental_report, ["stats", "relation", "example_count"]) ?? 0 }}
            </strong>
            <p>更新时间：{{ formatUpdatedAt(acceptedPipeline.incremental_report.updated_at) }}</p>
          </article>
          <article class="dataset-split-card">
            <span>merged 训练集</span>
            <strong>
              NER +{{ readReportValue(acceptedPipeline.merge_report, ["stats", "ner", "added_count"]) ?? 0 }}
              · RE +{{ readReportValue(acceptedPipeline.merge_report, ["stats", "relation", "added_count"]) ?? 0 }}
            </strong>
            <p>更新时间：{{ formatUpdatedAt(acceptedPipeline.merge_report.updated_at) }}</p>
          </article>
        </div>

      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("models.inferenceKicker") }}</p>
            <h2>NER 在线预测</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runPrediction">
          <textarea
            v-model="inferenceText"
            rows="6"
            placeholder="输入《伤寒论》条文或短句，系统会返回字符级标签和实体结果。"
          />
          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="predicting">
              {{ predicting ? "预测中..." : "开始预测" }}
            </button>
          </div>
        </form>

        <StatePanel v-if="predictError" tone="error">
          <p>{{ predictError }}</p>
        </StatePanel>
        <StatePanel v-else-if="!prediction" tone="info">
          <p>如果这里返回 “checkpoint not found”，说明模型数据链路已经通了，但还需要按训练流程导出检查点。</p>
        </StatePanel>

        <template v-else>
          <div class="entity-chip-list">
            <div v-for="entity in prediction.entities" :key="`${entity.start}-${entity.end}-${entity.type}`" class="entity-chip">
              <strong>{{ entity.text }}</strong>
              <span>{{ formatEntityType(entity.type) }}</span>
              <small>{{ entity.start }}-{{ entity.end }}</small>
              <div class="entity-chip-actions">
                <button class="ghost-button mini-button" type="button" @click="useEntityForRelation('head', entity)">设为头实体</button>
                <button class="ghost-button mini-button" type="button" @click="useEntityForRelation('tail', entity)">设为尾实体</button>
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
            <h2>关系预测</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runRelationPrediction">
          <textarea
            v-model="relationText"
            rows="5"
            placeholder="输入一条含有两个实体的条文，系统会预测两者关系。"
          />

          <div class="relation-form-grid">
            <div class="relation-form-block">
              <label>头实体文本</label>
              <input v-model="relationHeadText" type="text" placeholder="例如：太阳病" />
              <label>头实体类型</label>
              <select v-model="relationHeadType">
                <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>

            <div class="relation-form-block">
              <label>尾实体文本</label>
              <input v-model="relationTailText" type="text" placeholder="例如：桂枝汤" />
              <label>尾实体类型</label>
              <select v-model="relationTailType">
                <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
          </div>

          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="relationPredicting">
              {{ relationPredicting ? "预测中..." : "开始关系预测" }}
            </button>
          </div>
        </form>

        <StatePanel v-if="relationPredictError" tone="error">
          <p>{{ relationPredictError }}</p>
        </StatePanel>
        <StatePanel v-else-if="!relationPrediction" tone="info">
          <p>先从上面的 NER 结果中快速填充实体，或者手动输入头尾实体。当前接口会优先使用关系基线检查点。</p>
        </StatePanel>

        <template v-else>
          <div class="relation-result-card">
            <div class="breakdown-item"><span>预测标签</span><strong>{{ formatRelationTypeLabel(relationPrediction.label) }}</strong></div>
            <div class="breakdown-item"><span>置信度</span><strong>{{ relationPrediction.confidence.toFixed(4) }}</strong></div>
            <div class="breakdown-item"><span>头实体</span><strong>{{ relationPrediction.head.text }} / {{ formatEntityType(relationPrediction.head.type) }}</strong></div>
            <div class="breakdown-item"><span>尾实体</span><strong>{{ relationPrediction.tail.text }} / {{ formatEntityType(relationPrediction.tail.type) }}</strong></div>
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
