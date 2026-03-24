<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import StatePanel from "../components/common/StatePanel.vue";
import { formatEntityTypeLabel, formatRelationTypeLabel } from "../i18n";
import {
  activateGraphVersion,
  deleteGraphManualRelation,
  fetchGraphClauseDetail,
  fetchGraphEntityDetail,
  fetchGraphEntityPathways,
  fetchGraphManualRelations,
  fetchGraphRegistry,
  fetchGraphShowcase,
  fetchGraphSummary,
  predictNer,
  predictRelation,
  saveAnnotationCandidate,
  searchGraphClauses,
  searchGraphEntities,
  suppressGraphRelation,
  upsertGraphManualRelation,
} from "../services/api";
import type {
  GraphClauseDetail,
  GraphClauseSearchRecord,
  GraphEntity,
  GraphEntityDetail,
  GraphManualRelationOverrideRecord,
  GraphEntityPathways,
  GraphRegistryStatus,
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
  recordKey: string;
  headKey: string;
  tailKey: string;
  label: string;
  confidence: number;
}

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

function tf(key: string, params: Record<string, string | number>) {
  let message = t(key);
  for (const [name, value] of Object.entries(params)) {
    message = message.split(`{${name}}`).join(String(value));
  }
  return message;
}

const graphSummary = ref<GraphSummary | null>(null);
const graphRegistry = ref<GraphRegistryStatus | null>(null);
const showcaseCases = ref<GraphShowcaseCase[]>([]);
const selectedEntityDetail = ref<GraphEntityDetail | null>(null);
const entityPathways = ref<GraphEntityPathways | null>(null);
const nerPrediction = ref<NerPrediction | null>(null);
const predictedGraphMatches = ref<Record<string, GraphEntity[]>>({});
const relationPrediction = ref<RelationPrediction | null>(null);
const relationHistory = ref<RelationPrediction[]>([]);
const manualRelationOverrides = ref<GraphManualRelationOverrideRecord[]>([]);
const loadingManualRelations = ref(false);
const applyingManualGraphRelation = ref(false);
const exportMessage = ref("");
const savingCandidate = ref(false);
const batchRelationPredicting = ref(false);

const loadingGraphSummary = ref(false);
const loadingGraphRegistry = ref(false);
const loadingShowcase = ref(false);
const searching = ref(false);
const loadingEntityDetail = ref(false);
const loadingEntityPathways = ref(false);
const predictingNer = ref(false);
const resolvingPredictedEntities = ref(false);
const relationPredicting = ref(false);

const graphError = ref("");
const pathwayError = ref("");
const searchError = ref("");
const showcaseError = ref("");
const nerError = ref("");
const relationPredictError = ref("");
const relationBatchMessage = ref("");
const manualGraphRelationError = ref("");
const manualGraphRelationMessage = ref("");
const graphVersionMessage = ref("");
const switchingGraphVersion = ref(false);

const keyword = ref("桂枝汤");
const entityType = ref("FORMULA");
const nerInputText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationInputText = ref("太阳病，头痛发热，汗出恶风，桂枝汤主之。");
const relationHeadKey = ref("");
const relationTailKey = ref("");
const manualRelationLabel = ref("SYNDROME_TO_FORMULA");
const graphManualRelationType = ref("SYNDROME_TO_FORMULA");
const graphManualRelationDirection = ref<"outgoing" | "incoming">("outgoing");
const graphManualRelationKeyword = ref("");
const graphManualRelationCandidates = ref<GraphEntity[]>([]);
const graphManualRelationTargetId = ref("");
const searchResults = ref<GraphEntity[]>([]);
const searchTotal = ref(0);
const clauseResults = ref<GraphClauseSearchRecord[]>([]);
const clauseTotal = ref(0);
const selectedClauseDetail = ref<GraphClauseDetail | null>(null);
const manualEntityText = ref("");
const manualEntityType = ref("SYMPTOM");
const manualEntityStart = ref("");
const manualEntityNote = ref("");
const manualEntityError = ref("");
const entityDisplayNotes = ref<Record<string, string>>({});
const selectedGraphVersionId = ref("");

const entityTypeOptions = [
  { label: formatEntityTypeLabel("FORMULA"), value: "FORMULA" },
  { label: formatEntityTypeLabel("SYNDROME"), value: "SYNDROME" },
  { label: formatEntityTypeLabel("SYMPTOM"), value: "SYMPTOM" },
  { label: formatEntityTypeLabel("HERB"), value: "HERB" },
  { label: formatEntityTypeLabel("THERAPY"), value: "THERAPY" },
  { label: formatEntityTypeLabel("ADMINISTRATION"), value: "ADMINISTRATION" },
];

const editableRelationOptions = [
  { label: formatRelationTypeLabel("SYNDROME_HAS_SYMPTOM"), value: "SYNDROME_HAS_SYMPTOM" },
  { label: formatRelationTypeLabel("SYNDROME_TO_FORMULA"), value: "SYNDROME_TO_FORMULA" },
  { label: `${formatRelationTypeLabel("SYNDROME_TO_THERAPY")}（${t("common.manual")}）`, value: "SYNDROME_TO_THERAPY" },
  { label: formatRelationTypeLabel("FORMULA_CONTAINS_HERB"), value: "FORMULA_CONTAINS_HERB" },
  { label: formatRelationTypeLabel("FORMULA_HAS_ADMINISTRATION"), value: "FORMULA_HAS_ADMINISTRATION" },
];

const relationPairPriority: Record<string, number> = {
  "SYNDROME->FORMULA": 0,
  "SYNDROME->SYMPTOM": 1,
  "FORMULA->HERB": 2,
  "FORMULA->ADMINISTRATION": 3,
};

const pathwayTypeLabels: Record<string, string> = {
  SYNDROME_TO_FORMULA: "explorer.pathType.syndromeFormula",
  SYMPTOM_SYNDROME_FORMULA: "explorer.pathType.symptomSyndromeFormula",
  SYNDROME_FORMULA_HERB: "explorer.pathType.syndromeFormulaHerb",
  SYNDROME_FORMULA_ADMINISTRATION: "explorer.pathType.syndromeFormulaAdministration",
  FORMULA_HERB: "explorer.pathType.formulaHerb",
  FORMULA_ADMINISTRATION: "explorer.pathType.formulaAdministration",
  SYNDROME_SYMPTOM: "explorer.pathType.syndromeSymptom",
};

const quickStats = computed(() => {
  if (!graphSummary.value) {
    return [];
  }
  return [
    { label: t("explorer.stats.nodes"), value: graphSummary.value.entity_node_count.toLocaleString("zh-CN") },
    { label: t("explorer.stats.relations"), value: graphSummary.value.entity_relation_count.toLocaleString("zh-CN") },
    { label: t("explorer.stats.evidence"), value: graphSummary.value.clause_mention_count.toLocaleString("zh-CN") },
  ];
});

