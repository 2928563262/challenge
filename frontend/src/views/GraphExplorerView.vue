<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  fetchGraphEntityDetail,
  fetchGraphShowcase,
  fetchGraphSummary,
  predictNer,
  predictRelation,
  saveAnnotationCandidate,
  searchCorpus,
  searchGraphEntities,
} from "../services/api";
import type {
  CorpusEntry,
  GraphEntity,
  GraphEntityDetail,
  GraphRelation,
  GraphShowcaseCase,
  GraphSummary,
  NerPrediction,
  NerPredictionEntity,
  RelationPrediction,
} from "../types/api";

interface SessionGraphNode {
  key: string;
  entity: NerPredictionEntity;
  matches: GraphEntity[];
  x: number;
  y: number;
}

interface SessionGraphEdge {
  key: string;
  headKey: string;
  tailKey: string;
  label: string;
  confidence: number;
}

const route = useRoute();
const router = useRouter();

const graphSummary = ref<GraphSummary | null>(null);
const showcaseCases = ref<GraphShowcaseCase[]>([]);
const selectedEntityDetail = ref<GraphEntityDetail | null>(null);
const nerPrediction = ref<NerPrediction | null>(null);
const predictedGraphMatches = ref<Record<string, GraphEntity[]>>({});
const relationPrediction = ref<RelationPrediction | null>(null);
const relationHistory = ref<RelationPrediction[]>([]);
const exportMessage = ref("");
const savingCandidate = ref(false);
const batchRelationPredicting = ref(false);

const loadingGraphSummary = ref(false);
const loadingShowcase = ref(false);
const searching = ref(false);
const loadingEntityDetail = ref(false);
const predictingNer = ref(false);
const resolvingPredictedEntities = ref(false);
const relationPredicting = ref(false);

const graphError = ref("");
const searchError = ref("");
const showcaseError = ref("");
const nerError = ref("");
const relationPredictError = ref("");
const relationBatchMessage = ref("");

const keyword = ref("桂枝汤");
const entityType = ref("FORMULA");
const nerInputText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationInputText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationHeadKey = ref("");
const relationTailKey = ref("");
const searchResults = ref<GraphEntity[]>([]);
const searchTotal = ref(0);
const corpusResults = ref<CorpusEntry[]>([]);
const corpusTotal = ref(0);

const entityTypeOptions = [
  { label: "方剂", value: "FORMULA" },
  { label: "证候", value: "SYNDROME" },
  { label: "症状", value: "SYMPTOM" },
  { label: "中药", value: "HERB" },
  { label: "治法", value: "THERAPY" },
  { label: "服法", value: "ADMINISTRATION" },
];

const relationLabels: Record<string, string> = {
  SYNDROME_HAS_SYMPTOM: "证候具有症状",
  SYNDROME_TO_FORMULA: "证候对应方剂",
  FORMULA_CONTAINS_HERB: "方剂包含中药",
  FORMULA_HAS_ADMINISTRATION: "方剂对应服法",
  NO_RELATION: "无稳定关系",
};

const relationPairPriority: Record<string, number> = {
  "SYNDROME->FORMULA": 0,
  "SYNDROME->SYMPTOM": 1,
  "FORMULA->HERB": 2,
  "FORMULA->ADMINISTRATION": 3,
};

const entityTypeLabels: Record<string, string> = {
  FORMULA: "方剂",
  SYNDROME: "证候",
  SYMPTOM: "症状",
  HERB: "中药",
  THERAPY: "治法",
  ADMINISTRATION: "服法",
};

const quickStats = computed(() => {
  if (!graphSummary.value) {
    return [];
  }
  return [
    { label: "节点", value: graphSummary.value.entity_node_count.toLocaleString("zh-CN") },
    { label: "关系", value: graphSummary.value.entity_relation_count.toLocaleString("zh-CN") },
    { label: "证据边", value: graphSummary.value.clause_mention_count.toLocaleString("zh-CN") },
  ];
});

const predictedEntities = computed(() => nerPrediction.value?.entities ?? []);

const predictedTypeBreakdown = computed(() => {
  const counts = predictedEntities.value.reduce<Record<string, number>>((accumulator, entity) => {
    accumulator[entity.type] = (accumulator[entity.type] || 0) + 1;
    return accumulator;
  }, {});
  return Object.entries(counts);
});

const predictionMatchSummary = computed(() => {
  const matchedCount = predictedEntities.value.filter((entity) => getPredictedMatches(entity).length > 0).length;
  return {
    total: predictedEntities.value.length,
    matched: matchedCount,
    unmatched: Math.max(predictedEntities.value.length - matchedCount, 0),
  };
});

