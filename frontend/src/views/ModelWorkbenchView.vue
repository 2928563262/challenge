<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref } from "vue";

import { fetchModelSummary, predictNer, predictRelation } from "../services/api";
import type { DatasetSplitSummary, ModelSummary, NerPrediction, NerPredictionEntity, RelationPrediction } from "../types/api";

const modelSummary = ref<ModelSummary | null>(null);
const prediction = ref<NerPrediction | null>(null);
const relationPrediction = ref<RelationPrediction | null>(null);

const inferenceText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationHeadText = ref("太阳病");
const relationHeadType = ref("SYNDROME");
const relationTailText = ref("桂枝汤");
const relationTailType = ref("FORMULA");

const loadingSummary = ref(false);
const predicting = ref(false);
const relationPredicting = ref(false);
const summaryError = ref("");
const predictError = ref("");
const relationPredictError = ref("");

const nerSplitEntries = computed(() => Object.entries(modelSummary.value?.ner.dataset_summary ?? {}));
const relationSplitEntries = computed(() => Object.entries(modelSummary.value?.relation.dataset_summary ?? {}));

const entityTypeLabels: Record<string, string> = {
  SYNDROME: "证候",
  SYMPTOM: "症状",
  FORMULA: "方剂",
  HERB: "中药",
  THERAPY: "治法",
  ADMINISTRATION: "服法",
};

const entityTypeOptions = [
  { label: "证候", value: "SYNDROME" },
  { label: "症状", value: "SYMPTOM" },
  { label: "方剂", value: "FORMULA" },
  { label: "中药", value: "HERB" },
  { label: "治法", value: "THERAPY" },
  { label: "服法", value: "ADMINISTRATION" },
];

function formatBoolean(value: boolean) {
  return value ? "已就绪" : "未就绪";
}

function formatEntityType(entityTypeName: string) {
  return entityTypeLabels[entityTypeName] || entityTypeName;
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
  } catch {
    summaryError.value = "模型摘要加载失败，请确认 Django 服务已经启动。";
  } finally {
    loadingSummary.value = false;
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
});
</script>

<template>
  <main class="page-shell knowledge-page model-page">
    <section class="panel explorer-hero">
      <div class="panel-header explorer-header">
        <div>
          <p class="panel-kicker">Model Layer</p>
          <h1>模型工作台</h1>
          <p class="hero-description explorer-description">
            这一页只关心模型层：查看 NER 与关系基线的数据准备、检查点和依赖状态，并直接在前端发起 NER / RE 预测。
          </p>
        </div>
        <div class="explorer-actions model-actions">
          <button class="ghost-button" type="button" @click="loadModelSummary" :disabled="loadingSummary">
            {{ loadingSummary ? "刷新中..." : "刷新模型摘要" }}
          </button>
          <RouterLink to="/explore" class="ghost-link">回到图谱浏览</RouterLink>
        </div>
      </div>
    </section>

    <p v-if="summaryError" class="status-text error">{{ summaryError }}</p>

    <section class="content-grid model-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">NER Baseline</p>
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
          <p>{{ modelSummary.ner.label_list.join(" / ") }}</p>
        </div>

        <div class="dataset-split-grid">
          <article v-for="([name, split]) in nerSplitEntries" :key="name" class="dataset-split-card">
            <span>{{ name }}</span>
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
            <p class="panel-kicker">Relation Baseline</p>
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
          <p>{{ modelSummary.relation.label_list.join(" / ") }}</p>
        </div>

        <div class="dataset-split-grid">
          <article v-for="([name, split]) in relationSplitEntries" :key="name" class="dataset-split-card">
            <span>{{ name }}</span>
            <strong>{{ summarizeSplit(split) }}</strong>
            <p v-if="labelEntries(split.label_count_by_type).length">
              {{ labelEntries(split.label_count_by_type).map(([key, value]) => `${key} ${value}`).join(" · ") }}
            </p>
          </article>
        </div>
      </article>
    </section>

    <section class="content-grid model-grid secondary-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Online Inference</p>
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

        <p v-if="predictError" class="status-text error">{{ predictError }}</p>
        <p v-else-if="!prediction" class="status-text">
          如果这里返回 “checkpoint not found”，说明模型数据链路已经通了，但还需要按工作台里的命令训练并导出检查点。
        </p>

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
              <span>{{ prediction.labels[index] }}</span>
            </div>
          </div>
        </template>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Relation Inference</p>
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

        <p v-if="relationPredictError" class="status-text error">{{ relationPredictError }}</p>
        <p v-else-if="!relationPrediction" class="status-text">
          先从上面的 NER 结果中快速填充实体，或者手动输入头尾实体。当前接口会优先使用关系基线检查点。
        </p>

        <template v-else>
          <div class="relation-result-card">
            <div class="breakdown-item"><span>预测标签</span><strong>{{ relationPrediction.label }}</strong></div>
            <div class="breakdown-item"><span>置信度</span><strong>{{ relationPrediction.confidence.toFixed(4) }}</strong></div>
            <div class="breakdown-item"><span>头实体</span><strong>{{ relationPrediction.head.text }} / {{ formatEntityType(relationPrediction.head.type) }}</strong></div>
            <div class="breakdown-item"><span>尾实体</span><strong>{{ relationPrediction.tail.text }} / {{ formatEntityType(relationPrediction.tail.type) }}</strong></div>
          </div>

          <div class="dataset-split-grid relation-score-grid">
            <article v-for="item in relationPrediction.top_predictions" :key="item.label" class="dataset-split-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.score.toFixed(4) }}</strong>
            </article>
          </div>
        </template>
      </article>
    </section>

    <section class="content-grid model-grid secondary-grid">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Runbook</p>
            <h2>当前模型链路</h2>
          </div>
        </div>

        <div class="narrative-list">
          <div class="narrative-item">
            <strong>1. NER 数据准备</strong>
            <p>{{ modelSummary?.ner.commands.prepare_ner_dataset || "python scripts/prepare_ner_dataset.py" }}</p>
          </div>
          <div class="narrative-item">
            <strong>2. NER 基线训练</strong>
            <p>{{ modelSummary?.ner.commands.train_ner_baseline || "python scripts/train_ner_baseline.py" }}</p>
          </div>
          <div class="narrative-item">
            <strong>3. RE 数据准备</strong>
            <p>{{ modelSummary?.relation.commands.prepare_relation_dataset || "python scripts/prepare_relation_dataset.py" }}</p>
          </div>
          <div class="narrative-item">
            <strong>4. RE 基线训练</strong>
            <p>{{ modelSummary?.relation.commands.train_relation_baseline || "python scripts/train_relation_baseline.py" }}</p>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Artifact Layout</p>
            <h2>训练产物约定</h2>
          </div>
        </div>

        <div class="narrative-list">
          <div class="narrative-item">
            <strong>NER 检查点目录</strong>
            <p>`models/baseline/ner/guwenbert-ner-baseline/best`</p>
          </div>
          <div class="narrative-item">
            <strong>RE 检查点目录</strong>
            <p>`models/baseline/relation/guwenbert-relation-baseline/best`</p>
          </div>
          <div class="narrative-item">
            <strong>实验结果目录</strong>
            <p>`experiments/ner` 与 `experiments/relation`</p>
          </div>
          <div class="narrative-item">
            <strong>系统读取方式</strong>
            <p>当前 Django 接口会自动读取上述默认目录，也支持通过环境变量覆盖。</p>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>
