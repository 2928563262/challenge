<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import { askQuestion } from "../services/api";
import type { QAAnswer } from "../types/api";

const router = useRouter();

const questionInput = ref("");
const answer = ref<QAAnswer | null>(null);
const isLoading = ref(false);
const errorMessage = ref("");

const suggestionQuestions = [
  "桂枝汤包含哪些中药？",
  "中风常见症状有哪些？",
  "桂枝汤主要对应什么证候？",
  "发热一般关联哪些证候？",
];

const isAsking = computed(() => isLoading.value && !answer.value);
const hasAnswer = computed(() => Boolean(answer.value));
const confidencePercent = computed(() => (answer.value ? Math.round(answer.value.confidence * 1000) / 10 : 0));
const confidenceLevel = computed(() => {
  const score = answer.value?.confidence ?? 0;
  if (score >= 0.8) {
    return "高";
  }
  if (score >= 0.6) {
    return "中";
  }
  return "低";
});

function goBack() {
  router.back();
}

function useSuggestion(question: string) {
  questionInput.value = question;
}

function renderMarkdown(text: string): string {
  if (!text) {
    return "";
  }
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.*?)__/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

function formatEntityType(type: string): string {
  const typeMap: Record<string, string> = {
    SYNDROME: "证候",
    SYMPTOM: "症状",
    FORMULA: "方剂",
    HERB: "中药",
    THERAPY: "治法",
    ADMINISTRATION: "服法",
  };
  return typeMap[type] || type;
}

async function handleAsk() {
  const question = questionInput.value.trim();
  if (!question) {
    errorMessage.value = "请输入问题后再提问。";
    return;
  }

  isLoading.value = true;
  errorMessage.value = "";
  answer.value = null;

  try {
    answer.value = await askQuestion(question);
  } catch (error: any) {
    errorMessage.value = String(error?.response?.data?.detail || "问答请求失败，请确认后端服务已启动。");
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <main class="page-shell knowledge-page qa-page">
    <section class="panel qa-hero-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">问答模块</p>
          <h1>智能问答</h1>
          <p class="hero-description">基于《伤寒论》图谱进行实体识别、关系检索与证据回溯。</p>
        </div>
        <button type="button" class="ghost-button" @click="goBack">返回上一页</button>
      </div>
    </section>

    <section class="panel qa-input-panel">
      <div class="qa-input-row">
        <textarea
          v-model="questionInput"
          rows="3"
          class="qa-question-input"
          placeholder="输入你的问题，例如：桂枝汤包含哪些中药？"
          :disabled="isAsking"
          @keyup.enter.exact.prevent="handleAsk"
        />
        <button type="button" class="primary-button qa-submit-button" :disabled="isAsking || !questionInput.trim()" @click="handleAsk">
          {{ isAsking ? "分析中..." : "开始提问" }}
        </button>
      </div>

      <div class="chip-group qa-suggest-group">
        <button v-for="q in suggestionQuestions" :key="q" type="button" class="filter-chip" @click="useSuggestion(q)">
          {{ q }}
        </button>
      </div>

      <p v-if="errorMessage" class="status-text error">{{ errorMessage }}</p>
    </section>

    <section v-if="isAsking" class="panel qa-loading-panel">
      <div class="qa-loading-dot" />
      <p>正在解析问题并检索图谱，请稍候...</p>
    </section>

    <section v-else-if="hasAnswer && answer" class="content-grid qa-result-layout">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">回答结果</p>
            <h2>问答结果</h2>
          </div>
        </div>
        <div class="qa-answer-main" v-html="renderMarkdown(answer.answer)" />

        <details v-if="answer.cypher" class="qa-details">
          <summary>查看查询语句</summary>
          <pre>{{ answer.cypher }}</pre>
        </details>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">证据检索</p>
            <h2>识别与证据</h2>
          </div>
        </div>

        <div class="qa-confidence-card">
          <span>置信度（{{ confidenceLevel }}）</span>
          <strong>{{ confidencePercent }}%</strong>
        </div>

        <div class="qa-side-block" v-if="answer.entities?.length">
          <h3>识别到的实体</h3>
          <div class="entity-chip-list">
            <span v-for="(entity, idx) in answer.entities" :key="`${entity.text}-${entity.start}-${idx}`" class="entity-chip">
              <strong>{{ entity.text }}</strong>
              <span>{{ formatEntityType(entity.type) }}</span>
            </span>
          </div>
        </div>

        <div class="qa-side-block" v-if="answer.related_entities?.length">
          <h3>图谱相关实体</h3>
          <div class="qa-related-list">
            <div v-for="entity in answer.related_entities" :key="entity.entity_id" class="qa-related-item">
              <div class="qa-related-head">
                <strong>{{ entity.name }}</strong>
                <span>{{ formatEntityType(entity.entity_type) }}</span>
              </div>
              <p>提及 {{ entity.mention_count }} 次 · 覆盖 {{ entity.record_count }} 条</p>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section v-else class="panel qa-empty-panel">
      <h2>使用说明</h2>
      <p>输入一条和《伤寒论》相关的问题，系统会优先识别实体，再从图谱中检索关系与原文证据。</p>
      <p>建议优先问：方剂组成、证候-症状、证候-方剂这三类问题，结果更稳定。</p>
    </section>
  </main>
</template>

<style scoped>
.qa-page {
  display: grid;
  gap: 16px;
}

.qa-hero-panel .panel-header h1 {
  margin: 0;
  font-size: clamp(1.6rem, 2.4vw, 2rem);
}

.qa-input-panel {
  display: grid;
  gap: 12px;
}

.qa-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
}

.qa-question-input {
  width: 100%;
  resize: vertical;
  border: 1px solid rgba(111, 74, 46, 0.18);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.84);
  font: inherit;
  color: #2f2218;
  line-height: 1.5;
}