const selectedHeadEntity = computed(() => getPredictedEntityByKey(relationHeadKey.value));
const selectedTailEntity = computed(() => getPredictedEntityByKey(relationTailKey.value));
const canRunRelation = computed(() => Boolean(selectedHeadEntity.value && selectedTailEntity.value && relationInputText.value.trim()));
const batchRelationPairs = computed(() => {
  const pairs: Array<{
    key: string;
    head: NerPredictionEntity;
    tail: NerPredictionEntity;
    priority: number;
    enabled: boolean;
  }> = [];
  predictedEntities.value.forEach((head, headIndex) => {
    predictedEntities.value.forEach((tail, tailIndex) => {
      if (headIndex === tailIndex) {
        return;
      }
      const pairKey = `${head.type}->${tail.type}`;
      if (!(pairKey in relationPairPriority)) {
        return;
      }
      pairs.push({
        key: `${predictedEntityKey(head)}__${predictedEntityKey(tail)}`,
        head,
        tail,
        priority: relationPairPriority[pairKey],
        enabled: true,
      });
    });
  });
  return pairs.sort((left, right) => {
    if (left.priority !== right.priority) {
      return left.priority - right.priority;
    }
    return left.head.start - right.head.start || left.tail.start - right.tail.start;
  });
});
const canRunBatchRelation = computed(() => Boolean(batchRelationPairs.value.length > 0 && relationInputText.value.trim()));
const selectedBatchPairs = ref<Set<string>>(new Set());
const selectedBatchCount = computed(() => selectedBatchPairs.value.size);

function toggleBatchPair(pairKey: string) {
  const newSet = new Set(selectedBatchPairs.value);
  if (newSet.has(pairKey)) {
    newSet.delete(pairKey);
  } else {
    newSet.add(pairKey);
  }
  selectedBatchPairs.value = newSet;
}

function selectAllBatchPairs() {
  selectedBatchPairs.value = new Set(batchRelationPairs.value.map((p) => p.key));
}

function clearAllBatchPairs() {
  selectedBatchPairs.value = new Set();
}

const sessionGraphNodes = computed<SessionGraphNode[]>(() => {
  const entities = predictedEntities.value;
  const radius = 34;
  return entities.map((entity, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(entities.length, 1) - Math.PI / 2;
    return {
      key: predictedEntityKey(entity),
      entity,
      matches: getPredictedMatches(entity),
      x: Number((50 + Math.cos(angle) * radius).toFixed(2)),
      y: Number((50 + Math.sin(angle) * radius).toFixed(2)),
    };
  });
});

const sessionGraphEdges = computed<SessionGraphEdge[]>(() => {
  return relationHistory.value
    .filter((item) => item.label !== "NO_RELATION")
    .map((item) => ({
      key: `${item.head.start}-${item.head.end}-${item.tail.start}-${item.tail.end}-${item.label}`,
      headKey: predictedEntityKey(item.head),
      tailKey: predictedEntityKey(item.tail),
      label: item.label,
      confidence: item.confidence,
    }));
});

const sessionGraphLines = computed(() => {
  const nodeLookup = new Map(sessionGraphNodes.value.map((node) => [node.key, node]));
  return sessionGraphEdges.value
    .map((edge) => {
      const head = nodeLookup.get(edge.headKey);
      const tail = nodeLookup.get(edge.tailKey);
      if (!head || !tail) {
        return null;
      }
      return {
        ...edge,
        x1: head.x,
        y1: head.y,
        x2: tail.x,
        y2: tail.y,
        midX: Number(((head.x + tail.x) / 2).toFixed(2)),
        midY: Number(((head.y + tail.y) / 2).toFixed(2)),
      };
    })
    .filter(Boolean) as Array<SessionGraphEdge & { x1: number; y1: number; x2: number; y2: number; midX: number; midY: number }>;
});

const sessionGraphExportPayload = computed(() => ({
  text: nerPrediction.value?.text ?? relationInputText.value.trim(),
  exported_at: new Date().toISOString(),
  node_count: sessionGraphNodes.value.length,
  edge_count: sessionGraphEdges.value.length,
  nodes: sessionGraphNodes.value.map((node) => ({
    key: node.key,
    text: node.entity.text,
    type: node.entity.type,
    start: node.entity.start,
    end: node.entity.end,
    match_count: node.matches.length,
    best_match: node.matches[0]
      ? {
          entity_id: node.matches[0].entity_id,
          name: node.matches[0].name,
          entity_type: node.matches[0].entity_type,
        }
      : null,
  })),
  edges: relationHistory.value.map((item) => ({
    head: item.head,
    tail: item.tail,
    label: item.label,
    confidence: item.confidence,
    top_predictions: item.top_predictions,
  })),
}));
const networkNodes = computed(() => {
  if (!selectedEntityDetail.value) {
    return [] as Array<{ entity: GraphEntity; relation?: GraphRelation; x: number; y: number; accent: string }>;
  }

  const center = {
    entity: selectedEntityDetail.value.entity,
    x: 50,
    y: 50,
    accent: "center",
  };

  const relations = [
    ...selectedEntityDetail.value.outgoing_relations.map((relation) => ({ relation, entity: relation.related_entity })),
    ...selectedEntityDetail.value.incoming_relations.map((relation) => ({ relation, entity: relation.related_entity })),
  ].slice(0, 8);

  const radius = 34;
  const peripherals = relations.map((item, index, list) => {
    const angle = (Math.PI * 2 * index) / Math.max(list.length, 1) - Math.PI / 2;
    return {
      entity: item.entity,
      relation: item.relation,
      x: Number((50 + Math.cos(angle) * radius).toFixed(2)),
      y: Number((50 + Math.sin(angle) * radius).toFixed(2)),
      accent: item.relation.direction === "outgoing" ? "outgoing" : "incoming",
    };
  });

  return [center, ...peripherals];
});

