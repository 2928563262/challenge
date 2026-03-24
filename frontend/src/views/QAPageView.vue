<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { askQuestion } from "../services/api";
import type { QAAnswer } from "../types/api";

const router = useRouter();

const questionInput = ref("");
const answer = ref<QAAnswer | null>(null);
const isLoading = ref(false);
const errorMessage = ref("");

const suggestionQuestions = ref([
  "桂枝汤包含哪些中药？",
  "中风有什么症状？",
  "桂枝汤主治什么证候？",
  "发热属于什么证候？",
]);

const isAsking = computed(() => isLoading.value && !answer.value);

async function handleAsk() {
  const question = questionInput.value.trim();
  if (!question) {
    errorMessage.value = "请输入问题";
    return;
  }

  isLoading.value = true;
  errorMessage.value = "";
  answer.value = null;

  try {
    const result = await askQuestion(question);
    answer.value = result;
    // 保留问题在输入框
  } catch (error: any) {
    errorMessage.value = error.response?.data?.detail || "提问失败，请检查后端服务是否正常。";
    console.error("Failed to ask question:", error);
  } finally {
    isLoading.value = false;
  }
}

function useSuggestion(question: string) {
  questionInput.value = question;
}

function goBack() {
  router.back();
}

// 简单的 Markdown 渲染
function renderMarkdown(text: string): string {
  if (!text) return "";
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.*?)__/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

// 实体类型格式化
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

onMounted(() => {
  // 可以预加载示例
});
</script>

<template>
  <main class="page-shell qa-page">
    <section class="page-header">
      <button class="back-button" @click="goBack">← 返回</button>
      <div>
        <h1>智能问答</h1>
        <p class="subtitle">基于《伤寒论》知识图谱的自然语言问答系统</p>
      </div>
    </section>

    <section class="qa-input-section">
      <div class="input-wrapper">
        <input
          v-model="questionInput"
          type="text"
          placeholder="请输入关于《伤寒论》的问题，例如：桂枝汤包含哪些中药？"
          class="question-input"
          @keyup.enter="handleAsk"
          :disabled="isAsking"
        />
        <button
          class="ask-button"
          @click="handleAsk"
          :disabled="isAsking || !questionInput.trim()"
        >
          {{ isLoading ? "思考中..." : "提问" }}
        </button>
      </div>

      <div class="suggestions" v-if="suggestionQuestions.length">
        <span class="suggest-label">试试：</span>
        <button
          v-for="q in suggestionQuestions"
          :key="q"
          class="suggestion-tag"
          @click="useSuggestion(q)"
        >
          {{ q }}
        </button>
      </div>
    </section>

    <!-- 错误提示 -->
    <div v-if="errorMessage" class="error-message">
      {{ errorMessage }}
    </div>

    <!-- 加载状态 -->
    <div v-if="isAsking" class="loading-state">
      <div class="spinner"></div>
      <p>正在分析问题并查询知识图谱...</p>
    </div>

    <!-- 答案展示 -->
    <section v-else-if="answer" class="answer-section">
      <div class="answer-card">
        <div class="answer-header">
          <h3>回答</h3>
          <span
            class="confidence-badge"
            :class="{
              high: answer.confidence >= 0.8,
              medium: answer.confidence >= 0.6,
              low: answer.confidence < 0.6
            }"
          >
            置信度: {{ (answer.confidence * 100).toFixed(1) }}%
          </span>
        </div>

        <div class="answer-content">
          <p class="answer-text" v-html="renderMarkdown(answer.answer)"></p>
        </div>

        <div v-if="answer.entities && answer.entities.length > 0" class="entities-section">
          <h4>识别到的实体</h4>
          <div class="entity-tags">
            <span v-for="(entity, idx) in answer.entities" :key="idx" class="entity-tag">
              {{ entity.text }} <small>({{ formatEntityType(entity.type) }})</small>
            </span>
          </div>
        </div>

        <div v-if="answer.related_entities && answer.related_entities.length > 0" class="related-section">
          <h4>知识图谱中的相关实体</h4>
          <ul class="related-list">
            <li v-for="entity in answer.related_entities" :key="entity.entity_id">
              <strong>{{ entity.name }}</strong>
              <span class="entity-type-tag">{{ formatEntityType(entity.entity_type) }}</span>
              <small class="mention-count">(提及 {{ entity.mention_count }} 次)</small>
            </li>
          </ul>
        </div>

        <details v-if="answer.cypher" class="cypher-details">
          <summary>查看查询语句</summary>
          <pre class="cypher-code">{{ answer.cypher }}</pre>
        </details>
        <div v-else class="cypher-hint">
          <small>注：当前使用模板生成答案，未执行 Cypher 查询。实际查询逻辑位于后端 qa/views.py 中。</small>
        </div>
      </div>
    </section>

    <!-- 使用说明 -->
    <section v-else class="help-section">
      <div class="help-card">
        <h3>使用说明</h3>
        <ul>
          <li>输入关于《伤寒论》的问题，例如方剂组成、证候症状、治法方药等。</li>
          <li>系统会自动识别问题中的实体，并在知识图谱中查找相关信息。</li>
          <li>回答会显示置信度，低置信度结果仅供参考。</li>
          <li>点击上方"试试"按钮快速体验常见问题。</li>
        </ul>
      </div>
    </section>
  </main>