const graphVersionOptions = computed(() => graphRegistry.value?.versions ?? []);
const graphQuerySourceLabel = computed(() => {
  const source = String((graphSummary.value as Record<string, unknown> | null)?.query_source || "").toLowerCase();
  if (source === "neo4j") {
    return t("explorer.graphVersion.querySourceNeo4j");
  }
  return t("explorer.graphVersion.querySourceCsv");
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
const selectedManualGraphTarget = computed(
  () => graphManualRelationCandidates.value.find((item) => item.entity_id === graphManualRelationTargetId.value) || null,
);
const canRunRelation = computed(() => Boolean(selectedHeadEntity.value && selectedTailEntity.value && relationInputText.value.trim()));
const batchRelationPairs = computed(() => {
  const pairs: Array<{ key: string; head: NerPredictionEntity; tail: NerPredictionEntity; priority: number }> = [];
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
const canRunBatchRelation = computed(() => Boolean(batchRelationPairs.value.length && relationInputText.value.trim()));

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
      recordKey: relationRecordKey(item),
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
    note_text: entityDisplayNotes.value[node.key] || "",
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
      syndromes.length ? tf("explorer.chain.syndrome", { value: syndromes.slice(0, 4).join("、") }) : t("explorer.chain.syndromeEmpty"),
      herbs.length ? tf("explorer.chain.herb", { value: herbs.slice(0, 6).join("、") }) : t("explorer.chain.herbEmpty"),
      administrations.length
        ? tf("explorer.chain.administration", { value: administrations.slice(0, 3).join("、") })
        : t("explorer.chain.administrationEmpty"),
    ];
  }

  return [
    tf("explorer.chain.entityType", { value: formatEntityType(entity.entity_type) }),
    tf("explorer.chain.incomingCount", { count: selectedEntityDetail.value.stats.incoming_relation_count }),
    tf("explorer.chain.outgoingCount", { count: selectedEntityDetail.value.stats.outgoing_relation_count }),
  ];
});

function formatEntityType(entityTypeName: string) {
  return formatEntityTypeLabel(entityTypeName);
}

function formatRelationType(relationType: string) {
  return formatRelationTypeLabel(relationType);
}

function formatEntryType(entryType: string | null) {
  if (!entryType) {
    return t("common.unknown");
  }
  if (entryType === "formula_entry") {
    return t("explorer.entryType.formula");
  }
  if (entryType === "syndrome_entry") {
    return t("explorer.entryType.syndrome");
  }
  return entryType;
}

function formatPathwayType(pathType: string) {
  return pathwayTypeLabels[pathType] ? t(pathwayTypeLabels[pathType]) : pathType;
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

function relationRecordKey(prediction: Pick<RelationPrediction, "head" | "tail">) {
  return `${prediction.head.start}-${prediction.head.end}-${prediction.tail.start}-${prediction.tail.end}`;
}

async function resolveSinglePredictedEntityToGraph(entity: NerPredictionEntity) {
  const key = predictedEntityKey(entity);
  try {
    const payload = await searchGraphEntities({ keyword: entity.text, entityType: entity.type, limit: 3 });
    predictedGraphMatches.value = {
      ...predictedGraphMatches.value,
      [key]: payload.results,
    };
  } catch {
    predictedGraphMatches.value = {
      ...predictedGraphMatches.value,
      [key]: [],
    };
  }
}

function entityPreviewText(entity: NerPredictionEntity) {
  return `${entity.text} · ${formatEntityType(entity.type)} · ${entity.start}-${entity.end}`;
}

function resetManualEntityForm() {
  manualEntityText.value = "";
  manualEntityType.value = "SYMPTOM";
  manualEntityStart.value = "";
  manualEntityNote.value = "";
  manualEntityError.value = "";
}

function resetManualRelationState() {
  manualRelationLabel.value = "SYNDROME_TO_FORMULA";
}

function findAllEntityPositions(text: string, needle: string) {
  const positions: number[] = [];
  let fromIndex = 0;
  while (fromIndex < text.length) {
    const foundIndex = text.indexOf(needle, fromIndex);
    if (foundIndex === -1) {
      break;
    }
    positions.push(foundIndex);
    fromIndex = foundIndex + 1;
  }
  return positions;
}

async function addManualEntity() {
  manualEntityError.value = "";
  exportMessage.value = "";

  if (!nerPrediction.value) {
    manualEntityError.value = t("explorer.errors.entityAddRunNerFirst");
    return;
  }

  const text = manualEntityText.value.trim();
  if (!text) {
    manualEntityError.value = t("explorer.errors.entityAddTextRequired");
    return;
  }

  const sourceText = nerPrediction.value.text;
  let start: number | null = null;

  if (manualEntityStart.value.trim()) {
    const parsed = Number.parseInt(manualEntityStart.value.trim(), 10);
    if (Number.isNaN(parsed) || parsed < 0) {
      manualEntityError.value = t("explorer.errors.entityAddInvalidStart");
      return;
    }
    start = parsed;
  } else {
    const positions = findAllEntityPositions(sourceText, text);
    if (!positions.length) {
      manualEntityError.value = t("explorer.errors.entityAddTextNotFound");
      return;
    }
    if (positions.length > 1) {
      manualEntityError.value = tf("explorer.errors.entityAddNeedStart", { text, count: positions.length });
      return;
    }
    start = positions[0];
  }

  const end = start + text.length;
  if (sourceText.slice(start, end) !== text) {
    manualEntityError.value = t("explorer.errors.entityAddStartMismatch");
    return;
  }

  const entity: NerPredictionEntity = {
    text,
    type: manualEntityType.value,
    start,
    end,
  };
  const entityKey = predictedEntityKey(entity);
  const duplicate = predictedEntities.value.some((item) => predictedEntityKey(item) === entityKey);
  if (duplicate) {
    manualEntityError.value = t("explorer.errors.entityAddDuplicate");
    return;
  }

  nerPrediction.value = {
    ...nerPrediction.value,
    entities: [...predictedEntities.value, entity].sort((left, right) => left.start - right.start || left.end - right.end),
  };

  if (manualEntityNote.value.trim()) {
    entityDisplayNotes.value = {
      ...entityDisplayNotes.value,
      [entityKey]: manualEntityNote.value.trim(),
    };
  }

  await resolveSinglePredictedEntityToGraph(entity);

  if (!relationHeadKey.value) {
    relationHeadKey.value = entityKey;
  } else if (!relationTailKey.value && relationHeadKey.value !== entityKey) {
    relationTailKey.value = entityKey;
  }

  exportMessage.value = tf("explorer.messages.entityAdded", { text });
  resetManualEntityForm();
}

function removePredictedEntity(target: NerPredictionEntity) {
  if (!nerPrediction.value) {
    return;
  }

  const targetKey = predictedEntityKey(target);
  const nextEntities = predictedEntities.value.filter((entity) => predictedEntityKey(entity) !== targetKey);
  nerPrediction.value = {
    ...nerPrediction.value,
    entities: nextEntities,
  };

  const nextMatches = { ...predictedGraphMatches.value };
  delete nextMatches[targetKey];
  predictedGraphMatches.value = nextMatches;

  const nextNotes = { ...entityDisplayNotes.value };
  delete nextNotes[targetKey];
  entityDisplayNotes.value = nextNotes;

  relationHistory.value = relationHistory.value.filter((item) => {
    const headKey = predictedEntityKey(item.head);
    const tailKey = predictedEntityKey(item.tail);
    return headKey !== targetKey && tailKey !== targetKey;
  });

  if (
    relationPrediction.value &&
    (predictedEntityKey(relationPrediction.value.head) === targetKey || predictedEntityKey(relationPrediction.value.tail) === targetKey)
  ) {
    relationPrediction.value = null;
  }

  if (relationHeadKey.value === targetKey) {
    relationHeadKey.value = "";
  }
  if (relationTailKey.value === targetKey) {
    relationTailKey.value = "";
  }

  relationBatchMessage.value = "";
  relationPredictError.value = "";
  exportMessage.value = tf("explorer.messages.entityRemoved", { text: target.text });
}

function graphCandidateSummary(candidate: GraphEntity) {
  return tf("explorer.messages.candidateSummary", {
    mentionCount: candidate.mention_count,
    recordCount: candidate.record_count,
  });
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
    manualRelationLabel.value = "SYNDROME_TO_FORMULA";
    return;
  }
  if (syndrome && symptom) {
    relationHeadKey.value = predictedEntityKey(syndrome);
    relationTailKey.value = predictedEntityKey(symptom);
    manualRelationLabel.value = "SYNDROME_HAS_SYMPTOM";
    return;
  }
  relationHeadKey.value = entities[0] ? predictedEntityKey(entities[0]) : "";
  relationTailKey.value = entities[1] ? predictedEntityKey(entities[1]) : "";
}

