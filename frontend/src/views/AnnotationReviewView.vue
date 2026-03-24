<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import HoverHint from "../components/common/HoverHint.vue";
import StatePanel from "../components/common/StatePanel.vue";
import { formatEntityTypeLabel, formatRelationTypeLabel, formatStatusLabel } from "../i18n";
import {
  batchUpdateAnnotationCandidateStatus,
  deleteAnnotationCandidate,
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
const translate = t as unknown as (key: string, params?: Record<string, unknown>) => string;

function tf(key: string, params: Record<string, string | number>) {
  return String(translate(key, params));
}

const records = ref<AnnotationCandidateRecord[]>([]);
const selectedRecord = ref<AnnotationCandidateRecord | null>(null);
const loadingList = ref(false);
const loadingDetail = ref(false);
const updatingStatus = ref(false);
const exportingAccepted = ref(false);
const savingEdits = ref(false);
const deletingRecord = ref(false);
const batchingStatus = ref(false);
const errorMessage = ref("");
const actionMessage = ref("");
const statusFilter = ref("all");
const selectedRecordIds = ref<string[]>([]);
const keywordFilter = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const totalRecords = ref(0);
const totalPages = ref(0);

const editableSourceText = ref("");
const editableNodes = ref<EditableNode[]>([]);
const editableEdges = ref<EditableEdge[]>([]);

const statusOptions = computed(() => [
  { value: "all", label: t("common.all") },
  { value: "pending", label: formatStatus("pending") },
  { value: "reviewed", label: formatStatus("reviewed") },
  { value: "accepted", label: formatStatus("accepted") },
  { value: "rejected", label: formatStatus("rejected") },
]);

const hasPreviousPage = computed(() => currentPage.value > 1);
const hasNextPage = computed(() => currentPage.value < totalPages.value);

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

function formatStatus(status: string) {
  return formatStatusLabel(status);
}

function formatEntityType(type: string) {
  return formatEntityTypeLabel(type);
}

function formatRelationLabel(label: string) {
  return formatRelationTypeLabel(label);
}

function summarizeAutoPipelineRefresh(meta?: AnnotationCandidateRecord["auto_pipeline_refresh"]) {
  if (!meta || !meta.triggered) {
    return "";
  }
  if (!meta.ok) {
    return `${t("annotation.messages.autoPipelineFailed")}: ${meta.detail || t("common.unknown")}`;
  }
  const parts = [tf("annotation.messages.autoPipelineDone", { count: meta.export_record_count ?? 0 })];
  if (typeof meta.merge_ner_added_count === "number") {
    parts.push(`NER +${meta.merge_ner_added_count}`);
  }
  if (typeof meta.merge_relation_added_count === "number") {
    parts.push(`RE +${meta.merge_relation_added_count}`);
  }
  return parts.join("; ");
}

function summarizeAutoGraphRefresh(meta?: AnnotationCandidateRecord["auto_graph_refresh"]) {
  if (!meta || !meta.triggered) {
    return "";
  }
  if (!meta.ok) {
    return `${t("annotation.messages.autoGraphFailed")}: ${meta.detail || t("common.unknown")}`;
  }
  const name = meta.run_name || "graph-reviewed";
  const nodes = meta.entity_node_count ?? 0;
  const relations = meta.entity_relation_count ?? 0;
  return tf("annotation.messages.autoGraphDone", { name, nodes, relations });
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
      q: keywordFilter.value.trim() || undefined,
      page: currentPage.value > 1 ? String(currentPage.value) : undefined,
      recordId: recordId || undefined,
    },
  });
}

function isRecordSelected(recordId: string) {
  return selectedRecordIds.value.includes(recordId);
}

function toggleRecordSelection(recordId: string) {
  if (isRecordSelected(recordId)) {
    selectedRecordIds.value = selectedRecordIds.value.filter((item) => item !== recordId);
    return;
  }
  selectedRecordIds.value = [...selectedRecordIds.value, recordId];
}

function toggleSelectAllVisibleRecords() {
  const visibleIds = records.value.map((item) => item.record_id);
  if (!visibleIds.length) {
    selectedRecordIds.value = [];
    return;
  }
  const isAllSelected = visibleIds.every((recordId) => selectedRecordIds.value.includes(recordId));
  selectedRecordIds.value = isAllSelected ? [] : [...visibleIds];
}

function reconcileSelectionWithVisibleRecords() {
  const visibleIds = new Set(records.value.map((item) => item.record_id));
  selectedRecordIds.value = selectedRecordIds.value.filter((recordId) => visibleIds.has(recordId));
}