</template>

<style scoped>
.qa-page {
  width: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 20px;
  min-height: 100vh;
  background: #fafafa;
}

.page-header {
  margin-bottom: 24px;
  position: relative;
  padding: 20px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e5e5;
}

.page-header h1 {
  font-size: 1.75rem;
  margin-bottom: 0.5rem;
  color: #2a2318;
  font-weight: 700;
}

.subtitle {
  color: #666;
  font-size: 1rem;
  margin: 0;
}

.back-button {
  position: absolute;
  left: 20px;
  top: 20px;
  padding: 8px 16px;
  background: #f5f2e9;
  border: 1px solid rgba(125, 79, 43, 0.2);
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  color: #2a2318;
  transition: all 0.2s;
}

.back-button:hover {
  background: #ede8dc;
}

.qa-input-section {
  background: #fff;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.question-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 1rem;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  background: #fafafa;
  color: #333;
  line-height: 1.5;
}

.question-input:focus {
  border-color: #7d4f2b;
  box-shadow: 0 0 0 3px rgba(125, 79, 43, 0.1);
  background: #fff;
}

.question-input::placeholder {
  color: #aaa;
}

.question-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.ask-button {
  padding: 12px 24px;
  background: #7d4f2b;
  color: #fff;
  border: none;
  border-radius: 999px;
  font-size: 1rem;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.25s ease;
  box-shadow: 0 4px 12px rgba(125, 79, 43, 0.2);
  align-self: flex-start;
}

.ask-button:hover:not(:disabled) {
  background: #8c5e34;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(125, 79, 43, 0.3);
}

.ask-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.suggest-label {
  font-size: 0.875rem;
  color: #666;
  font-weight: 500;
}

.suggestion-tag {
  padding: 8px 14px;
  background: #f5f2e9;
  border: 1px solid rgba(125, 79, 43, 0.15);
  border-radius: 999px;
  cursor: pointer;
  font-size: 0.85rem;
  color: #2a2318;
  transition: all 0.2s ease;
}

.suggestion-tag:hover {
  background: #ede8dc;
  border-color: rgba(125, 79, 43, 0.3);
  transform: translateY(-1px);
}

.error-message {
  padding: 12px 16px;
  background: #ffebee;
  border: 1px solid #ffcdd2;
  border-radius: 8px;
  color: #c62828;
  margin-bottom: 16px;
  font-size: 0.9rem;
}