.qa-question-input:focus {
  outline: none;
  border-color: rgba(125, 79, 43, 0.42);
  box-shadow: 0 0 0 3px rgba(125, 79, 43, 0.14);
}

.qa-submit-button {
  white-space: nowrap;
}

.qa-suggest-group {
  justify-content: flex-start;
}

.qa-loading-panel {
  display: flex;
  align-items: center;
  gap: 10px;
}

.qa-loading-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #7d4f2b;
  box-shadow: 0 0 0 0 rgba(125, 79, 43, 0.55);
  animation: pulse 1.2s infinite;
}

.qa-result-layout {
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.9fr);
  align-items: start;
}

.qa-answer-main {
  line-height: 1.75;
  color: #2f2218;
  font-size: 1.02rem;
}

.qa-details {
  margin-top: 12px;
}

.qa-details pre {
  margin: 8px 0 0;
  padding: 12px;
  border-radius: 10px;
  background: rgba(248, 242, 233, 0.8);
  border: 1px solid rgba(111, 74, 46, 0.16);
  overflow-x: auto;
}

.qa-confidence-card {
  display: grid;
  gap: 4px;
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(250, 245, 236, 0.82);
  border: 1px solid rgba(111, 74, 46, 0.16);
}

.qa-confidence-card strong {
  font-size: 1.3rem;
}

.qa-side-block {
  margin-top: 12px;
}

.qa-side-block h3 {
  margin: 0 0 8px;
  font-size: 1rem;
}

.qa-related-list {
  display: grid;
  gap: 8px;
}

.qa-related-item {
  border: 1px solid rgba(111, 74, 46, 0.14);
  border-radius: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.72);
}

.qa-related-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.qa-related-item p {
  margin: 6px 0 0;
  color: #5d4a38;
  font-size: 0.92rem;
}

.qa-empty-panel h2 {
  margin: 0 0 10px;
}

.qa-empty-panel p {
  margin: 0;
  color: #5d4a38;
  line-height: 1.7;
}

.qa-empty-panel p + p {
  margin-top: 8px;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(125, 79, 43, 0.45);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(125, 79, 43, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(125, 79, 43, 0);
  }
}

@media (max-width: 980px) {
  .qa-result-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .qa-input-row {
    grid-template-columns: 1fr;
  }
}
</style>
