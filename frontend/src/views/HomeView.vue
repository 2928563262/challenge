<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { fetchGraphShowcase, fetchGraphSummary, fetchOverview } from "../services/api";
import type { CorpusOverview, GraphEntity, GraphShowcaseCase, GraphSummary } from "../types/api";

const router = useRouter();

const overview = ref<CorpusOverview | null>(null);
const graphSummary = ref<GraphSummary | null>(null);
const showcaseCases = ref<GraphShowcaseCase[]>([]);

const loadingOverview = ref(false);
const loadingGraphSummary = ref(false);
const loadingShowcase = ref(false);

const overviewError = ref("");
const graphError = ref("");
const showcaseError = ref("");

const entityTypeLabels: Record<string, string> = {
  FORMULA: "方剂",
  SYNDROME: "证候",
  SYMPTOM: "症状",
  HERB: "中药",
  THERAPY: "治法",
  ADMINISTRATION: "服法",
};

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

function formatEntityType(entityTypeName: string) {
  return entityTypeLabels[entityTypeName] || entityTypeName;
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
  await Promise.all([loadOverview(), loadGraphSummary(), loadShowcase()]);
});
</script>

<template>
  <main class="page-shell knowledge-page home-dashboard">
    <section class="hero-panel hero-grid">
      <div class="hero-copy">
        <p class="eyebrow">伤寒论知识图谱系统</p>
        <h1>《伤寒论》知识图谱与抽取系统</h1>
        <p class="hero-description">
          支持实体检索、关系浏览与原文证据回溯。
        </p>
        <div class="cta-row">
          <RouterLink to="/explore" class="primary-link-button">进入图谱浏览</RouterLink>
          <button class="ghost-button" type="button" @click="loadGraphSummary" :disabled="loadingGraphSummary">
            {{ loadingGraphSummary ? "刷新中..." : "刷新图谱摘要" }}
          </button>
        </div>
      </div>

        <div class="hero-side showcase-card">
          <div class="showcase-block">
            <span>当前版本</span>
            <strong>文本清洗 → 图谱导入 → 查询展示</strong>
          </div>
        </div>
    </section>

    <section class="stats-grid hero-stats">
      <article v-for="item in heroStats" :key="item.label" class="stat-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <section class="panel showcase-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">Case Showcase</p>
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
            <p class="panel-kicker">Graph Snapshot</p>
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
            <p class="panel-kicker">Top Entities</p>
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
            <p class="panel-kicker">Formula Preview</p>
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
            <p class="panel-kicker">Project Focus</p>
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
            <strong>典型案例答辩</strong>
            <p>固定案例卡片可以直接作为比赛和课堂演示入口，减少临场检索风险。</p>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>