function recordRelationPrediction(prediction: RelationPrediction) {
  const key = relationRecordKey(prediction);
  const filtered = relationHistory.value.filter((item) => relationRecordKey(item) !== key);
  relationHistory.value = [...filtered, prediction];
}

function applyManualRelation() {
  if (!selectedHeadEntity.value || !selectedTailEntity.value) {
    relationPredictError.value = t("explorer.errors.manualRelationSelectEntities");
    return;
  }
  if (predictedEntityKey(selectedHeadEntity.value) === predictedEntityKey(selectedTailEntity.value)) {
    relationPredictError.value = t("explorer.errors.relationHeadTailSame");
    return;
  }

  const prediction: RelationPrediction = {
    text: relationInputText.value.trim(),
    sequence_text: relationInputText.value.trim(),
    head: selectedHeadEntity.value,
    tail: selectedTailEntity.value,
    label: manualRelationLabel.value,
    confidence: 1,
    top_predictions: [{ label: manualRelationLabel.value, score: 1 }],
    source_mode: "manual",
  };

  relationPredictError.value = "";
  relationBatchMessage.value =
    manualRelationLabel.value === "SYNDROME_TO_THERAPY"
      ? t("explorer.messages.manualTherapyRelationOnly")
      : t("explorer.messages.manualRelationOverwritten");
  relationPrediction.value = prediction;
  recordRelationPrediction(prediction);
}

function removeRelationPredictionByRecordKey(recordKey: string) {
  const target = relationHistory.value.find((item) => relationRecordKey(item) === recordKey);
  relationHistory.value = relationHistory.value.filter((item) => relationRecordKey(item) !== recordKey);
  if (relationPrediction.value && relationRecordKey(relationPrediction.value) === recordKey) {
    relationPrediction.value = null;
  }
  relationPredictError.value = "";
  relationBatchMessage.value = target ? tf("explorer.messages.relationRemoved", { relation: formatRelationType(target.label) }) : "";
}

function inspectRelationPrediction(prediction: RelationPrediction) {
  relationPrediction.value = prediction;
  relationHeadKey.value = predictedEntityKey(prediction.head);
  relationTailKey.value = predictedEntityKey(prediction.tail);
  manualRelationLabel.value = prediction.label === "NO_RELATION" ? "SYNDROME_TO_FORMULA" : prediction.label;
}

async function loadGraphSummary() {
  loadingGraphSummary.value = true;
  graphError.value = "";
  try {
    graphSummary.value = await fetchGraphSummary();
  } catch {
    graphError.value = t("home.errors.graphSummaryLoadFailed");
  } finally {
    loadingGraphSummary.value = false;
  }
}

async function loadGraphRegistry() {
  loadingGraphRegistry.value = true;
  graphError.value = "";
  try {
    graphRegistry.value = await fetchGraphRegistry();
    selectedGraphVersionId.value = graphRegistry.value.active.id;
  } catch {
    graphError.value = t("explorer.errors.graphRegistryLoadFailed");
  } finally {
    loadingGraphRegistry.value = false;
  }
}

async function runGraphVersionSwitch() {
  if (!selectedGraphVersionId.value.trim()) {
    graphError.value = t("explorer.errors.graphVersionRequired");
    return;
  }
  switchingGraphVersion.value = true;
  graphError.value = "";
  graphVersionMessage.value = "";
  try {
    const payload = await activateGraphVersion(selectedGraphVersionId.value);
    graphRegistry.value = payload.registry;
    selectedGraphVersionId.value = payload.registry.active.id;
    graphVersionMessage.value = tf("explorer.messages.graphVersionSwitched", {
      runName: payload.record.run_name,
    });

    await Promise.all([loadGraphSummary(), loadShowcase(), loadManualGraphRelations()]);
    if (selectedEntityDetail.value?.entity.entity_id) {
      await loadEntityDetail(selectedEntityDetail.value.entity.entity_id, false);
    }
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      graphError.value = String(error.response?.data?.detail || t("explorer.errors.graphVersionSwitchFailed"));
    } else {
      graphError.value = t("explorer.errors.graphVersionSwitchFailed");
    }
  } finally {
    switchingGraphVersion.value = false;
  }
}

async function loadShowcase() {
  loadingShowcase.value = true;
  showcaseError.value = "";
  try {
    const payload = await fetchGraphShowcase();
    showcaseCases.value = payload.cases;
  } catch {
    showcaseError.value = t("home.errors.showcaseLoadFailed");
  } finally {
    loadingShowcase.value = false;
  }
}

async function loadManualGraphRelations() {
  loadingManualRelations.value = true;
  try {
    const payload = await fetchGraphManualRelations();
    manualRelationOverrides.value = payload.records;
  } catch {
    manualRelationOverrides.value = [];
  } finally {
    loadingManualRelations.value = false;
  }
}

async function searchGraphManualRelationTargets() {
  const normalizedKeyword = graphManualRelationKeyword.value.trim();
  if (!normalizedKeyword) {
    manualGraphRelationError.value = t("explorer.errors.graphManualKeywordRequired");
    return;
  }
  manualGraphRelationError.value = "";
  manualGraphRelationMessage.value = "";
  try {
    const payload = await searchGraphEntities({ keyword: normalizedKeyword, limit: 8 });
    graphManualRelationCandidates.value = payload.results;
    if (!payload.results.length) {
      manualGraphRelationError.value = t("explorer.errors.graphManualTargetNotFound");
      graphManualRelationTargetId.value = "";
      return;
    }
    graphManualRelationTargetId.value = payload.results[0].entity_id;
  } catch {
    manualGraphRelationError.value = t("explorer.errors.graphManualTargetSearchFailed");
  }
}