async function loadList() {
  loadingList.value = true;
  errorMessage.value = "";
  try {
    const payload = await fetchAnnotationCandidates({
      status: statusFilter.value === "all" ? undefined : statusFilter.value,
      page: currentPage.value,
      pageSize: pageSize.value,
      q: keywordFilter.value,
    });
    records.value = payload.results;
    totalRecords.value = payload.total;
    currentPage.value = payload.page || currentPage.value;
    totalPages.value = payload.total_pages || 0;
    reconcileSelectionWithVisibleRecords();
  } catch {
    errorMessage.value = t("annotation.errors.loadListFailed");
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
    errorMessage.value = t("annotation.errors.loadDetailFailed");
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
    const pipelineMessage = summarizeAutoPipelineRefresh(updated.auto_pipeline_refresh);
    const graphMessage = summarizeAutoGraphRefresh(updated.auto_graph_refresh);
    const combinedMessage = [pipelineMessage, graphMessage].filter(Boolean).join("; ");
    actionMessage.value = combinedMessage
      ? `${tf("annotation.messages.statusUpdated", { status: formatStatus(status) })} ${combinedMessage}`
      : tf("annotation.messages.statusUpdated", { status: formatStatus(status) });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      errorMessage.value = String(error.response?.data?.detail || t("annotation.errors.updateStatusFailed"));
    } else {
      errorMessage.value = t("annotation.errors.updateStatusFailed");
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
    const payload = await fetchAnnotationCandidates({ limit: 100, status: "accepted" });
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
    actionMessage.value = tf("annotation.messages.exportDone", { count: payload.total });
  } catch {
    errorMessage.value = t("annotation.errors.exportFailed");
  } finally {
    exportingAccepted.value = false;
  }
}

async function applyFilter(status: string) {
  statusFilter.value = status;
  currentPage.value = 1;
  selectedRecordIds.value = [];
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

async function applyKeywordSearch() {
  currentPage.value = 1;
  selectedRecordIds.value = [];
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

async function clearKeywordSearch() {
  if (!keywordFilter.value.trim()) {
    return;
  }
  keywordFilter.value = "";
  await applyKeywordSearch();
}

async function goToPage(targetPage: number) {
  if (targetPage < 1 || targetPage > totalPages.value || targetPage === currentPage.value) {
    return;
  }
  currentPage.value = targetPage;
  selectedRecordIds.value = [];
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

async function runBatchStatusUpdate(status: string) {
  if (!selectedRecordIds.value.length) {
    errorMessage.value = t("annotation.errors.batchNoSelection");
    return;
  }
  batchingStatus.value = true;
  errorMessage.value = "";
  actionMessage.value = "";
  try {
    const payload = await batchUpdateAnnotationCandidateStatus(selectedRecordIds.value, status);
    const pipelineMessage = summarizeAutoPipelineRefresh(payload.auto_pipeline_refresh as AnnotationCandidateRecord["auto_pipeline_refresh"]);
    const graphMessage = summarizeAutoGraphRefresh(payload.auto_graph_refresh as AnnotationCandidateRecord["auto_graph_refresh"]);
    const combinedMessage = [pipelineMessage, graphMessage].filter(Boolean).join("; ");
    actionMessage.value = combinedMessage
      ? `${tf("annotation.messages.batchStatusDone", { count: payload.updated_count, status: formatStatus(status) })} ${combinedMessage}`
      : tf("annotation.messages.batchStatusDone", { count: payload.updated_count, status: formatStatus(status) });

    selectedRecordIds.value = [];
    await loadList();
    if (selectedRecord.value) {
      const stillExists = records.value.some((item) => item.record_id === selectedRecord.value?.record_id);
      if (!stillExists) {
        const nextRecordId = records.value[0]?.record_id || "";
        if (nextRecordId) {
          await loadDetail(nextRecordId, false);
          await syncRouteQuery(nextRecordId);
        } else {
          selectedRecord.value = null;
          syncEditorState(null);
          await syncRouteQuery();
        }
      }
    }
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      errorMessage.value = String(error.response?.data?.detail || t("annotation.errors.batchStatusFailed"));
    } else {
      errorMessage.value = t("annotation.errors.batchStatusFailed");
    }
  } finally {
    batchingStatus.value = false;
  }
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
    errorMessage.value = t("annotation.errors.sourceTextRequired");
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
    const pipelineMessage = summarizeAutoPipelineRefresh(updated.auto_pipeline_refresh);
    const graphMessage = summarizeAutoGraphRefresh(updated.auto_graph_refresh);
    const combinedMessage = [pipelineMessage, graphMessage].filter(Boolean).join("; ");
    actionMessage.value = combinedMessage ? `${t("annotation.messages.saveDone")} ${combinedMessage}` : t("annotation.messages.saveDone");
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      errorMessage.value = String(error.response?.data?.detail || t("annotation.errors.saveFailed"));
    } else {
      errorMessage.value = t("annotation.errors.saveFailed");
    }
  } finally {
    savingEdits.value = false;
  }
}