const chainSummary = computed(() => {
  if (!selectedEntityDetail.value) {
    return [] as string[];
  }

  const entity = selectedEntityDetail.value.entity;
  const incoming = selectedEntityDetail.value.incoming_relations;
  const outgoing = selectedEntityDetail.value.outgoing_relations;

  if (entity.entity_type === "FORMULA") {
    const syndromes = incoming.filter((item) => item.relation_type === "SYNDROME_TO_FORMULA").map((item) => item.related_entity.name);
    const herbs = outgoing.filter((item) => item.relation_type === "FORMULA_CONTAINS_HERB").map((item) => item.related_entity.name);
    const administrations = outgoing.filter((item) => item.relation_type === "FORMULA_HAS_ADMINISTRATION").map((item) => item.related_entity.name);

    return [
      syndromes.length ? `证候: ${syndromes.slice(0, 4).join("、")}` : "证候: 暂无明确证候链路",
      herbs.length ? `中药: ${herbs.slice(0, 6).join("、")}` : "中药: 暂无药味关系",
      administrations.length ? `服法: ${administrations.slice(0, 3).join("、")}` : "服法: 暂无服法关系",
    ];
  }

  return [
    `实体类型: ${entityTypeLabels[entity.entity_type] || entity.entity_type}`,
    `入边数量: ${selectedEntityDetail.value.stats.incoming_relation_count}`,
    `出边数量: ${selectedEntityDetail.value.stats.outgoing_relation_count}`,
  ];
});

function formatEntityType(entityTypeName: string) {
  return entityTypeLabels[entityTypeName] || entityTypeName;
}

function formatRelationType(relationType: string) {
  return relationLabels[relationType] || relationType;
}

function predictedEntityKey(entity: NerPredictionEntity) {
  return `${entity.type}-${entity.start}-${entity.end}-${entity.text}`;
}

function getPredictedEntityByKey(key: string) {
  return predictedEntities.value.find((entity) => predictedEntityKey(entity) === key) || null;
}

function getPredictedMatches(entity: NerPredictionEntity) {
  return predictedGraphMatches.value[predictedEntityKey(entity)] ?? [];
}

function entityPreviewText(entity: NerPredictionEntity) {
  return `${entity.text} · ${formatEntityType(entity.type)} · ${entity.start}-${entity.end}`;
}

function graphCandidateSummary(candidate: GraphEntity) {
  return `提及 ${candidate.mention_count} 次 · 覆盖 ${candidate.record_count} 条`;
}

function assignRelationEntity(role: "head" | "tail", entity: NerPredictionEntity) {
  relationPrediction.value = null;
  relationPredictError.value = "";
  relationBatchMessage.value = "";
  if (role === "head") {
    relationHeadKey.value = predictedEntityKey(entity);
    if (relationTailKey.value === relationHeadKey.value) {
      relationTailKey.value = "";
    }
    return;
  }

  relationTailKey.value = predictedEntityKey(entity);
  if (relationHeadKey.value === relationTailKey.value) {
    relationHeadKey.value = "";
  }
}

function autoSelectRelationPair(entities: NerPredictionEntity[]) {
  const syndrome = entities.find((entity) => entity.type === "SYNDROME");
  const formula = entities.find((entity) => entity.type === "FORMULA");
  const symptom = entities.find((entity) => entity.type === "SYMPTOM");
  if (syndrome && formula) {
    relationHeadKey.value = predictedEntityKey(syndrome);
    relationTailKey.value = predictedEntityKey(formula);
    return;
  }
  if (syndrome && symptom) {
    relationHeadKey.value = predictedEntityKey(syndrome);
    relationTailKey.value = predictedEntityKey(symptom);
    return;
  }
  relationHeadKey.value = entities[0] ? predictedEntityKey(entities[0]) : "";
  relationTailKey.value = entities[1] ? predictedEntityKey(entities[1]) : "";
}

