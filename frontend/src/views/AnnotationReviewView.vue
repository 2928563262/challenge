<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  fetchAnnotationCandidateDetail,
  fetchAnnotationCandidates,
  updateAnnotationCandidateStatus,
} from "../services/api";
import type { AnnotationCandidateRecord } from "../types/api";

const route = useRoute();
const router = useRouter();

const records = ref<AnnotationCandidateRecord[]>([]);
const selectedRecord = ref<AnnotationCandidateRecord | null>(null);
const loadingList = ref(false);
const loadingDetail = ref(false);
const updatingStatus = ref(false);
const exportingAccepted = ref(false);
const errorMessage = ref("");
const actionMessage = ref("");

const statusFilter = ref("all");
const sourcePageFilter = ref("all");
const dateFrom = ref("");
const dateTo = ref("");
const minNodes = ref<number | null>(null);
const maxNodes = ref<number | null>(null);
const searchQuery = ref("");

const statusLabels: Record<string, string> = {
  pending: "待复核",
  reviewed: "已复核",
  accepted: "已采纳",
  rejected: "已拒绝",
};

const statusOptions = [
  { value: "all", label: "全部" },
  { value: "pending", label: "待复核" },
  { value: "reviewed", label: "已复核" },
  { value: "accepted", label: "已采纳" },
  { value: "rejected", label: "已拒绝" },
];

const sourcePageOptions = [
  { value: "all", label: "全部来源" },
  { value: "explore", label: "图谱浏览页" },
  { value: "models", label: "模型工作台" },
];

const sourcePageLabels: Record<string, string> = {
  explore: "图谱浏览页",
  models: "模型工作台",
};

const filteredRecords = computed(() => {
  let result = records.value;

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    result = result.filter((r) => r.record_id.toLowerCase().includes(q) || r.source_text.toLowerCase().includes(q));
  }

  if (statusFilter.value !== "all") {
    result = result.filter((r) => r.status === statusFilter.value);
  }
  if (sourcePageFilter.value !== "all") {
    result = result.filter((r) => r.source_page === sourcePageFilter.value);
  }

  if (dateFrom.value) {
    const fromDate = new Date(dateFrom.value);
    result = result.filter((r) => new Date(r.created_at) >= fromDate);
  }
  if (dateTo.value) {
    const toDate = new Date(dateTo.value);
    toDate.setHours(23, 59, 59, 999);
    result = result.filter((r) => new Date(r.created_at) <= toDate);
  }
  if (minNodes.value !== null) {
    result = result.filter((r) => r.node_count >= minNodes.value!);
  }
  if (maxNodes.value !== null) {
    result = result.filter((r) => r.node_count <= maxNodes.value!);
  }

  return result;
});

const batchSelected = ref<Set<string>>(new Set());
const bulkUpdating = ref(false);

function toggleBatchSelect(recordId: string) {
  const newSet = new Set(batchSelected.value);
  if (newSet.has(recordId)) {
    newSet.delete(recordId);
  } else {
    newSet.add(recordId);
  }
  batchSelected.value = newSet;
}

function clearBatchSelection() {
  batchSelected.value = new Set();
}

function copyRecordId(recordId: string) {
  navigator.clipboard.writeText(recordId).then(() => {
    actionMessage.value = "记录ID已复制到剪贴板。";
  }).catch(() => {
    actionMessage.value = "复制失败，请手动复制。";
  });
}

async function bulkUpdateStatus(status: string) {
  if (batchSelected.value.size === 0) {
    actionMessage.value = "请先选择要批量操作的记录。";
    return;
  }

  bulkUpdating.value = true;
  actionMessage.value = "";
  errorMessage.value = "";
  let successCount = 0;
  let failCount = 0;

  try {
    for (const recordId of batchSelected.value) {
      try {
        await updateAnnotationCandidateStatus(recordId, { status });
        successCount += 1;
      } catch {
        failCount += 1;
      }
    }
    await loadList();
    clearBatchSelection();
    actionMessage.value = `批量更新完成：成功 ${successCount} 条，失败 ${failCount} 条。`;
  } catch {
    errorMessage.value = "批量更新过程中出现错误。";
  } finally {
    bulkUpdating.value = false;
  }
}