function buildRelationMutationPayloadFromDetail(relation: GraphRelation) {
  const detail = selectedEntityDetail.value;
  if (!detail) {
    return null;
  }
  if (relation.direction === "outgoing") {
    return {
      startId: detail.entity.entity_id,
      endId: relation.related_entity.entity_id,
      relationType: relation.relation_type,
    };
  }
  return {
    startId: relation.related_entity.entity_id,
    endId: detail.entity.entity_id,
    relationType: relation.relation_type,
  };
}

async function addManualGraphRelation() {
  const detail = selectedEntityDetail.value;
  if (!detail) {
    manualGraphRelationError.value = t("explorer.errors.graphManualNeedCenterEntity");
    return;
  }
  if (!selectedManualGraphTarget.value) {
    manualGraphRelationError.value = t("explorer.errors.graphManualNeedTargetEntity");
    return;
  }

  const startId = graphManualRelationDirection.value === "outgoing" ? detail.entity.entity_id : selectedManualGraphTarget.value.entity_id;
  const endId = graphManualRelationDirection.value === "outgoing" ? selectedManualGraphTarget.value.entity_id : detail.entity.entity_id;

  applyingManualGraphRelation.value = true;
  manualGraphRelationError.value = "";
  manualGraphRelationMessage.value = "";
  try {
    const payload = await upsertGraphManualRelation({
      startId,
      endId,
      relationType: graphManualRelationType.value,
      exampleText: detail.mentions[0]?.clause_text || detail.entity.name,
      evidenceCount: 1,
      recordIds: detail.mentions.slice(0, 3).map((item) => item.record_id),
    });
    manualRelationOverrides.value = payload.manual_relations.records;
    await loadEntityDetail(detail.entity.entity_id, false);
    manualGraphRelationMessage.value = t("explorer.messages.graphManualRelationAdded");
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      manualGraphRelationError.value = String(error.response?.data?.detail || t("explorer.errors.graphManualRelationAddFailed"));
    } else {
      manualGraphRelationError.value = t("explorer.errors.graphManualRelationAddFailed");
    }
  } finally {
    applyingManualGraphRelation.value = false;
  }
}

async function suppressRelationFromDetail(relation: GraphRelation) {
  const payload = buildRelationMutationPayloadFromDetail(relation);
  if (!payload) {
    manualGraphRelationError.value = t("explorer.errors.graphManualNoEntityDetail");
    return;
  }
  applyingManualGraphRelation.value = true;
  manualGraphRelationError.value = "";
  manualGraphRelationMessage.value = "";
  try {
    const response = await suppressGraphRelation({
      ...payload,
      exampleText: relation.example_text || t("explorer.messages.graphManualSuppressExample"),
    });
    manualRelationOverrides.value = response.manual_relations.records;
    await loadEntityDetail(selectedEntityDetail.value!.entity.entity_id, false);
    manualGraphRelationMessage.value = t("explorer.messages.graphManualRelationSuppressed");
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      manualGraphRelationError.value = String(error.response?.data?.detail || t("explorer.errors.graphManualRelationDeleteFailed"));
    } else {
      manualGraphRelationError.value = t("explorer.errors.graphManualRelationDeleteFailed");
    }
  } finally {
    applyingManualGraphRelation.value = false;
  }
}

async function rollbackManualOverride(overrideId: string) {
  applyingManualGraphRelation.value = true;
  manualGraphRelationError.value = "";
  manualGraphRelationMessage.value = "";
  try {
    const response = await deleteGraphManualRelation(overrideId);
    manualRelationOverrides.value = response.manual_relations.records;
    if (selectedEntityDetail.value) {
      await loadEntityDetail(selectedEntityDetail.value.entity.entity_id, false);
    }
    manualGraphRelationMessage.value = t("explorer.messages.graphManualRelationRollbackDone");
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      manualGraphRelationError.value = String(error.response?.data?.detail || t("explorer.errors.graphManualRollbackFailed"));
    } else {
      manualGraphRelationError.value = t("explorer.errors.graphManualRollbackFailed");
    }
  } finally {
    applyingManualGraphRelation.value = false;
  }
}

async function loadEntityPathways(entityId: string) {
  loadingEntityPathways.value = true;
  pathwayError.value = "";
  try {
    entityPathways.value = await fetchGraphEntityPathways(entityId, 12);
  } catch {
    entityPathways.value = null;
    pathwayError.value = t("explorer.errors.pathwayLoadFailed");
  } finally {
    loadingEntityPathways.value = false;
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
    await loadEntityPathways(entityId);
  } catch {
    graphError.value = t("explorer.errors.entityDetailLoadFailed");
    entityPathways.value = null;
    pathwayError.value = "";
  } finally {
    loadingEntityDetail.value = false;
  }
}

async function loadClauseDetail(clauseId: string) {
  try {
    selectedClauseDetail.value = await fetchGraphClauseDetail(clauseId);
  } catch {
    selectedClauseDetail.value = null;
  }
}

async function runSearch(updateRoute = true) {
  const normalizedKeyword = keyword.value.trim();
  if (!normalizedKeyword) {
    searchError.value = t("explorer.errors.searchKeywordRequired");
    return;
  }

  searching.value = true;
  searchError.value = "";

  try {
    const [graphPayload, clausePayload] = await Promise.all([
      searchGraphEntities({ keyword: normalizedKeyword, entityType: entityType.value, limit: 10 }),
      searchGraphClauses({ keyword: normalizedKeyword, page: 1, pageSize: 12 }),
    ]);

    searchResults.value = graphPayload.results;
    searchTotal.value = graphPayload.total;
    clauseResults.value = clausePayload.results;
    clauseTotal.value = clausePayload.total;
    const firstClauseId = clausePayload.results[0]?.clause_id || "";
    if (firstClauseId) {
      await loadClauseDetail(firstClauseId);
    } else {
      selectedClauseDetail.value = null;
    }

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
      entityPathways.value = null;
      pathwayError.value = "";
    }
  } catch {
    searchError.value = t("explorer.errors.searchFailed");
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
    nerError.value = t("explorer.errors.nerInputRequired");
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
    entityDisplayNotes.value = {};
    resetManualEntityForm();
    resetManualRelationState();
    autoSelectRelationPair(prediction.entities);
    await resolvePredictedEntitiesToGraph(prediction);
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      nerError.value = String(error.response?.data?.detail || t("explorer.errors.nerFailedWithCheckpoint"));
    } else {
      nerError.value = t("explorer.errors.nerFailed");
    }
  } finally {
    predictingNer.value = false;
  }
}

async function runRelationPrediction() {
  if (!selectedHeadEntity.value || !selectedTailEntity.value) {
    relationPredictError.value = t("explorer.errors.relationSelectHeadTail");
    return;
  }
  if (predictedEntityKey(selectedHeadEntity.value) === predictedEntityKey(selectedTailEntity.value)) {
    relationPredictError.value = t("explorer.errors.relationHeadTailSame");
    return;
  }
  if (!relationInputText.value.trim()) {
    relationPredictError.value = t("explorer.errors.relationInputRequired");
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
      relationPredictError.value = String(error.response?.data?.detail || t("explorer.errors.relationFailedWithCheckpoint"));
    } else {
      relationPredictError.value = t("explorer.errors.relationFailed");
    }
  } finally {
    relationPredicting.value = false;
  }
}