function recordRelationPrediction(prediction: RelationPrediction) {
  const key = `${prediction.head.start}-${prediction.head.end}-${prediction.tail.start}-${prediction.tail.end}`;
  const filtered = relationHistory.value.filter((item) => `${item.head.start}-${item.head.end}-${item.tail.start}-${item.tail.end}` !== key);
  relationHistory.value = [...filtered, prediction];
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

async function loadEntityDetail(entityId: string, updateRoute = true) {
  loadingEntityDetail.value = true;
  graphError.value = "";
  try {
    selectedEntityDetail.value = await fetchGraphEntityDetail(entityId, {
      relationLimit: 8,
      evidenceLimit: 8,
    });
    if (updateRoute) {
      await router.replace({ query: { ...route.query, entityId } });
    }
  } catch {
    graphError.value = "实体详情加载失败，请稍后重试。";
  } finally {
    loadingEntityDetail.value = false;
  }
}

async function runSearch(updateRoute = true) {
  const normalizedKeyword = keyword.value.trim();
  if (!normalizedKeyword) {
    searchError.value = "请输入关键词后再检索。";
    return;
  }

  searching.value = true;
  searchError.value = "";

  try {
    const [graphPayload, corpusPayload] = await Promise.all([
      searchGraphEntities({ keyword: normalizedKeyword, entityType: entityType.value, limit: 10 }),
      searchCorpus(normalizedKeyword),
    ]);

    searchResults.value = graphPayload.results;
    searchTotal.value = graphPayload.total;
    corpusResults.value = corpusPayload.results;
    corpusTotal.value = corpusPayload.total;

    let targetEntityId = typeof route.query.entityId === "string" ? route.query.entityId : "";
    const selectedExists = graphPayload.results.some((item) => item.entity_id === targetEntityId);
    if (!selectedExists) {
      targetEntityId = graphPayload.results[0]?.entity_id || "";
    }

    if (updateRoute) {
      await router.replace({
        query: {
          keyword: normalizedKeyword,
          entityType: entityType.value,
          entityId: targetEntityId || undefined,
        },
      });
    }

    if (targetEntityId) {
      await loadEntityDetail(targetEntityId, false);
    } else {
      selectedEntityDetail.value = null;
    }
  } catch {
    searchError.value = "检索失败，请检查后端服务、图谱接口或跨域配置。";
  } finally {
    searching.value = false;
  }
}
async function resolvePredictedEntitiesToGraph(prediction: NerPrediction) {
  resolvingPredictedEntities.value = true;
  const matches: Record<string, GraphEntity[]> = {};

  try {
    await Promise.all(
      prediction.entities.map(async (entity) => {
        const key = predictedEntityKey(entity);
        try {
          const payload = await searchGraphEntities({ keyword: entity.text, entityType: entity.type, limit: 3 });
          matches[key] = payload.results;
        } catch {
          matches[key] = [];
        }
      }),
    );
    predictedGraphMatches.value = matches;
  } finally {
    resolvingPredictedEntities.value = false;
  }
}

async function runNerPrediction() {
  const text = nerInputText.value.trim();
  if (!text) {
    nerError.value = "请输入待抽取条文。";
    return;
  }

  predictingNer.value = true;
  nerError.value = "";
  relationPredictError.value = "";
  relationBatchMessage.value = "";
  relationPrediction.value = null;
  relationHistory.value = [];
  exportMessage.value = "";
  relationInputText.value = text;
  try {
    const prediction = await predictNer(text);
    nerPrediction.value = prediction;
    autoSelectRelationPair(prediction.entities);
    await resolvePredictedEntitiesToGraph(prediction);
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      nerError.value = String(error.response?.data?.detail || "NER 抽取失败，请确认模型检查点已加载。");
    } else {
      nerError.value = "NER 抽取失败，请稍后重试。";
    }
  } finally {
    predictingNer.value = false;
  }
}

async function runRelationPrediction() {
  if (!selectedHeadEntity.value || !selectedTailEntity.value) {
    relationPredictError.value = "请先从抽取结果里选择头实体和尾实体。";
    return;
  }
  if (predictedEntityKey(selectedHeadEntity.value) === predictedEntityKey(selectedTailEntity.value)) {
    relationPredictError.value = "头实体和尾实体不能相同。";
    return;
  }
  if (!relationInputText.value.trim()) {
    relationPredictError.value = "请输入关系判断文本。";
    return;
  }

  relationPredicting.value = true;
  relationPredictError.value = "";
  relationBatchMessage.value = "";
  relationPrediction.value = null;

  try {
    const prediction = await predictRelation({
      text: relationInputText.value.trim(),
      head: selectedHeadEntity.value,
      tail: selectedTailEntity.value,
    });
    relationPrediction.value = prediction;
    recordRelationPrediction(prediction);
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      relationPredictError.value = String(error.response?.data?.detail || "关系预测失败，请确认 RE 检查点已加载。");
    } else {
      relationPredictError.value = "关系预测失败，请稍后重试。";
    }
  } finally {
    relationPredicting.value = false;
  }
}

async function runSelectedBatchRelationPrediction() {
  if (!relationInputText.value.trim()) {
    relationPredictError.value = "请输入关系判断文本。";
    return;
  }
  const selectedPairs = batchRelationPairs.value.filter((p) => selectedBatchPairs.value.has(p.key));
  if (!selectedPairs.length) {
    relationPredictError.value = "请至少选择一组实体对。";
    return;
  }

  batchRelationPredicting.value = true;
  relationPredictError.value = "";
  relationBatchMessage.value = "";
  relationPrediction.value = null;

  const results: RelationPrediction[] = [];
  let failedCount = 0;

  try {
    for (const pair of selectedPairs) {
      try {
        const prediction = await predictRelation({
          text: relationInputText.value.trim(),
          head: pair.head,
          tail: pair.tail,
        });
        recordRelationPrediction(prediction);
        results.push(prediction);
      } catch {
        failedCount += 1;
      }
    }

    const preferred = [...results]
      .filter((item) => item.label !== "NO_RELATION")
      .sort((left, right) => right.confidence - left.confidence)[0];
    relationPrediction.value = preferred || results[0] || null;
    relationBatchMessage.value = `已批量判断 ${results.length} 组实体对，保留 ${results.filter((item) => item.label !== "NO_RELATION").length} 条非空关系${failedCount ? `，失败 ${failedCount} 组` : ""}。`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      relationPredictError.value = String(error.response?.data?.detail || "批量关系判断失败，请确认 RE 检查点已加载。");
    } else {
      relationPredictError.value = "批量关系判断失败，请稍后重试。";
    }
  } finally {
    batchRelationPredicting.value = false;
  }
}

