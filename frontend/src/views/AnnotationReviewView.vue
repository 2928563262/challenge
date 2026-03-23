<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import { formatEntityTypeLabel, formatRelationTypeLabel, formatStatusLabel } from "../i18n";
import {
  fetchAnnotationCandidateDetail,
  fetchAnnotationCandidates,
  updateAnnotationCandidate,
  updateAnnotationCandidateStatus,
} from "../services/api";
import type { AnnotationCandidateRecord } from "../types/api";

interface EditableNode {
  text: string;
  type: string;
  start: number;
  end: number;
  noteText: string;
}

interface EditableEdge {
  label: string;
  headText: string;
  headType: string;
  headStart: number;
  headEnd: number;
  tailText: string;
  tailType: string;
  tailStart: number;
  tailEnd: number;
  confidence: number;
  sourceMode: "model" | "manual";
}

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const records = ref<AnnotationCandidateRecord[]>([]);
const selectedRecord = ref<AnnotationCandidateRecord | null>(null);
const loadingList = ref(false);
const loadingDetail = ref(false);
const updatingStatus = ref(false);
const exportingAccepted = ref(false);
const savingEdits = ref(false);
const errorMessage = ref("");
const actionMessage = ref("");
const statusFilter = ref("all");

const editableSourceText = ref("");
const editableNodes = ref<EditableNode[]>([]);
const editableEdges = ref<EditableEdge[]>([]);

const statusOptions = [
  { value: "all", label: t("common.all") },
  { value: "pending", label: formatStatus("pending") },
  { value: "reviewed", label: formatStatus("reviewed") },
  { value: "accepted", label: formatStatus("accepted") },
  { value: "rejected", label: formatStatus("rejected") },
];

const entityTypeOptions = [
  { value: "SYNDROME", label: formatEntityType("SYNDROME") },
  { value: "SYMPTOM", label: formatEntityType("SYMPTOM") },
  { value: "FORMULA", label: formatEntityType("FORMULA") },
  { value: "HERB", label: formatEntityType("HERB") },
  { value: "THERAPY", label: formatEntityType("THERAPY") },
  { value: "ADMINISTRATION", label: formatEntityType("ADMINISTRATION") },
];

const relationOptions = [
  { value: "SYNDROME_HAS_SYMPTOM", label: formatRelationLabel("SYNDROME_HAS_SYMPTOM") },
  { value: "SYNDROME_TO_FORMULA", label: formatRelationLabel("SYNDROME_TO_FORMULA") },
  { value: "SYNDROME_TO_THERAPY", label: formatRelationLabel("SYNDROME_TO_THERAPY") },
  { value: "FORMULA_CONTAINS_HERB", label: formatRelationLabel("FORMULA_CONTAINS_HERB") },
  { value: "FORMULA_HAS_ADMINISTRATION", label: formatRelationLabel("FORMULA_HAS_ADMINISTRATION") },
];

const rawPayloadPreview = computed(() => {
  if (!selectedRecord.value) {
    return "{}";
  }
  return JSON.stringify(buildSessionPayload(), null, 2);
});

function formatStatus(status: string) {
  return formatStatusLabel(status);
}

function formatEntityType(type: string) {
  return formatEntityTypeLabel(type);
}

function formatRelationLabel(label: string) {
  return formatRelationTypeLabel(label);
}

function normalizeNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nodeSignature(node: Pick<EditableNode, "text" | "type" | "start" | "end">) {
  return `${node.type}|${node.text}|${node.start}|${node.end}`;
}

function cloneEditableNodes(record: AnnotationCandidateRecord | null) {
  const payload = record?.session_payload;
  const rawNodes = payload && typeof payload === "object" ? (payload as Record<string, unknown>).nodes : undefined;
  if (!Array.isArray(rawNodes)) {
    return [];
  }
  return rawNodes.map((node) => {
    const item = (node || {}) as Record<string, unknown>;
    return {
      text: String(item.text || ""),
      type: String(item.type || "SYMPTOM"),
      start: normalizeNumber(item.start, 0),
      end: normalizeNumber(item.end, 0),
      noteText: String(item.note_text || ""),
    } satisfies EditableNode;
  });
}