async function deleteCurrentRecord() {
  if (!selectedRecord.value) {
    return;
  }
  if (!window.confirm(t("annotation.deleteConfirm"))) {
    return;
  }

  deletingRecord.value = true;
  errorMessage.value = "";
  actionMessage.value = "";
  const deletingRecordId = selectedRecord.value.record_id;
  try {
    await deleteAnnotationCandidate(deletingRecordId);
    await loadList();
    if (!records.value.length && currentPage.value > 1) {
      currentPage.value -= 1;
      await loadList();
    }
    const nextRecordId = records.value[0]?.record_id || "";
    if (nextRecordId) {
      await loadDetail(nextRecordId, false);
      await syncRouteQuery(nextRecordId);
    } else {
      selectedRecord.value = null;
      syncEditorState(null);
      await syncRouteQuery();
    }
    actionMessage.value = tf("annotation.messages.deleteDone", { recordId: deletingRecordId });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      errorMessage.value = String(error.response?.data?.detail || t("annotation.errors.deleteFailed"));
    } else {
      errorMessage.value = t("annotation.errors.deleteFailed");
    }
  } finally {
    deletingRecord.value = false;
  }
}

async function applyRouteState() {
  const routeStatus = typeof route.query.status === "string" ? route.query.status : "";
  const routeKeyword = typeof route.query.q === "string" ? route.query.q : "";
  const routePage = typeof route.query.page === "string" ? Number.parseInt(route.query.page, 10) : NaN;
  if (routeStatus && statusOptions.value.some((item) => item.value === routeStatus)) {
    statusFilter.value = routeStatus;
  }
  keywordFilter.value = routeKeyword || "";
  if (!Number.isNaN(routePage) && Number.isFinite(routePage) && routePage > 0) {
    currentPage.value = routePage;
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
  const routeStatus = typeof route.query.status === "string" ? route.query.status : "";
  if (routeStatus && statusOptions.value.some((item) => item.value === routeStatus)) {
    statusFilter.value = routeStatus;
  }
  keywordFilter.value = typeof route.query.q === "string" ? route.query.q : "";
  const routePage = typeof route.query.page === "string" ? Number.parseInt(route.query.page, 10) : NaN;
  if (!Number.isNaN(routePage) && Number.isFinite(routePage) && routePage > 0) {
    currentPage.value = routePage;
  }
  await loadList();
  await applyRouteState();
});