.loading-state {
  text-align: center;
  padding: 3rem 2rem;
  color: #666;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e5e5;
}

.spinner {
  width: 40px;
  height: 40px;
  margin: 0 auto 1rem;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #7d4f2b;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.answer-section {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.answer-card {
  background: #fff;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(125, 79, 43, 0.06);
}

.answer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #eee;
}

.answer-header h3 {
  margin: 0;
  font-size: 1.25rem;
  color: #2a2318;
  font-weight: 700;
}

.confidence-badge {
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 0.85rem;
  font-weight: 600;
}

.confidence-badge.high {
  background: #e8f5e9;
  color: #2e7d32;
  border: 1px solid #c8e6c9;
}

.confidence-badge.medium {
  background: #fff3e0;
  color: #ef6c00;
  border: 1px solid #ffe0b2;
}

.confidence-badge.low {
  background: #ffebee;
  color: #c62828;
  border: 1px solid #ffcdd2;
}

.answer-content {
  margin-bottom: 20px;
}

.answer-text {
  font-size: 1.05rem;
  line-height: 1.8;
  color: #333;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.entities-section,
.related-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.entities-section h4,
.related-section h4 {
  margin: 0 0 12px 0;
  font-size: 1rem;
  color: #666;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.entity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  padding: 6px 12px;
  background: #e8eaf6;
  border-radius: 8px;
  font-size: 0.9rem;
  color: #3949ab;
  font-weight: 500;
  border: 1px solid #c5cae9;
}

.entity-tag small {
  color: #888;
  margin-left: 6px;
  font-size: 0.8rem;
}

.related-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.related-list li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #f5f2e9;
  border-radius: 8px;
  font-size: 0.9rem;
  border: 1px solid rgba(125, 79, 43, 0.1);
}

.entity-type-tag {
  padding: 2px 8px;
  background: rgba(125, 79, 43, 0.1);
  color: #7d4f2b;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.mention-count {
  color: #999;
  font-size: 0.8rem;
}

.cypher-details {
  margin-top: 20px;
  padding: 16px;
  background: #f8f8f8;
  border-radius: 8px;
  font-size: 0.85rem;
  border: 1px solid #e0e0e0;
}

.cypher-code {
  margin: 8px 0 0 0;
  padding: 12px;
  background: #2d2d2d;
  color: #f8f8f2;
  border-radius: 6px;
  overflow-x: auto;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.8rem;
  line-height: 1.5;
}

.cypher-hint {
  margin-top: 12px;
  padding: 10px;
  background: #fff8e1;
  border-radius: 6px;
  font-size: 0.85rem;
  color: #856404;
}

.help-section {
  text-align: center;
  padding: 3rem 2rem;
}

.help-card {
  background: #fff;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 2rem;
  box-shadow: 0 2px 8px rgba(125, 79, 43, 0.06);
  text-align: left;
  max-width: 600px;
  margin: 0 auto;
}

.help-card h3 {
  margin: 0 0 1rem 0;
  color: #2a2318;
  font-size: 1.25rem;
  font-weight: 700;
}

.help-card ul {
  margin: 0;
  padding-left: 1.5rem;
  color: #555;
  line-height: 1.8;
}

.help-card li {
  margin-bottom: 0.5rem;
}

@media (max-width: 768px) {
  .qa-page {
    padding: 16px 12px;
  }

  .page-header {
    padding: 16px;
  }

  .page-header h1 {
    font-size: 1.5rem;
    padding-left: 60px;
  }

  .back-button {
    left: 16px;
    top: 16px;
    padding: 6px 12px;
    font-size: 0.85rem;
  }

  .input-wrapper {
    flex-direction: column;
  }

  .ask-button {
    width: 100%;
    padding: 12px;
  }

  .answer-card {
    padding: 16px;
  }

  .answer-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .confidence-badge {
    align-self: flex-start;
  }
}
</style>