const payloadNodes = computed(() => {
  const payload = selectedRecord.value?.session_payload;
  const nodes = payload && typeof payload === "object" ? (payload as Record<string, unknown>).nodes : undefined;
  return Array.isArray(nodes) ? nodes : [];
});

const payloadEdges = computed(() => {
  const payload = selectedRecord.value?.session_payload;
  const edges = payload && typeof payload === "object" ? (payload as Record<string, unknown>).edges : undefined;
  return Array.isArray(edges) ? edges : [];
});

function formatStatus(status: string) {
  return statusLabels[status] || status;
}

function syncRouteQuery(recordId?: string) {
  return router.replace({
    query: {
      ...route.query,
      status: statusFilter.value !== "all" ? statusFilter.value : undefined,
      recordId: recordId || undefined,
    },
  });
}

async function loadList() {
  loadingList.value = true;
  errorMessage.value = "";
  try {
    const statusParam = statusFilter.value === "all" ? undefined : statusFilter.value;
    const payload = await fetchAnnotationCandidates(30, statusParam);
    records.value = payload.results;
  } catch {
    errorMessage.value = "候选记录列表加载失败，请检查后端接口。";
  } finally {
    loadingList.value = false;
  }
}

async function loadDetail(recordId: string, updateRoute = true) {
  loadingDetail.value = true;
  errorMessage.value = "";
  actionMessage.value = "";
  try {
    selectedRecord.value = await fetchAnnotationCandidateDetail(recordId);
    if (updateRoute) {
      await syncRouteQuery(recordId);
    }
    records.value = records.value.map((item) => (item.record_id === recordId ? { ...item, ...selectedRecord.value! } : item));
  } catch {
    errorMessage.value = "候选记录详情加载失败。";
  } finally {
    loadingDetail.value = false;
  }
}

async function selectRecord(recordId: string) {
  await loadDetail(recordId);
}

async function updateStatus(status: string) {
  if (!selectedRecord.value) {
    return;
  }
  updatingStatus.value = true;
  errorMessage.value = "";
  actionMessage.value = "";
  try {
    const updated = await updateAnnotationCandidateStatus(selectedRecord.value.record_id, { status });
    selectedRecord.value = updated;
    if (statusFilter.value !== "all" && updated.status !== statusFilter.value) {
      await loadList();
      const nextRecordId = records.value[0]?.record_id || "";
      if (nextRecordId) {
        await loadDetail(nextRecordId, false);
      } else {
        selectedRecord.value = null;
        await syncRouteQuery();
      }
    } else {
      records.value = records.value.map((item) => (item.record_id === updated.record_id ? { ...item, ...updated } : item));
    }
    actionMessage.value = `状态已更新为${formatStatus(status)}。`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      errorMessage.value = String(error.response?.data?.detail || "状态更新失败。");
    } else {
      errorMessage.value = "状态更新失败。";
    }
  } finally {
    updatingStatus.value = false;
  }
}