watch(
  () => route.fullPath,
  async () => {
    const routeStatus = typeof route.query.status === "string" ? route.query.status : "";
    const routeKeyword = typeof route.query.q === "string" ? route.query.q : "";
    const routePage = typeof route.query.page === "string" ? Number.parseInt(route.query.page, 10) : 1;
    const normalizedRoutePage = Number.isFinite(routePage) && routePage > 0 ? routePage : 1;
    if ((routeStatus || "all") !== statusFilter.value || routeKeyword !== keywordFilter.value || normalizedRoutePage !== currentPage.value) {
      statusFilter.value = routeStatus || "all";
      keywordFilter.value = routeKeyword || "";
      currentPage.value = normalizedRoutePage;
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
          <h1>{{ t("annotation.heroTitle") }}</h1>
          <p class="hero-description explorer-description">{{ t("annotation.heroDescription") }}</p>
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
            <h2>{{ t("annotation.candidatesTitle") }}</h2>
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

        <form class="annotation-search-row" @submit.prevent="applyKeywordSearch">
          <input v-model="keywordFilter" type="text" :placeholder="t('annotation.searchPlaceholder')" />
          <button type="submit" class="ghost-button mini-button">{{ t("annotation.searchAction") }}</button>
          <button type="button" class="ghost-button mini-button" @click="clearKeywordSearch">{{ t("annotation.clearSearchAction") }}</button>
        </form>

        <div class="annotation-batch-toolbar">
          <button type="button" class="ghost-button mini-button" @click="toggleSelectAllVisibleRecords">
            {{ t("annotation.selectAllVisible") }}
          </button>
          <span>{{ tf("annotation.selectedCount", { count: selectedRecordIds.length }) }}</span>
          <span>{{ tf("annotation.totalCount", { count: totalRecords }) }}</span>
          <button type="button" class="ghost-button mini-button" :disabled="batchingStatus" @click="runBatchStatusUpdate('accepted')">
            {{ batchingStatus ? t("annotation.batchRunning") : t("annotation.batchAccept") }}
          </button>
          <button type="button" class="ghost-button mini-button" :disabled="batchingStatus" @click="runBatchStatusUpdate('reviewed')">
            {{ t("annotation.batchReview") }}
          </button>
          <button type="button" class="ghost-button mini-button" :disabled="batchingStatus" @click="runBatchStatusUpdate('rejected')">
            {{ t("annotation.batchReject") }}
          </button>
        </div>

        <StatePanel v-if="errorMessage && !selectedRecord" tone="error">
          <p>{{ errorMessage }}</p>
        </StatePanel>
        <StatePanel v-else-if="loadingList" tone="info">
          <p>{{ t("annotation.loadingList") }}</p>
        </StatePanel>
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
              <input
                class="annotation-record-checkbox"
                type="checkbox"
                :checked="isRecordSelected(record.record_id)"
                @click.stop="toggleRecordSelection(record.record_id)"
              />
            </div>
            <p>{{ record.text_preview }}</p>
            <p>{{ tf("annotation.recordSummary", { nodeCount: record.node_count, edgeCount: record.edge_count }) }}</p>
          </button>
        </div>

        <div class="annotation-pagination-row">
          <button type="button" class="ghost-button mini-button" :disabled="!hasPreviousPage || loadingList" @click="goToPage(currentPage - 1)">
            {{ t("annotation.prevPage") }}
          </button>
          <span>{{ tf("annotation.pageSummary", { page: currentPage, totalPages: totalPages || 1 }) }}</span>
          <button type="button" class="ghost-button mini-button" :disabled="!hasNextPage || loadingList" @click="goToPage(currentPage + 1)">
            {{ t("annotation.nextPage") }}
          </button>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("annotation.detailKicker") }}</p>
            <h2>{{ t("annotation.detailTitle") }}</h2>
          </div>
          <div class="session-action-group">
            <button type="button" class="ghost-button danger-button" :disabled="!selectedRecord || deletingRecord" @click="deleteCurrentRecord">
              {{ deletingRecord ? t("annotation.deleting") : t("annotation.deleteRecord") }}
            </button>
            <button type="button" class="primary-button" :disabled="!selectedRecord || savingEdits" @click="saveEdits">
              {{ savingEdits ? t("common.saving") : t("annotation.saveEdits") }}
            </button>
          </div>
        </div>

        <StatePanel v-if="errorMessage && selectedRecord" tone="error">
          <p>{{ errorMessage }}</p>
        </StatePanel>
        <StatePanel v-else-if="actionMessage" tone="success">
          <p>{{ actionMessage }}</p>
        </StatePanel>
        <StatePanel v-if="loadingDetail" tone="info">
          <p>{{ t("annotation.loadingDetail") }}</p>
        </StatePanel>
        <div v-else-if="!selectedRecord" class="inline-hint-row">
          <HoverHint :text="t('annotation.noRecordSelected')" :aria-label="t('annotation.detailTitle')" />
        </div>

        <template v-else>
          <div class="entity-focus-card annotation-summary-card">
            <div class="annotation-summary-main">
              <p class="entity-type-tag">{{ formatStatus(selectedRecord.status) }}</p>
              <h3>{{ selectedRecord.record_id }}</h3>
              <textarea v-model="editableSourceText" class="annotation-source-text" rows="4" />
            </div>
            <div class="focus-metrics">
              <span>{{ tf("annotation.nodesCount", { count: editableNodes.length }) }}</span>
              <span>{{ tf("annotation.edgesCount", { count: editableEdges.length }) }}</span>
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
              {{ updatingStatus && selectedRecord.status !== option.value ? t("annotation.updating") : option.label }}
            </button>
          </div>

          <div class="relation-columns annotation-detail-columns">
            <div class="relation-column">
              <div class="annotation-section-header">
                <p class="column-title">{{ t("annotation.nodeSectionTitle") }}</p>
                <button type="button" class="ghost-button mini-button" @click="addNode">{{ t("annotation.addNode") }}</button>
              </div>
              <div class="session-side-list">
                <div v-if="!editableNodes.length" class="session-side-card empty">
                  <p>{{ t("annotation.noNodes") }}</p>
                </div>
                <div
                  v-for="(node, index) in editableNodes"
                  :key="`${selectedRecord.record_id}-node-${index}`"
                  class="session-side-card annotation-edit-card"
                >
                  <div class="annotation-node-grid">
                    <input v-model="node.text" type="text" :placeholder="t('annotation.nodeTextPlaceholder')" />
                    <select v-model="node.type">
                      <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                  </div>
                  <div class="annotation-position-grid">
                    <input v-model.number="node.start" type="number" min="0" :placeholder="t('annotation.startPos')" />
                    <input v-model.number="node.end" type="number" min="0" :placeholder="t('annotation.endPos')" />
                  </div>
                  <textarea v-model="node.noteText" rows="3" :placeholder="t('annotation.notePlaceholder')" />
                  <div class="annotation-edit-actions">
                    <span>{{ formatEntityType(node.type) }}</span>
                    <button type="button" class="ghost-button mini-button danger-button" @click="removeNode(index)">
                      {{ t("annotation.removeNode") }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="relation-column">
              <div class="annotation-section-header">
                <p class="column-title">{{ t("annotation.edgeSectionTitle") }}</p>
                <button type="button" class="ghost-button mini-button" @click="addEdge">{{ t("annotation.addEdge") }}</button>
              </div>
              <div class="session-side-list">
                <div v-if="!editableEdges.length" class="session-side-card empty">
                  <p>{{ t("annotation.noEdges") }}</p>
                </div>
                <div
                  v-for="(edge, index) in editableEdges"
                  :key="`${selectedRecord.record_id}-edge-${index}`"
                  class="session-side-card annotation-edit-card"
                >
                  <div class="annotation-edge-topline">
                    <select v-model="edge.label" class="annotation-relation-select">
                      <option v-for="option in relationOptions" :key="option.value" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                    <button type="button" class="ghost-button mini-button danger-button" @click="removeEdge(index)">
                      {{ t("annotation.removeEdge") }}
                    </button>
                  </div>

                  <div class="annotation-edge-meta-grid">
                    <label class="annotation-field">
                      <span>{{ t("models.confidence") }}</span>
                      <input v-model.number="edge.confidence" type="number" min="0" max="1" step="0.01" />
                    </label>
                    <label class="annotation-field">
                      <span>{{ t("annotation.sourceMode") }}</span>
                      <select v-model="edge.sourceMode">
                        <option value="manual">{{ t("common.manual") }}</option>
                        <option value="model">{{ t("common.model") }}</option>
                      </select>
                    </label>
                  </div>

                  <div class="annotation-edge-block">
                    <strong>{{ t("models.headEntity") }}</strong>
                    <select class="annotation-node-select" @change="handleNodeSelection(edge, 'head', $event)">
                      <option value="">{{ t("common.fromExistingEntities") }}</option>
                      <option v-for="(node, nodeIndex) in editableNodes" :key="`head-${nodeIndex}`" :value="nodeIndex">
                        {{ node.text || `${t("annotation.node")} ${nodeIndex + 1}` }} / {{ formatEntityType(node.type) }}
                      </option>
                    </select>
                    <div class="annotation-edge-entity-grid">
                      <input v-model="edge.headText" type="text" :placeholder="t('models.headEntityText')" />
                      <select v-model="edge.headType">
                        <option v-for="option in entityTypeOptions" :key="`head-type-${option.value}`" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </div>
                    <div class="annotation-position-grid">
                      <input v-model.number="edge.headStart" type="number" min="0" :placeholder="t('annotation.startPos')" />
                      <input v-model.number="edge.headEnd" type="number" min="0" :placeholder="t('annotation.endPos')" />
                    </div>
                  </div>

                  <div class="annotation-edge-block">
                    <strong>{{ t("models.tailEntity") }}</strong>
                    <select class="annotation-node-select" @change="handleNodeSelection(edge, 'tail', $event)">
                      <option value="">{{ t("common.fromExistingEntities") }}</option>
                      <option v-for="(node, nodeIndex) in editableNodes" :key="`tail-${nodeIndex}`" :value="nodeIndex">
                        {{ node.text || `${t("annotation.node")} ${nodeIndex + 1}` }} / {{ formatEntityType(node.type) }}
                      </option>
                    </select>
                    <div class="annotation-edge-entity-grid">
                      <input v-model="edge.tailText" type="text" :placeholder="t('models.tailEntityText')" />
                      <select v-model="edge.tailType">
                        <option v-for="option in entityTypeOptions" :key="`tail-type-${option.value}`" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </div>
                    <div class="annotation-position-grid">
                      <input v-model.number="edge.tailStart" type="number" min="0" :placeholder="t('annotation.startPos')" />
                      <input v-model.number="edge.tailEnd" type="number" min="0" :placeholder="t('annotation.endPos')" />
                    </div>
                  </div>

                  <div class="annotation-edit-actions">
                    <span>{{ formatRelationLabel(edge.label) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </article>
    </section>
  </main>
</template>