async function openGraphCandidate(candidate: GraphEntity) {
  keyword.value = candidate.name;
  entityType.value = candidate.entity_type;
  await router.replace({
    query: {
      keyword: candidate.name,
      entityType: candidate.entity_type,
      entityId: candidate.entity_id,
    },
  });
}

async function openEntityInGraph(entity: NerPredictionEntity) {
  const bestMatch = getPredictedMatches(entity)[0];
  if (bestMatch) {
    await openGraphCandidate(bestMatch);
    return;
  }

  keyword.value = entity.text;
  entityType.value = entity.type;
  await runSearch();
}

async function jumpToPredictedEntity(entity: NerPredictionEntity) {
  await openEntityInGraph(entity);
}

function downloadSessionGraph() {
  if (!sessionGraphNodes.value.length) {
    exportMessage.value = "当前没有可导出的会话图数据。";
    return;
  }

  const safeStem = (nerPrediction.value?.text ?? relationInputText.value ?? "session-graph")
    .slice(0, 20)
    .replace(/[\\/:*?"<>|\s]+/g, "_");
  const fileName = `${safeStem || "session-graph"}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
  const blob = new Blob([JSON.stringify(sessionGraphExportPayload.value, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
  exportMessage.value = `已导出 ${sessionGraphNodes.value.length} 个节点、${sessionGraphEdges.value.length} 条关系。`;
}

async function saveSessionCandidate() {
  if (!sessionGraphNodes.value.length) {
    exportMessage.value = "当前没有可提交的候选记录。";
    return;
  }

  savingCandidate.value = true;
  try {
    const payload = await saveAnnotationCandidate({
      source_text: String(sessionGraphExportPayload.value.text || relationInputText.value || ""),
      source_page: "explore",
      session_payload: sessionGraphExportPayload.value as Record<string, unknown>,
    });
    exportMessage.value = `已保存候选记录 ${payload.record_id}。`;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      exportMessage.value = String(error.response?.data?.detail || "候选记录保存失败，请检查后端接口。");
    } else {
      exportMessage.value = "候选记录保存失败，请稍后重试。";
    }
  } finally {
    savingCandidate.value = false;
  }
}

async function usePredictionAsSearchSeed(entity: NerPredictionEntity) {
  keyword.value = entity.text;
  entityType.value = entity.type;
  await router.replace({
    query: {
      keyword: entity.text,
      entityType: entity.type,
      entityId: undefined,
    },
  });
}

async function applyRouteState() {
  const routeKeyword = typeof route.query.keyword === "string" ? route.query.keyword : "";
  const routeEntityType = typeof route.query.entityType === "string" ? route.query.entityType : "";
  const routeEntityId = typeof route.query.entityId === "string" ? route.query.entityId : "";

  keyword.value = routeKeyword || "桂枝汤";
  entityType.value = routeEntityType || "FORMULA";

  await runSearch(false);

  if (routeEntityId && selectedEntityDetail.value?.entity.entity_id !== routeEntityId) {
    await loadEntityDetail(routeEntityId, false);
  }
}

async function openShowcaseCase(caseItem: GraphShowcaseCase) {
  keyword.value = caseItem.entity.name;
  entityType.value = caseItem.entity.entity_type;
  await router.replace({
    query: {
      keyword: caseItem.entity.name,
      entityType: caseItem.entity.entity_type,
      entityId: caseItem.entity.entity_id,
    },
  });
}

onMounted(async () => {
  await Promise.all([loadGraphSummary(), loadShowcase()]);
  await applyRouteState();
  await runNerPrediction();
});

watch(
  () => route.fullPath,
  async () => {
    await applyRouteState();
  },
);
</script>
<template>
  <main class="page-shell knowledge-page explorer-page">
    <section class="panel explorer-hero">
      <div class="panel-header explorer-header">
        <div>
          <p class="panel-kicker">Graph Explorer</p>
          <h1>图谱浏览</h1>
          <p class="hero-description explorer-description">
            在这里按实体类型检索知识节点，查看入边出边、原文条文证据，并把模型抽到的实体自动映射到已有图谱节点，再辅助判断关系。
          </p>
        </div>
        <div class="explorer-actions">
          <RouterLink to="/" class="ghost-link">返回总览</RouterLink>
        </div>
      </div>

      <div class="quick-stat-row">
        <article v-for="item in quickStats" :key="item.label" class="mini-stat-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>
    </section>

    <section class="panel compact-showcase-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">Quick Cases</p>
          <h2>一键演示案例</h2>
        </div>
      </div>
      <p v-if="showcaseError" class="status-text error">{{ showcaseError }}</p>
      <div v-else class="compact-showcase-list">
        <button v-for="caseItem in showcaseCases" :key="caseItem.slug" type="button" class="compact-case-chip" @click="openShowcaseCase(caseItem)">
          <strong>{{ caseItem.entity.name }}</strong>
          <span>{{ caseItem.title }}</span>
        </button>
      </div>
    </section>

    <section class="content-grid model-assisted-layout">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Model Assisted Extraction</p>
            <h2>条文智能抽取</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runNerPrediction">
          <textarea v-model="nerInputText" rows="5" placeholder="输入一条《伤寒论》条文，系统会用当前 NER 模型先抽取实体。" />
          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="predictingNer">{{ predictingNer ? "抽取中..." : "运行 NER 抽取" }}</button>
          </div>
        </form>

        <p v-if="nerError" class="status-text error">{{ nerError }}</p>
        <p v-else class="status-text">当前这一步使用已经训练好的 NER 基线，把条文中的证候、症状、方剂等实体先找出来，再自动尝试映射到已有图谱节点。</p>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Prediction Result</p>
            <h2>模型抽取结果</h2>
          </div>
        </div>

        <p v-if="!nerPrediction" class="status-text">先运行一次抽取，这里会显示实体结果和类型分布。</p>
        <template v-else>
          <div class="prediction-summary-strip">
            <div class="breakdown-item"><span>抽取实体</span><strong>{{ predictionMatchSummary.total }}</strong></div>
            <div class="breakdown-item"><span>成功映射</span><strong>{{ predictionMatchSummary.matched }}</strong></div>
            <div class="breakdown-item"><span>待人工判断</span><strong>{{ predictionMatchSummary.unmatched }}</strong></div>
          </div>

          <div class="breakdown-list predicted-breakdown-list">
            <div v-for="([type, count]) in predictedTypeBreakdown" :key="type" class="breakdown-item">
              <span>{{ formatEntityType(type) }}</span>
              <strong>{{ count }}</strong>
            </div>
          </div>

          <p v-if="resolvingPredictedEntities" class="status-text">正在把抽取结果映射到图谱节点...</p>

          <div class="entity-chip-list explorer-entity-chip-list">
            <div v-for="entity in predictedEntities" :key="predictedEntityKey(entity)" class="entity-chip mapped-entity-chip">
              <strong>{{ entity.text }}</strong>
              <span>{{ formatEntityType(entity.type) }}</span>
              <small>{{ entity.start }}-{{ entity.end }}</small>
              <p class="entity-preview-copy">{{ entityPreviewText(entity) }}</p>

              <div class="selection-strip">
                <span class="selection-pill" :class="{ active: relationHeadKey === predictedEntityKey(entity) }">头实体</span>
                <span class="selection-pill" :class="{ active: relationTailKey === predictedEntityKey(entity) }">尾实体</span>
              </div>

              <div class="candidate-panel">
                <p class="candidate-title">图谱候选节点</p>
                <div v-if="getPredictedMatches(entity).length" class="candidate-list">
                  <button v-for="candidate in getPredictedMatches(entity)" :key="candidate.entity_id" type="button" class="candidate-chip" @click="openGraphCandidate(candidate)">
                    <strong>{{ candidate.name }}</strong>
                    <span>{{ graphCandidateSummary(candidate) }}</span>
                  </button>
                </div>
                <p v-else class="candidate-empty">当前图谱里没有稳定命中，建议先用它作为检索词人工确认。</p>
              </div>

              <div class="entity-chip-actions">
                <button class="ghost-button mini-button" type="button" @click="assignRelationEntity('head', entity)">设为头实体</button>
                <button class="ghost-button mini-button" type="button" @click="assignRelationEntity('tail', entity)">设为尾实体</button>
                <button class="ghost-button mini-button" type="button" @click="usePredictionAsSearchSeed(entity)">设为检索词</button>
                <button class="primary-button mini-button" type="button" @click="jumpToPredictedEntity(entity)">打开最佳映射</button>
              </div>
            </div>
          </div>
        </template>
      </article>
    </section>

    <section class="content-grid relation-assistant-layout">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Relation Assistant</p>
            <h2>关系辅助判断</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runRelationPrediction">
          <textarea v-model="relationInputText" rows="4" placeholder="输入或确认当前关系判断用的条文文本。" />

          <div class="relation-batch-control">
            <div class="relation-batch-header">
              <span>可批量判断 {{ batchRelationPairs.length }} 组实体对（仅覆盖核心关系）</span>
              <div class="batch-actions">
                <button type="button" class="ghost-button mini-button" @click="selectAllBatchPairs">全选</button>
                <button type="button" class="ghost-button mini-button" @click="clearAllBatchPairs">清空</button>
              </div>
            </div>

            <div class="batch-pair-list">
              <div
                v-for="pair in batchRelationPairs"
                :key="pair.key"
                class="batch-pair-item"
                :class="{ selected: selectedBatchPairs.has(pair.key) }"
                @click="toggleBatchPair(pair.key)"
              >
                <span class="pair-check">{{ selectedBatchPairs.has(pair.key) ? '✓' : '○' }}</span>
                <span class="pair-head">{{ pair.head.text }} ({{ formatEntityType(pair.head.type) }})</span>
                <span class="pair-arrow">→</span>
                <span class="pair-tail">{{ pair.tail.text }} ({{ formatEntityType(pair.tail.type) }})</span>
              </div>
            </div>
          </div>

          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="relationPredicting || batchRelationPredicting || !canRunRelation">
              {{ relationPredicting ? '判断中...' : '运行关系判断' }}
            </button>
            <button
              class="ghost-button"
              type="button"
              :disabled="relationPredicting || batchRelationPredicting || !selectedBatchPairs.size"
              @click="runSelectedBatchRelationPrediction"
            >
              {{ batchRelationPredicting ? "批量判断中..." : `批量执行 (${selectedBatchPairs.size})` }}
            </button>
          </div>
        </form>

        <p v-if="relationPredictError" class="status-text error">{{ relationPredictError }}</p>
        <p v-else-if="relationBatchMessage" class="status-text">{{ relationBatchMessage }}</p>
        <p v-else class="status-text">当前关系模型只作为辅助判断，不直接覆盖规则结果。更适合帮助你快速判断"证候-方剂"或"证候-症状"是否成立。</p>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Relation Result</p>
            <h2>关系预测结果</h2>
          </div>
        </div>

        <p v-if="!relationPrediction" class="status-text">选择头尾实体后运行一次关系判断，这里会显示预测标签和候选分数。</p>
        <template v-else>
          <div class="relation-result-card">
            <div class="breakdown-item"><span>预测关系</span><strong>{{ formatRelationType(relationPrediction.label) }}</strong></div>
            <div class="breakdown-item"><span>置信度</span><strong>{{ relationPrediction.confidence.toFixed(4) }}</strong></div>
            <div class="breakdown-item"><span>头实体</span><strong>{{ relationPrediction.head.text }} / {{ formatEntityType(relationPrediction.head.type) }}</strong></div>
            <div class="breakdown-item"><span>尾实体</span><strong>{{ relationPrediction.tail.text }} / {{ formatEntityType(relationPrediction.tail.type) }}</strong></div>
          </div>

          <div class="dataset-split-grid relation-score-grid">
            <article v-for="item in relationPrediction.top_predictions" :key="item.label" class="dataset-split-card">
              <span>{{ formatRelationType(item.label) }}</span>
              <strong>{{ item.score.toFixed(4) }}</strong>
            </article>
          </div>
        </template>
      </article>
    </section>
    <section class="panel session-graph-panel">
      <div class="panel-header compact-header">
        <div>
          <p class="panel-kicker">Session Graph</p>
          <h2>本次条文临时会话图</h2>
        </div>
        <div class="session-action-group">
          <button type="button" class="ghost-button session-export-button" :disabled="!sessionGraphNodes.length || savingCandidate" @click="saveSessionCandidate">
            {{ savingCandidate ? "保存中..." : "提交候选记录" }}
          </button>
          <button type="button" class="ghost-button session-export-button" :disabled="!sessionGraphNodes.length || savingCandidate" @click="downloadSessionGraph">导出 JSON</button>
        </div>
      </div>

      <p v-if="!predictedEntities.length" class="status-text">先运行一次 NER 抽取，这里会根据本次条文临时组织实体与关系。</p>
      <template v-else>
        <p class="status-text">{{ exportMessage || '可将当前条文的临时节点、映射候选和关系判断导出为 JSON，方便后续复核或入库。' }}</p>
        <div class="session-graph-layout">
          <div class="session-graph-canvas">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="network-lines">
              <line v-for="edge in sessionGraphLines" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" class="session-graph-line" />
            </svg>

            <div v-for="edge in sessionGraphLines" :key="`${edge.key}-label`" class="session-graph-edge-label" :style="{ left: `${edge.midX}%`, top: `${edge.midY}%` }">
              {{ formatRelationType(edge.label) }}
            </div>

            <button
              v-for="node in sessionGraphNodes"
              :key="node.key"
              type="button"
              class="session-graph-node"
              :class="{ mapped: node.matches.length > 0 }"
              :style="{ left: `${node.x}%`, top: `${node.y}%` }"
              @click="openEntityInGraph(node.entity)"
            >
              <strong>{{ node.entity.text }}</strong>
              <span>{{ formatEntityType(node.entity.type) }}</span>
            </button>
          </div>

          <div class="session-graph-sidebar">
            <div class="session-side-block">
              <strong>实体节点</strong>
              <div class="session-side-list">
                <div v-for="node in sessionGraphNodes" :key="`${node.key}-item`" class="session-side-card">
                  <span>{{ formatEntityType(node.entity.type) }}</span>
                  <strong>{{ node.entity.text }}</strong>
                  <p>{{ node.matches.length ? `已映射 ${node.matches.length} 个候选` : '暂无映射候选' }}</p>
                </div>
              </div>
            </div>

            <div class="session-side-block">
              <strong>已判断关系</strong>
              <div class="session-side-list">
                <div v-if="!relationHistory.length" class="session-side-card empty">
                  <p>运行一次关系判断后，这里会累计本次条文的关系结果。</p>
                </div>
                <button
                  v-for="item in relationHistory"
                  :key="`${item.head.start}-${item.tail.start}-${item.label}`"
                  type="button"
                  class="session-side-card action-card"
                  @click="openEntityInGraph(item.head)"
                >
                  <span>{{ formatRelationType(item.label) }}</span>
                  <strong>{{ item.head.text }} -> {{ item.tail.text }}</strong>
                  <p>置信度 {{ item.confidence.toFixed(4) }}</p>
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </section>

    <section class="content-grid search-layout">
      <article class="panel search-panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Keyword Search</p>
            <h2>实体检索</h2>
          </div>
        </div>

        <form class="search-form search-form-stacked" @submit.prevent="runSearch()">
          <input v-model="keyword" type="text" placeholder="输入方剂、证候、症状或中药，例如：桂枝汤" />

          <div class="search-row">
            <div class="chip-group">
              <button v-for="option in entityTypeOptions" :key="option.value" type="button" class="filter-chip" :class="{ active: entityType === option.value }" @click="entityType = option.value">
                {{ option.label }}
              </button>
            </div>
            <button class="primary-button" type="submit" :disabled="searching">{{ searching ? '检索中...' : '开始检索' }}</button>
          </div>
        </form>

        <p v-if="searchError" class="status-text error">{{ searchError }}</p>
        <p v-else class="status-text">图谱命中 {{ searchTotal }} 个实体，条文命中 {{ corpusTotal }} 条。</p>

        <div class="entity-result-list">
          <button v-for="entity in searchResults" :key="entity.entity_id" class="entity-result-card" :class="{ active: selectedEntityDetail?.entity.entity_id === entity.entity_id }" type="button" @click="loadEntityDetail(entity.entity_id)">
            <div class="entity-result-head">
              <strong>{{ entity.name }}</strong>
              <span>{{ formatEntityType(entity.entity_type) }}</span>
            </div>
            <p>提及 {{ entity.mention_count }} 次 · 覆盖 {{ entity.record_count }} 条 · 首次出现 {{ entity.first_record_id }}</p>
          </button>
        </div>
      </article>

      <article class="panel network-panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Relation Preview</p>
            <h2>关系网络概览</h2>
          </div>
        </div>

        <p v-if="graphError" class="status-text error">{{ graphError }}</p>
        <p v-else-if="loadingEntityDetail" class="status-text">正在加载实体详情...</p>
        <p v-else-if="!selectedEntityDetail" class="status-text">先检索并选择一个实体，系统会展示它的关联关系与原文证据。</p>

        <template v-else>
          <div class="entity-focus-card">
            <div>
              <p class="entity-type-tag">{{ formatEntityType(selectedEntityDetail.entity.entity_type) }}</p>
              <h3>{{ selectedEntityDetail.entity.name }}</h3>
            </div>
            <div class="focus-metrics">
              <span>入边 {{ selectedEntityDetail.stats.incoming_relation_count }}</span>
              <span>出边 {{ selectedEntityDetail.stats.outgoing_relation_count }}</span>
              <span>证据 {{ selectedEntityDetail.stats.mention_count }}</span>
            </div>
          </div>

          <div class="network-map">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="network-lines">
              <line v-for="node in networkNodes.slice(1)" :key="`${selectedEntityDetail.entity.entity_id}-${node.entity.entity_id}`" x1="50" y1="50" :x2="node.x" :y2="node.y" class="network-line" />
            </svg>

            <div v-for="node in networkNodes" :key="node.entity.entity_id" class="network-node" :class="node.accent" :style="{ left: `${node.x}%`, top: `${node.y}%` }">
              <strong>{{ node.entity.name }}</strong>
              <span>{{ formatEntityType(node.entity.entity_type) }}</span>
            </div>
          </div>

          <div class="relation-columns">
            <div class="relation-column">
              <p class="column-title">典型链路</p>
              <div class="chain-list">
                <div v-for="item in chainSummary" :key="item" class="chain-item">{{ item }}</div>
              </div>
            </div>

            <div class="relation-column">
              <p class="column-title">主要关系</p>
              <div class="relation-list">
                <div v-for="relation in [...selectedEntityDetail.outgoing_relations, ...selectedEntityDetail.incoming_relations].slice(0, 8)" :key="`${relation.direction}-${relation.relation_type}-${relation.related_entity.entity_id}`" class="relation-item">
                  <span>{{ relation.direction === 'outgoing' ? '出边' : '入边' }}</span>
                  <strong>{{ formatRelationType(relation.relation_type) }}</strong>
                  <p>{{ relation.related_entity.name }} · 证据 {{ relation.evidence_count }}</p>
                </div>
              </div>
            </div>
          </div>
        </template>
      </article>
    </section>

    <section class="content-grid evidence-layout">
      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Evidence Traceback</p>
            <h2>原文证据回溯</h2>
          </div>
        </div>

        <p v-if="!selectedEntityDetail" class="status-text">选择一个实体后，这里会显示它在条文中的出现位置与证据片段。</p>
        <div v-else class="evidence-list">
          <article v-for="mention in selectedEntityDetail.mentions" :key="`${mention.clause_id}-${mention.start}-${mention.end}`" class="evidence-card">
            <div class="evidence-meta">
              <span>{{ mention.record_id }}</span>
              <span>{{ mention.line_number ? `行号 ${mention.line_number}` : '行号未知' }}</span>
              <span>{{ mention.entry_type || 'unknown' }}</span>
            </div>
            <p>{{ mention.clause_text }}</p>
          </article>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">Text Preview</p>
            <h2>条文检索结果</h2>
          </div>
        </div>

        <div class="result-list">
          <div v-for="entry in corpusResults" :key="entry.id" class="result-item">
            <div class="result-meta">
              <span>条文 #{{ entry.id }}</span>
              <span v-if="entry.formula_name">{{ entry.formula_name }}</span>
            </div>
            <p>{{ entry.text }}</p>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>