async function exportAcceptedRecords() {
  exportingAccepted.value = true;
  errorMessage.value = "";
  actionMessage.value = "";
  try {
    const payload = await fetchAnnotationCandidates(100, "accepted");
    const exportPayload = {
      exported_at: new Date().toISOString(),
      total: payload.total,
      results: payload.results,
    };
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `accepted-candidates-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
    link.click();
    URL.revokeObjectURL(url);
    actionMessage.value = `已导出 ${payload.total} 条已采纳记录。`;
  } catch {
    errorMessage.value = "导出已采纳记录失败。";
  } finally {
    exportingAccepted.value = false;
  }
}

async function applyFilter(status: string, sourcePage?: string) {
  statusFilter.value = status;
  if (sourcePage !== undefined) {
    sourcePageFilter.value = sourcePage;
  }
  await loadList();
  const nextRecordId = filteredRecords.value[0]?.record_id || "";
  if (nextRecordId) {
    await loadDetail(nextRecordId, false);
  } else {
    selectedRecord.value = null;
  }
  await syncRouteQuery(nextRecordId || undefined);
}

async function applyRouteState() {
  const routeStatus = typeof route.query.status === "string" ? route.query.status : "";
  if (routeStatus && statusOptions.some((item) => item.value === routeStatus)) {
    statusFilter.value = routeStatus;
  }

  if (!records.value.length) {
    selectedRecord.value = null;
    return;
  }
  const routeRecordId = typeof route.query.recordId === "string" ? route.query.recordId : "";
  const targetRecordId = routeRecordId || records.value[0]?.record_id || "";
  if (!targetRecordId) {
    selectedRecord.value = null;
    return;
  }
  if (selectedRecord.value?.record_id === targetRecordId) {
    return;
  }
  await loadDetail(targetRecordId, false);
}

onMounted(async () => {
  await loadList();
  await applyRouteState();
});

watch(
  () => route.fullPath,
  async () => {
    const routeStatus = typeof route.query.status === "string" ? route.query.status : "";
    if ((routeStatus || "all") !== statusFilter.value) {
      statusFilter.value = routeStatus || "all";
      await loadList();
    }
    await applyRouteState();
  },
);
</script>

<template>
  <main class="page-shell annotation-page">
    <section class="panel explorer-hero">
      <div class="panel-header explorer-header">
        <div>
          <p class="panel-kicker">Annotation Review</p>
          <h1>候选记录复核</h1>
          <p class="hero-description explorer-description">
            查看从图谱浏览页提交的候选记录，对条文、实体节点和关系结果进行快速复核，并更新记录状态。
          </p>
        </div>
        <button type="button" class="ghost-button" :disabled="exportingAccepted" @click="exportAcceptedRecords">
          {{ exportingAccepted ? "导出中..." : "导出已采纳记录" }}
        </button>
      </div>
    </section>

    <section class="content-grid annotation-layout">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Candidates</p>
            <h2>候选记录列表</h2>
          </div>
        </div>

        <div class="annotation-toolbar">
          <input v-model="searchQuery" type="text" placeholder="搜索记录ID或原文..." class="search-input" />
          <div class="batch-actions" v-if="batchSelected.size > 0">
            <span class="batch-count">已选 {{ batchSelected.size }} 条</span>
            <button class="ghost-button mini-button" @click="clearBatchSelection">清空</button>
            <button class="ghost-button mini-button" :disabled="bulkUpdating" @click="bulkUpdateStatus('accepted')">批量采纳</button>
            <button class="ghost-button mini-button" :disabled="bulkUpdating" @click="bulkUpdateStatus('rejected')">批量拒绝</button>
          </div>
        </div>

        <div class="filter-row">
          <div class="chip-group annotation-filter-group">
            <button
              v-for="option in statusOptions"
              :key="option.value"
              type="button"
              class="filter-chip"
              :class="{ active: statusFilter === option.value }"
              @click="applyFilter(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div class="filter-row">
          <div class="date-range">
            <input v-model="dateFrom" type="date" class="date-input" placeholder="从" />
            <span>至</span>
            <input v-model="dateTo" type="date" class="date-input" placeholder="至" />
          </div>
          <div class="node-range">
            <input v-model.number="minNodes" type="number" placeholder="最少节点" class="range-input" min="0" />
            <span>至</span>
            <input v-model.number="maxNodes" type="number" placeholder="最多节点" class="range-input" min="0" />
          </div>
        </div>

        <p v-if="errorMessage && !selectedRecord" class="status-text error">{{ errorMessage }}</p>
        <p v-else-if="loadingList" class="status-text">正在加载候选记录...</p>
        <div v-else class="entity-result-list annotation-record-list">
          <button
            v-for="record in filteredRecords"
            :key="record.record_id"
            type="button"
            class="entity-result-card"
            :class="{ active: selectedRecord?.record_id === record.record_id, selected: batchSelected.has(record.record_id) }"
            @click="toggleBatchSelect(record.record_id); selectRecord(record.record_id)"
          >
            <div class="entity-result-head">
              <strong>{{ record.record_id }}</strong>
              <span>{{ formatStatus(record.status) }}</span>
            </div>
            <p>{{ record.text_preview }}</p>
            <div class="record-meta">
              <span>节点 {{ record.node_count }}</span>
              <span>关系 {{ record.edge_count }}</span>
              <span>{{ record.source_page === 'explore' ? '浏览页' : '工作台' }}</span>
            </div>
          </button>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Review Detail</p>
            <h2>记录详情</h2>
          </div>
          <div v-if="selectedRecord?.status === 'accepted'" class="accepted-badge">
            <span>✓ 已采纳</span>
          </div>
        </div>

        <p v-if="errorMessage && selectedRecord" class="status-text error">{{ errorMessage }}</p>
        <p v-else-if="actionMessage" class="status-text">{{ actionMessage }}</p>
        <p v-if="loadingDetail" class="status-text">正在加载详情...</p>
        <p v-else-if="!selectedRecord" class="status-text">先从左侧选择一条候选记录。</p>

        <template v-else>
          <div class="entity-focus-card annotation-summary-card" :class="selectedRecord.status">
            <div>
              <p class="entity-type-tag">{{ formatStatus(selectedRecord.status) }}</p>
              <h3>{{ selectedRecord.record_id }}</h3>
              <p class="entity-preview-copy">{{ selectedRecord.source_text }}</p>
            </div>
            <div class="focus-metrics">
              <span>节点 {{ selectedRecord.node_count }}</span>
              <span>关系 {{ selectedRecord.edge_count }}</span>
              <span>{{ selectedRecord.created_at.slice(0, 19).replace("T", " ") }}</span>
            </div>
          </div>

          <div v-if="selectedRecord.status === 'accepted'" class="accepted-actions">
            <button class="ghost-button mini-button" @click="exportAcceptedRecords">导出已采纳记录（JSON）</button>
            <button class="ghost-button mini-button" @click="copyRecordId(selectedRecord.record_id)">复制记录ID</button>
          </div>

          <div class="chip-group annotation-status-group">
            <button
              v-for="option in statusOptions.filter((item) => item.value !== 'all')"
              :key="option.value"
              type="button"
              class="filter-chip"
              :class="{ active: selectedRecord.status === option.value }"
              :disabled="updatingStatus || selectedRecord.status === option.value"
              @click="updateStatus(option.value)"
            >
              {{ updatingStatus && selectedRecord.status !== option.value ? "处理中..." : option.label }}
            </button>
          </div>

          <div class="relation-columns annotation-detail-columns">
            <div class="relation-column">
              <p class="column-title">实体节点</p>
              <div class="session-side-list">
                <div v-if="!payloadNodes.length" class="session-side-card empty">
                  <p>当前记录没有实体节点。</p>
                </div>
                <div v-for="(node, index) in payloadNodes" :key="`${selectedRecord.record_id}-node-${index}`" class="session-side-card">
                  <span>{{ String((node as Record<string, unknown>).type || "unknown") }}</span>
                  <strong>{{ String((node as Record<string, unknown>).text || "") }}</strong>
                  <p>位置 {{ String((node as Record<string, unknown>).start ?? "-") }} - {{ String((node as Record<string, unknown>).end ?? "-") }}</p>
                </div>
              </div>
            </div>

            <div class="relation-column">
              <p class="column-title">关系结果</p>
              <div class="session-side-list">
                <div v-if="!payloadEdges.length" class="session-side-card empty">
                  <p>当前记录没有关系结果。</p>
                </div>
                <div v-for="(edge, index) in payloadEdges" :key="`${selectedRecord.record_id}-edge-${index}`" class="session-side-card">
                  <span>{{ String((edge as Record<string, unknown>).label || "NO_RELATION") }}</span>
                  <strong>{{ String(((edge as Record<string, unknown>).head as Record<string, unknown> | undefined)?.text || "") }} -> {{ String(((edge as Record<string, unknown>).tail as Record<string, unknown> | undefined)?.text || "") }}</strong>
                  <p>置信度 {{ typeof (edge as Record<string, unknown>).confidence === "number" ? ((edge as Record<string, unknown>).confidence as number).toFixed(4) : '-' }}</p>
                </div>
              </div>
            </div>
          </div>

          <div class="relation-column annotation-payload-block">
            <p class="column-title">原始 Payload</p>
            <pre class="annotation-payload">{{ JSON.stringify(selectedRecord.session_payload || {}, null, 2) }}</pre>
          </div>
        </template>
      </article>
    </section>
  </main>
</template>