async function runBatchRelationPrediction() {
  if (!relationInputText.value.trim()) {
    relationPredictError.value = t("explorer.errors.relationInputRequired");
    return;
  }
  if (!batchRelationPairs.value.length) {
    relationPredictError.value = t("explorer.errors.batchNoPairs");
    return;
  }

  batchRelationPredicting.value = true;
  relationPredictError.value = "";
  relationBatchMessage.value = "";
  relationPrediction.value = null;

  const results: RelationPrediction[] = [];
  let failedCount = 0;

  try {
    for (const pair of batchRelationPairs.value) {
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
    relationBatchMessage.value = tf("explorer.messages.batchRelationDone", {
      total: results.length,
      kept: results.filter((item) => item.label !== "NO_RELATION").length,
      failedPart: failedCount ? tf("explorer.messages.batchRelationFailedPart", { failed: failedCount }) : "",
    });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      relationPredictError.value = String(error.response?.data?.detail || t("explorer.errors.batchRelationFailedWithCheckpoint"));
    } else {
      relationPredictError.value = t("explorer.errors.batchRelationFailed");
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

async function openClauseRecord(item: GraphClauseSearchRecord) {
  await loadClauseDetail(item.clause_id);
  nerInputText.value = item.text;
  relationInputText.value = item.text;
}

function downloadSessionGraph() {
  if (!sessionGraphNodes.value.length) {
    exportMessage.value = t("explorer.errors.exportNoGraphData");
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
  exportMessage.value = tf("explorer.messages.exportDone", {
    nodeCount: sessionGraphNodes.value.length,
    edgeCount: sessionGraphEdges.value.length,
  });
}

async function saveSessionCandidate() {
  if (!sessionGraphNodes.value.length) {
    exportMessage.value = t("explorer.errors.saveCandidateNoData");
    return;
  }

  savingCandidate.value = true;
  try {
    const payload = await saveAnnotationCandidate({
      source_text: String(sessionGraphExportPayload.value.text || relationInputText.value || ""),
      source_page: "explore",
      session_payload: sessionGraphExportPayload.value as Record<string, unknown>,
    });
    exportMessage.value = tf("explorer.messages.saveCandidateDone", { recordId: payload.record_id });
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      exportMessage.value = String(error.response?.data?.detail || t("explorer.errors.saveCandidateFailed"));
    } else {
      exportMessage.value = t("explorer.errors.saveCandidateFailedRetry");
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

  keyword.value = routeKeyword || t("explorer.defaultKeyword");
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
  await Promise.all([loadGraphSummary(), loadGraphRegistry(), loadShowcase(), loadManualGraphRelations()]);
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
          <p class="panel-kicker">{{ t("explorer.heroKicker") }}</p>
          <h1>{{ t("explorer.heroTitle") }}</h1>
          <p class="hero-description explorer-description">{{ t("explorer.heroDescription") }}</p>
        </div>
        <div class="explorer-actions">
          <RouterLink to="/" class="ghost-link">{{ t("explorer.backToOverview") }}</RouterLink>
        </div>
      </div>

      <div class="graph-version-strip">
        <label>
          <span>{{ t("explorer.graphVersion.label") }}</span>
          <select v-model="selectedGraphVersionId" :disabled="loadingGraphRegistry || switchingGraphVersion">
            <option v-for="item in graphVersionOptions" :key="item.id" :value="item.id">{{ item.run_name }}</option>
          </select>
        </label>
        <button class="ghost-button" type="button" :disabled="loadingGraphRegistry || switchingGraphVersion" @click="runGraphVersionSwitch">
          {{ switchingGraphVersion ? t("explorer.graphVersion.switching") : t("explorer.graphVersion.switch") }}
        </button>
        <p class="status-text">{{ t("explorer.graphVersion.querySource") }}：{{ graphQuerySourceLabel }}</p>
      </div>

      <StatePanel v-if="graphVersionMessage" tone="success">
        <p>{{ graphVersionMessage }}</p>
      </StatePanel>

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
          <p class="panel-kicker">{{ t("explorer.quickCasesKicker") }}</p>
            <h2>{{ t("explorer.quickCasesTitle") }}</h2>
        </div>
      </div>
        <StatePanel v-if="showcaseError" tone="error">
          <p>{{ showcaseError }}</p>
        </StatePanel>
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
            <p class="panel-kicker">{{ t("explorer.extractionKicker") }}</p>
            <h2>{{ t("explorer.extractionTitle") }}</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runNerPrediction">
          <textarea v-model="nerInputText" rows="5" :placeholder="t('explorer.nerInputPlaceholder')" />
          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="predictingNer">{{ predictingNer ? t("explorer.nerRunning") : t("explorer.runNer") }}</button>
          </div>
        </form>

        <StatePanel v-if="nerError" tone="error">
          <p>{{ nerError }}</p>
        </StatePanel>
        <StatePanel v-else tone="info">
          <p>{{ t("explorer.nerHint") }}</p>
        </StatePanel>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("explorer.predictionResultKicker") }}</p>
            <h2>{{ t("explorer.predictionResultTitle") }}</h2>
          </div>
        </div>

        <StatePanel v-if="!nerPrediction" tone="warning">
          <p>{{ t("explorer.nerResultHint") }}</p>
        </StatePanel>
        <template v-else>
          <div class="prediction-summary-strip">
            <div class="breakdown-item"><span>{{ t("explorer.predictSummary.total") }}</span><strong>{{ predictionMatchSummary.total }}</strong></div>
            <div class="breakdown-item"><span>{{ t("explorer.predictSummary.matched") }}</span><strong>{{ predictionMatchSummary.matched }}</strong></div>
            <div class="breakdown-item"><span>{{ t("explorer.predictSummary.unmatched") }}</span><strong>{{ predictionMatchSummary.unmatched }}</strong></div>
          </div>

          <div class="breakdown-list predicted-breakdown-list">
            <div v-for="([type, count]) in predictedTypeBreakdown" :key="type" class="breakdown-item">
              <span>{{ formatEntityType(type) }}</span>
              <strong>{{ count }}</strong>
            </div>
          </div>

          <div class="manual-entity-panel">
            <div class="manual-entity-header">
              <strong>{{ t("explorer.manualEntity.title") }}</strong>
              <span>{{ t("explorer.manualEntity.desc") }}</span>
            </div>
            <div class="manual-entity-grid">
              <input v-model="manualEntityText" type="text" :placeholder="t('explorer.manualEntity.textPlaceholder')" />
              <select v-model="manualEntityType">
                <option v-for="option in entityTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <input v-model="manualEntityStart" type="text" inputmode="numeric" :placeholder="t('explorer.manualEntity.startPlaceholder')" />
              <button class="ghost-button" type="button" @click="addManualEntity">{{ t("explorer.manualEntity.add") }}</button>
            </div>
            <textarea
              v-model="manualEntityNote"
              rows="2"
              :placeholder="t('explorer.manualEntity.notePlaceholder')"
            />
            <StatePanel v-if="manualEntityError" tone="error">
              <p>{{ manualEntityError }}</p>
            </StatePanel>
            <StatePanel v-else tone="info">
              <p>{{ t("explorer.manualEntity.hint") }}</p>
            </StatePanel>
          </div>

          <StatePanel v-if="resolvingPredictedEntities" tone="info">
            <p>{{ t("explorer.mappingRunning") }}</p>
          </StatePanel>

          <div class="entity-chip-list explorer-entity-chip-list">
            <div v-for="entity in predictedEntities" :key="predictedEntityKey(entity)" class="entity-chip mapped-entity-chip">
              <strong>{{ entity.text }}</strong>
              <span>{{ formatEntityType(entity.type) }}</span>
              <small>{{ entity.start }}-{{ entity.end }}</small>
              <p class="entity-preview-copy">{{ entityPreviewText(entity) }}</p>
              <p v-if="entityDisplayNotes[predictedEntityKey(entity)]" class="entity-note-copy">{{ t("explorer.manualEntity.noteLabel") }}: {{ entityDisplayNotes[predictedEntityKey(entity)] }}</p>

              <div class="selection-strip">
                <span class="selection-pill" :class="{ active: relationHeadKey === predictedEntityKey(entity) }">{{ t("explorer.relation.headEntity") }}</span>
                <span class="selection-pill" :class="{ active: relationTailKey === predictedEntityKey(entity) }">{{ t("explorer.relation.tailEntity") }}</span>
              </div>

              <div class="candidate-panel">
                <p class="candidate-title">{{ t("explorer.candidates.title") }}</p>
                <div v-if="getPredictedMatches(entity).length" class="candidate-list">
                  <button v-for="candidate in getPredictedMatches(entity)" :key="candidate.entity_id" type="button" class="candidate-chip" @click="openGraphCandidate(candidate)">
                    <strong>{{ candidate.name }}</strong>
                    <span>{{ graphCandidateSummary(candidate) }}</span>
                  </button>
                </div>
                <p v-else class="candidate-empty">{{ t("explorer.candidates.empty") }}</p>
              </div>

              <div class="entity-chip-actions">
                <button class="ghost-button mini-button" type="button" @click="assignRelationEntity('head', entity)">{{ t("explorer.actions.setHead") }}</button>
                <button class="ghost-button mini-button" type="button" @click="assignRelationEntity('tail', entity)">{{ t("explorer.actions.setTail") }}</button>
                <button class="ghost-button mini-button" type="button" @click="usePredictionAsSearchSeed(entity)">{{ t("explorer.actions.setKeyword") }}</button>
                <button class="primary-button mini-button" type="button" @click="jumpToPredictedEntity(entity)">{{ t("explorer.actions.openBestMatch") }}</button>
                <button class="ghost-button mini-button danger-button" type="button" @click="removePredictedEntity(entity)">{{ t("explorer.actions.deleteEntity") }}</button>
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
            <p class="panel-kicker">{{ t("explorer.relationAssistantKicker") }}</p>
            <h2>{{ t("explorer.relationAssistantTitle") }}</h2>
          </div>
        </div>

        <form class="model-form" @submit.prevent="runRelationPrediction">
          <textarea v-model="relationInputText" rows="4" :placeholder="t('explorer.relation.inputPlaceholder')" />

          <p class="status-text">{{ tf("explorer.relation.batchCountHint", { count: batchRelationPairs.length }) }}</p>

          <div class="relation-form-grid">
            <div class="relation-form-block">
              <label>{{ t("explorer.relation.headEntity") }}</label>
              <div class="selected-entity-card" :class="{ active: Boolean(selectedHeadEntity) }">
                <strong>{{ selectedHeadEntity?.text || t("explorer.relation.notSelected") }}</strong>
                <span>{{ selectedHeadEntity ? formatEntityType(selectedHeadEntity.type) : t("explorer.relation.selectFromAbove") }}</span>
              </div>
            </div>
            <div class="relation-form-block">
              <label>{{ t("explorer.relation.tailEntity") }}</label>
              <div class="selected-entity-card" :class="{ active: Boolean(selectedTailEntity) }">
                <strong>{{ selectedTailEntity?.text || t("explorer.relation.notSelected") }}</strong>
                <span>{{ selectedTailEntity ? formatEntityType(selectedTailEntity.type) : t("explorer.relation.selectFromAbove") }}</span>
              </div>
            </div>
          </div>

          <div class="cta-row compact-cta-row">
            <button class="primary-button" type="submit" :disabled="relationPredicting || batchRelationPredicting || !canRunRelation">{{ relationPredicting ? t("explorer.relation.predicting") : t("explorer.relation.predict") }}</button>
            <button class="ghost-button" type="button" :disabled="relationPredicting || batchRelationPredicting || !canRunBatchRelation" @click="runBatchRelationPrediction">
              {{ batchRelationPredicting ? t("explorer.relation.batchPredicting") : t("explorer.relation.batchPredict") }}
            </button>
          </div>

          <div class="manual-relation-panel">
            <div class="manual-relation-header">
              <strong>{{ t("explorer.relation.manualTitle") }}</strong>
              <span>{{ t("explorer.relation.manualDesc") }}</span>
            </div>
            <div class="manual-relation-grid">
              <select v-model="manualRelationLabel">
                <option v-for="option in editableRelationOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <button class="ghost-button" type="button" :disabled="!canRunRelation" @click="applyManualRelation">{{ t("explorer.relation.manualApply") }}</button>
            </div>
            <p class="status-text">{{ t("explorer.relation.manualTherapyHint") }}</p>
          </div>
        </form>

        <StatePanel v-if="relationPredictError" tone="error">
          <p>{{ relationPredictError }}</p>
        </StatePanel>
        <StatePanel v-else-if="relationBatchMessage" tone="success">
          <p>{{ relationBatchMessage }}</p>
        </StatePanel>
        <StatePanel v-else tone="info">
          <p>{{ t("explorer.relation.modelHint") }}</p>
        </StatePanel>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("explorer.relationResultKicker") }}</p>
            <h2>{{ t("explorer.relationResultTitle") }}</h2>
          </div>
        </div>

        <StatePanel v-if="!relationPrediction" tone="warning">
          <p>{{ t("explorer.relation.resultHint") }}</p>
        </StatePanel>
        <template v-else>
          <div class="relation-result-card">
            <div class="breakdown-item"><span>{{ t("models.predictedRelation") }}</span><strong>{{ formatRelationType(relationPrediction.label) }}</strong></div>
            <div class="breakdown-item"><span>{{ t("models.confidence") }}</span><strong>{{ relationPrediction.confidence.toFixed(4) }}</strong></div>
            <div class="breakdown-item"><span>{{ t("models.headEntity") }}</span><strong>{{ relationPrediction.head.text }} / {{ formatEntityType(relationPrediction.head.type) }}</strong></div>
            <div class="breakdown-item"><span>{{ t("models.tailEntity") }}</span><strong>{{ relationPrediction.tail.text }} / {{ formatEntityType(relationPrediction.tail.type) }}</strong></div>
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
          <p class="panel-kicker">{{ t("explorer.sessionGraphKicker") }}</p>
          <h2>{{ t("explorer.sessionGraphTitle") }}</h2>
        </div>
        <div class="session-action-group">
          <button type="button" class="ghost-button session-export-button" :disabled="!sessionGraphNodes.length || savingCandidate" @click="saveSessionCandidate">
            {{ savingCandidate ? t("common.saving") : t("explorer.session.saveCandidate") }}
          </button>
          <button type="button" class="ghost-button session-export-button" :disabled="!sessionGraphNodes.length || savingCandidate" @click="downloadSessionGraph">{{ t("explorer.session.exportJson") }}</button>
        </div>
      </div>

      <StatePanel v-if="!predictedEntities.length" tone="warning">
        <p>{{ t("explorer.session.noEntitiesHint") }}</p>
      </StatePanel>
      <template v-else>
        <StatePanel :tone="exportMessage ? 'success' : 'info'">
          <p>{{ exportMessage || t("explorer.session.defaultHint") }}</p>
        </StatePanel>
        <div class="session-graph-layout">
          <div class="session-graph-canvas">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="network-lines">
              <line v-for="edge in sessionGraphLines" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" class="session-graph-line" />
            </svg>

            <button
              v-for="edge in sessionGraphLines"
              :key="`${edge.key}-label`"
              type="button"
              class="session-graph-edge-label"
              :style="{ left: `${edge.midX}%`, top: `${edge.midY}%` }"
              @click="removeRelationPredictionByRecordKey(edge.recordKey)"
              :title="tf('explorer.session.edgeDeleteTitle', { relation: formatRelationType(edge.label) })"
            >
              {{ formatRelationType(edge.label) }}
            </button>

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
              <strong>{{ t("explorer.session.entityNodes") }}</strong>
              <div class="session-side-list">
                <div v-for="node in sessionGraphNodes" :key="`${node.key}-item`" class="session-side-card">
                  <span>{{ formatEntityType(node.entity.type) }}</span>
                  <strong>{{ node.entity.text }}</strong>
                  <p v-if="entityDisplayNotes[node.key]">{{ entityDisplayNotes[node.key] }}</p>
                  <p>{{ node.matches.length ? tf("explorer.session.mappedCandidates", { count: node.matches.length }) : t("explorer.session.noMappedCandidates") }}</p>
                </div>
              </div>
            </div>

            <div class="session-side-block">
              <strong>{{ t("explorer.session.predictedRelations") }}</strong>
              <div class="session-side-list">
                <div v-if="!relationHistory.length" class="session-side-card empty">
                  <p>{{ t("explorer.session.noRelationsHint") }}</p>
                </div>
                <div
                  v-for="item in relationHistory"
                  :key="`${item.head.start}-${item.tail.start}-${item.label}`"
                  class="session-side-card action-card"
                >
                  <span>{{ formatRelationType(item.label) }}</span>
                  <strong>{{ item.head.text }} -> {{ item.tail.text }}</strong>
                  <p>
                    {{ tf("explorer.session.confidence", { score: item.confidence.toFixed(4) }) }}
                    <template v-if="item.source_mode === 'manual'"> · {{ t("common.manual") }}</template>
                  </p>
                  <div class="session-card-actions">
                    <button type="button" class="ghost-button mini-button" @click="inspectRelationPrediction(item)">{{ t("explorer.actions.viewEdit") }}</button>
                    <button type="button" class="ghost-button mini-button danger-button" @click="removeRelationPredictionByRecordKey(relationRecordKey(item))">{{ t("explorer.actions.deleteRelation") }}</button>
                  </div>
                </div>
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
            <p class="panel-kicker">{{ t("explorer.keywordSearchKicker") }}</p>
            <h2>{{ t("explorer.keywordSearchTitle") }}</h2>
          </div>
        </div>

        <form class="search-form search-form-stacked" @submit.prevent="runSearch()">
          <input v-model="keyword" type="text" :placeholder="t('explorer.searchInputPlaceholder')" />

          <div class="search-row">
            <div class="chip-group">
              <button v-for="option in entityTypeOptions" :key="option.value" type="button" class="filter-chip" :class="{ active: entityType === option.value }" @click="entityType = option.value">
                {{ option.label }}
              </button>
            </div>
            <button class="primary-button" type="submit" :disabled="searching">{{ searching ? t("explorer.searching") : t("explorer.search") }}</button>
          </div>
        </form>

        <StatePanel v-if="searchError" tone="error">
          <p>{{ searchError }}</p>
        </StatePanel>
        <StatePanel v-else tone="info">
          <p>{{ tf("explorer.searchResultSummary", { entityCount: searchTotal, corpusCount: clauseTotal }) }}</p>
        </StatePanel>

        <div class="entity-result-list">
          <button v-for="entity in searchResults" :key="entity.entity_id" class="entity-result-card" :class="{ active: selectedEntityDetail?.entity.entity_id === entity.entity_id }" type="button" @click="loadEntityDetail(entity.entity_id)">
            <div class="entity-result-head">
              <strong>{{ entity.name }}</strong>
              <span>{{ formatEntityType(entity.entity_type) }}</span>
            </div>
            <p>{{ tf("explorer.entityCardSummary", { mentionCount: entity.mention_count, recordCount: entity.record_count, firstRecordId: entity.first_record_id }) }}</p>
          </button>
        </div>
      </article>

      <article class="panel network-panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("explorer.relationPreviewKicker") }}</p>
            <h2>{{ t("explorer.relationPreviewTitle") }}</h2>
          </div>
        </div>

        <StatePanel v-if="graphError" tone="error">
          <p>{{ graphError }}</p>
        </StatePanel>
        <StatePanel v-else-if="loadingEntityDetail" tone="info">
          <p>{{ t("explorer.loadingEntityDetail") }}</p>
        </StatePanel>
        <StatePanel v-else-if="!selectedEntityDetail" tone="warning">
          <p>{{ t("explorer.noEntitySelectedHint") }}</p>
        </StatePanel>

        <template v-else>
          <div class="entity-focus-card">
            <div>
              <p class="entity-type-tag">{{ formatEntityType(selectedEntityDetail.entity.entity_type) }}</p>
              <h3>{{ selectedEntityDetail.entity.name }}</h3>
            </div>
            <div class="focus-metrics">
              <span>{{ tf("explorer.focus.incoming", { count: selectedEntityDetail.stats.incoming_relation_count }) }}</span>
              <span>{{ tf("explorer.focus.outgoing", { count: selectedEntityDetail.stats.outgoing_relation_count }) }}</span>
              <span>{{ tf("explorer.focus.evidence", { count: selectedEntityDetail.stats.mention_count }) }}</span>
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
              <p class="column-title">{{ t("explorer.columns.chain") }}</p>
              <div class="chain-list">
                <div v-for="item in chainSummary" :key="item" class="chain-item">{{ item }}</div>
              </div>

              <p class="column-title pathway-title">{{ t("explorer.columns.pathway") }}</p>
              <div class="chain-list">
                <div v-if="loadingEntityPathways" class="chain-item">{{ t("explorer.pathway.loading") }}</div>
                <div v-else-if="pathwayError" class="chain-item">{{ pathwayError }}</div>
                <template v-else-if="entityPathways?.paths.length">
                  <div v-for="pathway in entityPathways.paths.slice(0, 6)" :key="`${pathway.path_type}-${pathway.chain_text}`" class="chain-item pathway-item">
                    <strong>{{ formatPathwayType(pathway.path_type) }}</strong>
                    <p>{{ pathway.chain_text }}</p>
                    <small>{{ tf("explorer.pathway.evidenceScore", { score: pathway.evidence_score }) }}</small>
                  </div>
                </template>
                <div v-else class="chain-item">{{ t("explorer.pathway.empty") }}</div>
              </div>
            </div>

            <div class="relation-column">
              <p class="column-title">{{ t("explorer.columns.relation") }}</p>
              <div class="manual-relation-panel graph-manual-relation-panel">
                <div class="manual-relation-header">
                  <strong>{{ t("explorer.graphManual.title") }}</strong>
                  <span>{{ t("explorer.graphManual.desc") }}</span>
                </div>
                <div class="manual-relation-grid">
                  <select v-model="graphManualRelationDirection">
                    <option value="outgoing">{{ t("explorer.graphManual.directionOutgoing") }}</option>
                    <option value="incoming">{{ t("explorer.graphManual.directionIncoming") }}</option>
                  </select>
                  <select v-model="graphManualRelationType">
                    <option v-for="option in editableRelationOptions" :key="`graph-manual-${option.value}`" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </div>
                <div class="manual-relation-grid">
                  <input v-model="graphManualRelationKeyword" type="text" :placeholder="t('explorer.graphManual.keywordPlaceholder')" />
                  <button class="ghost-button" type="button" :disabled="applyingManualGraphRelation" @click="searchGraphManualRelationTargets">
                    {{ t("explorer.graphManual.searchTarget") }}
                  </button>
                </div>
                <div class="manual-relation-grid">
                  <select v-model="graphManualRelationTargetId">
                    <option value="">{{ t("explorer.graphManual.selectTarget") }}</option>
                    <option v-for="candidate in graphManualRelationCandidates" :key="candidate.entity_id" :value="candidate.entity_id">
                      {{ candidate.name }} / {{ formatEntityType(candidate.entity_type) }}
                    </option>
                  </select>
                  <button class="ghost-button" type="button" :disabled="applyingManualGraphRelation || !graphManualRelationTargetId" @click="addManualGraphRelation">
                    {{ t("explorer.graphManual.addRelation") }}
                  </button>
                </div>
              </div>

              <StatePanel v-if="manualGraphRelationError" tone="error">
                <p>{{ manualGraphRelationError }}</p>
              </StatePanel>
              <StatePanel v-else-if="manualGraphRelationMessage" tone="success">
                <p>{{ manualGraphRelationMessage }}</p>
              </StatePanel>

              <div class="relation-list">
                <div v-for="relation in [...selectedEntityDetail.outgoing_relations, ...selectedEntityDetail.incoming_relations].slice(0, 8)" :key="`${relation.direction}-${relation.relation_type}-${relation.related_entity.entity_id}`" class="relation-item">
                  <span>{{ relation.direction === 'outgoing' ? t("explorer.graphManual.outgoing") : t("explorer.graphManual.incoming") }}</span>
                  <strong>{{ formatRelationType(relation.relation_type) }}</strong>
                  <p>{{ tf("explorer.graphManual.relationEvidence", { name: relation.related_entity.name, count: relation.evidence_count }) }}</p>
                  <div class="entity-chip-actions relation-item-actions">
                    <button class="ghost-button mini-button danger-button" type="button" :disabled="applyingManualGraphRelation" @click="suppressRelationFromDetail(relation)">
                      {{ t("explorer.actions.deleteRelation") }}
                    </button>
                    <button
                      v-if="relation.manual_override && relation.manual_override_id"
                      class="ghost-button mini-button"
                      type="button"
                      :disabled="applyingManualGraphRelation"
                      @click="rollbackManualOverride(String(relation.manual_override_id))"
                    >
                      {{ t("explorer.graphManual.rollback") }}
                    </button>
                  </div>
                </div>
              </div>

              <div class="session-side-list graph-override-list">
                <div v-if="loadingManualRelations" class="session-side-card empty">
                  <p>{{ t("explorer.graphManual.loadingOverrides") }}</p>
                </div>
                <div v-else-if="!manualRelationOverrides.length" class="session-side-card empty">
                  <p>{{ t("explorer.graphManual.noOverrides") }}</p>
                </div>
                <div v-else class="session-side-card">
                  <strong>{{ t("explorer.graphManual.recentOverrides") }}</strong>
                  <div class="session-side-list">
                    <div v-for="item in manualRelationOverrides.slice(0, 4)" :key="item.id" class="session-side-card action-card">
                      <span>{{ item.action === "upsert" ? t("explorer.graphManual.actionUpsert") : t("explorer.graphManual.actionSuppress") }} · {{ formatRelationType(item.relation_type) }}</span>
                      <p>{{ item.start_id }} -> {{ item.end_id }}</p>
                      <div class="session-card-actions">
                        <button class="ghost-button mini-button" type="button" :disabled="applyingManualGraphRelation" @click="rollbackManualOverride(item.id)">
                          {{ t("explorer.graphManual.rollback") }}
                        </button>
                      </div>
                    </div>
                  </div>
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
            <p class="panel-kicker">{{ t("explorer.evidenceTracebackKicker") }}</p>
            <h2>{{ t("explorer.evidenceTracebackTitle") }}</h2>
          </div>
        </div>

        <StatePanel v-if="!selectedEntityDetail" tone="warning">
          <p>{{ t("explorer.evidenceHint") }}</p>
        </StatePanel>
        <div v-else class="evidence-list">
          <article v-for="mention in selectedEntityDetail.mentions" :key="`${mention.clause_id}-${mention.start}-${mention.end}`" class="evidence-card">
            <div class="evidence-meta">
              <span>{{ mention.record_id }}</span>
              <span>{{ mention.line_number ? tf("explorer.lineNumber", { line: mention.line_number }) : t("explorer.lineUnknown") }}</span>
              <span>{{ formatEntryType(mention.entry_type) }}</span>
            </div>
            <p>{{ mention.clause_text }}</p>
          </article>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="panel-kicker">{{ t("explorer.textPreviewKicker") }}</p>
            <h2>{{ t("explorer.textPreviewTitle") }}</h2>
          </div>
        </div>

        <div class="result-list">
          <button
            v-for="entry in clauseResults"
            :key="entry.clause_id"
            type="button"
            class="result-item text-preview-item"
            :class="{ active: selectedClauseDetail?.clause.clause_id === entry.clause_id }"
            @click="openClauseRecord(entry)"
          >
            <div class="result-meta">
              <span>{{ entry.record_id }}</span>
              <span>{{ entry.entry_type ? formatEntryType(entry.entry_type) : t("common.unknown") }}</span>
              <span>{{ tf("explorer.focus.evidence", { count: entry.mention_count }) }}</span>
            </div>
            <p>{{ entry.text }}</p>
          </button>
        </div>
        <StatePanel v-if="selectedClauseDetail" tone="info">
          <p>{{ selectedClauseDetail.clause.record_id }} · {{ selectedClauseDetail.clause.clause_id }}</p>
          <p>{{ tf("explorer.focus.evidence", { count: selectedClauseDetail.stats.mention_count }) }}</p>
        </StatePanel>
      </article>
    </section>
  </main>
</template>