function cloneEditableEdges(record: AnnotationCandidateRecord | null) {
  const payload = record?.session_payload;
  const rawEdges = payload && typeof payload === "object" ? (payload as Record<string, unknown>).edges : undefined;
  if (!Array.isArray(rawEdges)) {
    return [];
  }
  return rawEdges.map((edge) => {
    const item = (edge || {}) as Record<string, unknown>;
    const head = ((item.head || {}) as Record<string, unknown>) || {};
    const tail = ((item.tail || {}) as Record<string, unknown>) || {};
    return {
      label: String(item.label || "SYNDROME_TO_FORMULA"),
      headText: String(head.text || ""),
      headType: String(head.type || "SYNDROME"),
      headStart: normalizeNumber(head.start, 0),
      headEnd: normalizeNumber(head.end, 0),
      tailText: String(tail.text || ""),
      tailType: String(tail.type || "FORMULA"),
      tailStart: normalizeNumber(tail.start, 0),
      tailEnd: normalizeNumber(tail.end, 0),
      confidence: normalizeNumber(item.confidence, 1),
      sourceMode: item.source_mode === "model" ? "model" : "manual",
    } satisfies EditableEdge;
  });
}

function syncEditorState(record: AnnotationCandidateRecord | null) {
  editableSourceText.value = record?.source_text || "";
  editableNodes.value = cloneEditableNodes(record);
  editableEdges.value = cloneEditableEdges(record);
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
    const payload = await fetchAnnotationCandidates(30, statusFilter.value === "all" ? undefined : statusFilter.value);
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
    syncEditorState(selectedRecord.value);
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
    syncEditorState(updated);
    if (statusFilter.value !== "all" && updated.status !== statusFilter.value) {
      await loadList();
      const nextRecordId = records.value[0]?.record_id || "";
      if (nextRecordId) {
        await loadDetail(nextRecordId, false);
      } else {
        selectedRecord.value = null;
        syncEditorState(null);
        await syncRouteQuery();
      }
    } else {
      records.value = records.value.map((item) => (item.record_id === updated.record_id ? { ...item, ...updated } : item));
    }
    actionMessage.value = `状态已更新为 ${formatStatus(status)}。`;
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

async function applyFilter(status: string) {
  statusFilter.value = status;
  await loadList();
  const nextRecordId = records.value[0]?.record_id || "";
  if (nextRecordId) {
    await loadDetail(nextRecordId, false);
  } else {
    selectedRecord.value = null;
    syncEditorState(null);
  }
  await syncRouteQuery(nextRecordId || undefined);
}

function addNode() {
  editableNodes.value.push({
    text: "",
    type: "SYMPTOM",
    start: 0,
    end: 0,
    noteText: "",
  });
}

function removeNode(index: number) {
  const target = editableNodes.value[index];
  if (!target) {
    return;
  }
  const signature = nodeSignature(target);
  editableNodes.value.splice(index, 1);
  editableEdges.value = editableEdges.value.filter(
    (edge) =>
      nodeSignature({ text: edge.headText, type: edge.headType, start: edge.headStart, end: edge.headEnd }) !== signature &&
      nodeSignature({ text: edge.tailText, type: edge.tailType, start: edge.tailStart, end: edge.tailEnd }) !== signature,
  );
}

function addEdge() {
  editableEdges.value.push({
    label: "SYNDROME_TO_FORMULA",
    headText: "",
    headType: "SYNDROME",
    headStart: 0,
    headEnd: 0,
    tailText: "",
    tailType: "FORMULA",
    tailStart: 0,
    tailEnd: 0,
    confidence: 1,
    sourceMode: "manual",
  });
}

function removeEdge(index: number) {
  editableEdges.value.splice(index, 1);
}

function applyNodeToEdge(edge: EditableEdge, role: "head" | "tail", node: EditableNode) {
  if (role === "head") {
    edge.headText = node.text;
    edge.headType = node.type;
    edge.headStart = node.start;
    edge.headEnd = node.end;
    return;
  }
  edge.tailText = node.text;
  edge.tailType = node.type;
  edge.tailStart = node.start;
  edge.tailEnd = node.end;
}

function handleNodeSelection(edge: EditableEdge, role: "head" | "tail", event: Event) {
  const target = event.target as HTMLSelectElement | null;
  const nodeIndex = Number(target?.value || "");
  if (!Number.isInteger(nodeIndex) || nodeIndex < 0 || nodeIndex >= editableNodes.value.length) {
    return;
  }
  applyNodeToEdge(edge, role, editableNodes.value[nodeIndex]);
}

function buildSessionPayload() {
  const basePayload =
    selectedRecord.value?.session_payload && typeof selectedRecord.value.session_payload === "object"
      ? { ...(selectedRecord.value.session_payload as Record<string, unknown>) }
      : {};

  const nodes = editableNodes.value
    .map((node) => ({
      key: `${node.type}-${node.start}-${node.end}-${node.text}`,
      text: node.text.trim(),
      type: node.type,
      start: node.start,
      end: node.end,
      note_text: node.noteText.trim(),
    }))
    .filter((node) => node.text && node.end > node.start);

  const edges = editableEdges.value
    .map((edge) => ({
      label: edge.label,
      head: {
        text: edge.headText.trim(),
        type: edge.headType,
        start: edge.headStart,
        end: edge.headEnd,
      },
      tail: {
        text: edge.tailText.trim(),
        type: edge.tailType,
        start: edge.tailStart,
        end: edge.tailEnd,
      },
      confidence: edge.confidence,
      source_mode: edge.sourceMode,
      top_predictions: edge.sourceMode === "manual" ? [{ label: edge.label, score: 1 }] : [],
    }))
    .filter(
      (edge) =>
        edge.label &&
        edge.head.text &&
        edge.tail.text &&
        edge.head.end > edge.head.start &&
        edge.tail.end > edge.tail.start,
    );

  return {
    ...basePayload,
    text: editableSourceText.value.trim(),
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
  };
}

async function saveEdits() {
  if (!selectedRecord.value) {
    return;
  }
  const sourceText = editableSourceText.value.trim();
  if (!sourceText) {
    errorMessage.value = "原始条文不能为空。";
    return;
  }

  const payload = buildSessionPayload();
  savingEdits.value = true;
  errorMessage.value = "";
  actionMessage.value = "";
  try {
    const updated = await updateAnnotationCandidate(selectedRecord.value.record_id, {
      source_text: sourceText,
      session_payload: payload,
    });
    selectedRecord.value = updated;
    syncEditorState(updated);
    records.value = records.value.map((item) => (item.record_id === updated.record_id ? { ...item, ...updated } : item));
    actionMessage.value = "记录内容已保存，节点和关系变更已同步写入候选记录。";
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      errorMessage.value = String(error.response?.data?.detail || "保存修改失败。");
    } else {
      errorMessage.value = "保存修改失败。";
    }
  } finally {
    savingEdits.value = false;
  }
}

async function applyRouteState() {
  const routeStatus = typeof route.query.status === "string" ? route.query.status : "";
  if (routeStatus && statusOptions.some((item) => item.value === routeStatus)) {
    statusFilter.value = routeStatus;
  }

  if (!records.value.length) {
    selectedRecord.value = null;
    syncEditorState(null);
    return;
  }
  const routeRecordId = typeof route.query.recordId === "string" ? route.query.recordId : "";
  const targetRecordId = routeRecordId || records.value[0]?.record_id || "";
  if (!targetRecordId) {
    selectedRecord.value = null;
    syncEditorState(null);
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
          <p class="panel-kicker">{{ t("annotation.heroKicker") }}</p>
          <h1>候选记录复核</h1>
          <p class="hero-description explorer-description">
            查看从图谱浏览页提交的候选记录，对条文、实体节点和关系结果进行快速复核，并在系统内直接修订后保存。
          </p>
        </div>
        <button type="button" class="ghost-button" :disabled="exportingAccepted" @click="exportAcceptedRecords">
          {{ exportingAccepted ? t("common.exporting") : t("common.exportAcceptedRecords") }}
        </button>
      </div>
    </section>

    <section class="content-grid annotation-layout">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("annotation.candidatesKicker") }}</p>
            <h2>候选记录列表</h2>
          </div>
        </div>

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

        <p v-if="errorMessage && !selectedRecord" class="status-text error">{{ errorMessage }}</p>
        <p v-else-if="loadingList" class="status-text">正在加载候选记录...</p>
        <div v-else class="entity-result-list annotation-record-list">
          <button
            v-for="record in records"
            :key="record.record_id"
            type="button"
            class="entity-result-card"
            :class="{ active: selectedRecord?.record_id === record.record_id }"
            @click="selectRecord(record.record_id)"
          >
            <div class="entity-result-head">
              <strong>{{ record.record_id }}</strong>
              <span>{{ formatStatus(record.status) }}</span>
            </div>
            <p>{{ record.text_preview }}</p>
            <p>节点 {{ record.node_count }} · 关系 {{ record.edge_count }}</p>
          </button>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("annotation.detailKicker") }}</p>
            <h2>记录详情</h2>
          </div>
          <button type="button" class="primary-button" :disabled="!selectedRecord || savingEdits" @click="saveEdits">
            {{ savingEdits ? t("common.saving") : "保存修改" }}
          </button>
        </div>

        <p v-if="errorMessage && selectedRecord" class="status-text error">{{ errorMessage }}</p>
        <p v-else-if="actionMessage" class="status-text">{{ actionMessage }}</p>
        <p v-if="loadingDetail" class="status-text">正在加载详情...</p>
        <p v-else-if="!selectedRecord" class="status-text">先从左侧选择一条候选记录。</p>

        <template v-else>
          <div class="entity-focus-card annotation-summary-card">
            <div class="annotation-summary-main">
              <p class="entity-type-tag">{{ formatStatus(selectedRecord.status) }}</p>
              <h3>{{ selectedRecord.record_id }}</h3>
              <textarea v-model="editableSourceText" class="annotation-source-text" rows="4" />
            </div>
            <div class="focus-metrics">
              <span>节点 {{ editableNodes.length }}</span>
              <span>关系 {{ editableEdges.length }}</span>
              <span>{{ selectedRecord.created_at.slice(0, 19).replace("T", " ") }}</span>
            </div>
          </div>

          <div class="chip-group annotation-status-group">
            <button
              v-for="option in statusOptions.filter((item) => item.value !== 'all')"
              :key="option.value"
              type="button"
              class="filter-chip"
              :class="{ active: selectedRecord.status === option.value }"
              :disabled="updatingStatus"
              @click="updateStatus(option.value)"
            >
              {{ updatingStatus && selectedRecord.status !== option.value ? "处理中..." : option.label }}
            </button>
          </div>

          <div class="relation-columns annotation-detail-columns">
            <div class="relation-column">
              <div class="annotation-section-header">
                <p class="column-title">实体节点</p>
                <button type="button" class="ghost-button mini-button" @click="addNode">新增实体</button>
              </div>
              <div class="session-side-list">
                <div v-if="!editableNodes.length" class="session-side-card empty">
                  <p>当前记录没有实体节点。</p>
                </div>
                <div
                  v-for="(node, index) in editableNodes"
                  :key="`${selectedRecord.record_id}-node-${index}`"
                  class="session-side-card annotation-edit-card"
                >
                  <div class="annotation-node-grid">
                    <input v-model="node.text" type="text" placeholder="实体文本" />
                    <select v-model="node.type">
                      <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                  </div>
                  <div class="annotation-position-grid">
                    <input v-model.number="node.start" type="number" min="0" placeholder="开始位置" />
                    <input v-model.number="node.end" type="number" min="0" placeholder="结束位置" />
                  </div>
                  <textarea v-model="node.noteText" rows="3" placeholder="备注或完整服法文本，可选" />
                  <div class="annotation-edit-actions">
                    <span>{{ formatEntityType(node.type) }}</span>
                    <button type="button" class="ghost-button mini-button danger-button" @click="removeNode(index)">
                      删除实体
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="relation-column">
              <div class="annotation-section-header">
                <p class="column-title">关系结果</p>
                <button type="button" class="ghost-button mini-button" @click="addEdge">新增关系</button>
              </div>
              <div class="session-side-list">
                <div v-if="!editableEdges.length" class="session-side-card empty">
                  <p>当前记录没有关系结果。</p>
                </div>
                <div
                  v-for="(edge, index) in editableEdges"
                  :key="`${selectedRecord.record_id}-edge-${index}`"
                  class="session-side-card annotation-edit-card"
                >
                  <select v-model="edge.label" class="annotation-relation-select">
                    <option v-for="option in relationOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>

                  <div class="annotation-edge-meta-grid">
                    <input v-model.number="edge.confidence" type="number" min="0" max="1" step="0.01" placeholder="置信度" />
                    <select v-model="edge.sourceMode">
                      <option value="manual">{{ t("common.manual") }}</option>
                      <option value="model">{{ t("common.model") }}</option>
                    </select>
                  </div>

                  <div class="annotation-edge-block">
                    <strong>头实体</strong>
                    <select class="annotation-node-select" @change="handleNodeSelection(edge, 'head', $event)">
                      <option value="">{{ t("common.fromExistingEntities") }}</option>
                      <option v-for="(node, nodeIndex) in editableNodes" :key="`head-${nodeIndex}`" :value="nodeIndex">
                        {{ node.text || `实体 ${nodeIndex + 1}` }} / {{ formatEntityType(node.type) }}
                      </option>
                    </select>
                    <div class="annotation-edge-entity-grid">
                      <input v-model="edge.headText" type="text" placeholder="头实体文本" />
                      <select v-model="edge.headType">
                        <option v-for="option in entityTypeOptions" :key="`head-type-${option.value}`" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </div>
                    <div class="annotation-position-grid">
                      <input v-model.number="edge.headStart" type="number" min="0" placeholder="开始位置" />
                      <input v-model.number="edge.headEnd" type="number" min="0" placeholder="结束位置" />
                    </div>
                  </div>

                  <div class="annotation-edge-block">
                    <strong>尾实体</strong>
                    <select class="annotation-node-select" @change="handleNodeSelection(edge, 'tail', $event)">
                      <option value="">{{ t("common.fromExistingEntities") }}</option>
                      <option v-for="(node, nodeIndex) in editableNodes" :key="`tail-${nodeIndex}`" :value="nodeIndex">
                        {{ node.text || `实体 ${nodeIndex + 1}` }} / {{ formatEntityType(node.type) }}
                      </option>
                    </select>
                    <div class="annotation-edge-entity-grid">
                      <input v-model="edge.tailText" type="text" placeholder="尾实体文本" />
                      <select v-model="edge.tailType">
                        <option v-for="option in entityTypeOptions" :key="`tail-type-${option.value}`" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </div>
                    <div class="annotation-position-grid">
                      <input v-model.number="edge.tailStart" type="number" min="0" placeholder="开始位置" />
                      <input v-model.number="edge.tailEnd" type="number" min="0" placeholder="结束位置" />
                    </div>
                  </div>

                  <div class="annotation-edit-actions">
                    <span>{{ formatRelationLabel(edge.label) }}</span>
                    <button type="button" class="ghost-button mini-button danger-button" @click="removeEdge(index)">
                      删除关系
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="relation-column annotation-payload-block">
            <p class="column-title">保存后 Payload 预览</p>
            <pre class="annotation-payload">{{ rawPayloadPreview }}</pre>
          </div>
        </template>
      </article>
    </section>
  </main>
</template>
