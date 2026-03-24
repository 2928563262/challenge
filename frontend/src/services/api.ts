import axios from "axios";

import type {
  AnnotationCandidateBatchStatusResponse,
  AnnotationCandidateDeleteResponse,
  AnnotationCandidateListResponse,
  AnnotationCandidatePayload,
  AnnotationCandidateRecord,
  AnnotationCandidateStatusPayload,
  AnnotationCandidateUpdatePayload,
  CorpusOverview,
  CorpusSearchResult,
  ClinicalPath,
  FormulaAnalysis,
  GraphClauseDetail,
  GraphClauseSearchResponse,
  GraphActivationResponse,
  GraphNeo4jSyncResponse,
  GraphNeo4jSyncStatus,
  GraphManualRelationOverrideListResponse,
  GraphManualRelationOverrideMutationResponse,
  GraphEntityDetail,
  GraphEntityPathways,
  GraphEntitySearchResult,
  GraphRegistryStatus,
  HerbAnalysis,
  ReviewedGraphRefreshResponse,
  GraphShowcaseResponse,
  GraphSummary,
  StatsOverview,
  HerbAnalysis,
  FormulaAnalysis,
  ClinicalPath,
  TextAnalysis,
  ModelActivationResponse,
  ModelSummary,
  NerPrediction,
  QAAnswer,
  RelationPrediction,
  StatsOverview,
  TextAnalysis,
  AcceptedPipelineRefreshResponse,
  SystemPipelineRunResponse,
  TrainingJobsStatus,
  TrainingJobStartResponse,
} from "../types/api";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1",
  timeout: 10000,
});

export async function fetchOverview() {
  const response = await apiClient.get<CorpusOverview>("/corpus/overview/");
  return response.data;
}

export async function searchCorpus(params: {
  keyword?: string;
  page?: number;
  pageSize?: number;
  formulaRelated?: "all" | "true" | "false";
  sortBy?: "id" | "text_length" | "formula_name";
  sortOrder?: "asc" | "desc";
}) {
  const response = await apiClient.get<CorpusSearchResult>("/corpus/search/", {
    params: {
      keyword: params.keyword || "",
      page: params.page ?? 1,
      page_size: params.pageSize ?? 20,
      formula_related: params.formulaRelated ?? "all",
      sort_by: params.sortBy ?? "id",
      sort_order: params.sortOrder ?? "asc",
    },
  });
  return response.data;
}

export async function fetchGraphSummary() {
  const response = await apiClient.get<GraphSummary>("/graph/summary/");
  return response.data;
}

// ============ Statistics API ============
export async function fetchStatsOverview() {
  const response = await apiClient.get<StatsOverview>("/stats/overview/");
  return response.data;
}

export async function fetchHerbAnalysis(limit?: number) {
  const response = await apiClient.get<HerbAnalysis>("/stats/herbs/", {
    params: { limit: limit || 20 },
  });
  return response.data;
}

export async function fetchFormulaAnalysis(limit?: number) {
  const response = await apiClient.get<FormulaAnalysis>("/stats/formulas/", {
    params: { limit: limit || 20 },
  });
  return response.data;
}

export async function fetchClinicalPath() {
  const response = await apiClient.get<ClinicalPath>("/stats/clinical-path/");
  return response.data;
}

export async function fetchTextAnalysis() {
  const response = await apiClient.get<TextAnalysis>("/stats/text/");
  return response.data;
}

export async function fetchGraphShowcase() {
  const response = await apiClient.get<GraphShowcaseResponse>("/graph/showcase/");
  return response.data;
}

export async function refreshReviewedGraph(payload?: { statuses?: string[]; limit?: number | null }) {
  const response = await apiClient.post<ReviewedGraphRefreshResponse>("/graph/datasets/reviewed/refresh/", {
    statuses: payload?.statuses ?? ["accepted", "reviewed"],
    limit: payload?.limit ?? null,
  });
  return response.data;
}

export async function fetchGraphRegistry() {
  const response = await apiClient.get<GraphRegistryStatus>("/graph/registry/");
  return response.data;
}

export async function activateGraphVersion(graphId: string) {
  const response = await apiClient.post<GraphActivationResponse>("/graph/registry/activate/", {
    graph_id: graphId,
  });
  return response.data;
}

export async function fetchGraphNeo4jSyncStatus() {
  const response = await apiClient.get<GraphNeo4jSyncStatus>("/graph/neo4j/sync/");
  return response.data;
}

export async function syncGraphToNeo4j() {
  const response = await apiClient.post<GraphNeo4jSyncResponse>("/graph/neo4j/sync/", {});
  return response.data;
}

export async function fetchGraphManualRelations(graphId?: string) {
  const response = await apiClient.get<GraphManualRelationOverrideListResponse>("/graph/manual-relations/", {
    params: {
      graph_id: graphId || undefined,
    },
  });
  return response.data;
}

export async function upsertGraphManualRelation(payload: {
  startId: string;
  endId: string;
  relationType: string;
  exampleText?: string;
  evidenceCount?: number;
  recordIds?: string[];
}) {
  const response = await apiClient.post<GraphManualRelationOverrideMutationResponse>("/graph/manual-relations/", {
    action: "upsert",
    start_id: payload.startId,
    end_id: payload.endId,
    relation_type: payload.relationType,
    example_text: payload.exampleText || "",
    evidence_count: payload.evidenceCount ?? 1,
    record_ids: payload.recordIds ?? [],
  });
  return response.data;
}

export async function suppressGraphRelation(payload: {
  startId: string;
  endId: string;
  relationType: string;
  exampleText?: string;
}) {
  const response = await apiClient.post<GraphManualRelationOverrideMutationResponse>("/graph/manual-relations/", {
    action: "suppress",
    start_id: payload.startId,
    end_id: payload.endId,
    relation_type: payload.relationType,
    example_text: payload.exampleText || "",
  });
  return response.data;
}

export async function deleteGraphManualRelation(overrideId: string) {
  const response = await apiClient.delete<GraphManualRelationOverrideMutationResponse>(`/graph/manual-relations/${encodeURIComponent(overrideId)}/`);
  return response.data;
}

export async function searchGraphEntities(params: {
  keyword?: string;
  entityType?: string;
  limit?: number;
}) {
  const response = await apiClient.get<GraphEntitySearchResult>("/graph/entities/", {
    params: {
      keyword: params.keyword || "",
      entity_type: params.entityType || undefined,
      limit: params.limit ?? 12,
    },
  });
  return response.data;
}

export async function fetchGraphEntityDetail(entityId: string, params?: { relationLimit?: number; evidenceLimit?: number }) {
  const encodedEntityId = encodeURIComponent(entityId);
  const response = await apiClient.get<GraphEntityDetail>(`/graph/entities/${encodedEntityId}/`, {
    params: {
      relation_limit: params?.relationLimit ?? 12,
      evidence_limit: params?.evidenceLimit ?? 12,
    },
  });
  return response.data;
}

export async function fetchGraphEntityPathways(entityId: string, limit = 20) {
  const encodedEntityId = encodeURIComponent(entityId);
  const response = await apiClient.get<GraphEntityPathways>(`/graph/entities/${encodedEntityId}/pathways/`, {
    params: { limit },
  });
  return response.data;
}

export async function searchGraphClauses(params: {
  keyword?: string;
  entryType?: string;
  page?: number;
  pageSize?: number;
}) {
  const response = await apiClient.get<GraphClauseSearchResponse>("/graph/clauses/", {
    params: {
      keyword: params.keyword || "",
      entry_type: params.entryType || undefined,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 20,
    },
  });
  return response.data;
}

export async function fetchGraphClauseDetail(clauseId: string) {
  const encodedClauseId = encodeURIComponent(clauseId);
  const response = await apiClient.get<GraphClauseDetail>(`/graph/clauses/${encodedClauseId}/`);
  return response.data;
}

export async function fetchHerbAnalysis(limit = 20) {
  const response = await apiClient.get<HerbAnalysis>("/stats/herbs/", {
    params: { limit },
  });
  return response.data;
}

export async function fetchFormulaAnalysis(limit = 20) {
  const response = await apiClient.get<FormulaAnalysis>("/stats/formulas/", {
    params: { limit },
  });
  return response.data;
}

export async function fetchClinicalPath() {
  const response = await apiClient.get<ClinicalPath>("/stats/clinical-path/");
  return response.data;
}

export async function fetchTextAnalysis() {
  const response = await apiClient.get<TextAnalysis>("/stats/text/");
  return response.data;
}

export async function fetchModelSummary() {
  const response = await apiClient.get<ModelSummary>("/model/summary/");
  return response.data;
}

export async function refreshAcceptedPipeline(limit?: number) {
  const response = await apiClient.post<AcceptedPipelineRefreshResponse>("/model/datasets/accepted/refresh/", {
    limit: limit ?? null,
  });
  return response.data;
}

export async function activateModel(payload: { task: "ner" | "relation"; modelId: string }) {
  const response = await apiClient.post<ModelActivationResponse>("/model/registry/activate/", {
    task: payload.task,
    model_id: payload.modelId,
  });
  return response.data;
}

export async function fetchTrainingJobs(limit = 20) {
  const response = await apiClient.get<TrainingJobsStatus>("/model/jobs/", {
    params: { limit },
  });
  return response.data;
}

export async function startTrainingJob(payload: {
  task: "ner" | "relation";
  datasetSource: "baseline" | "merged";
  epochs?: number;
  batchSize?: number;
  learningRate?: number | null;
  runName?: string;
  activate?: boolean;
}) {
  const response = await apiClient.post<TrainingJobStartResponse>("/model/jobs/start/", {
    task: payload.task,
    dataset_source: payload.datasetSource,
    epochs: payload.epochs ?? 3,
    batch_size: payload.batchSize ?? 4,
    learning_rate: payload.learningRate ?? null,
    run_name: payload.runName ?? "",
    activate: payload.activate ?? false,
  });
  return response.data;
}

export async function runSystemPipeline(payload?: {
  refreshAccepted?: boolean;
  refreshGraph?: boolean;
  syncNeo4j?: boolean;
  startNerTraining?: boolean;
  startRelationTraining?: boolean;
  trainingDatasetSource?: "baseline" | "merged";
  trainingEpochs?: number;
  trainingBatchSize?: number;
  trainingLearningRate?: number | null;
  activateTraining?: boolean;
}) {
  const response = await apiClient.post<SystemPipelineRunResponse>("/model/pipeline/run/", {
    refresh_accepted: payload?.refreshAccepted ?? true,
    refresh_graph: payload?.refreshGraph ?? true,
    sync_neo4j: payload?.syncNeo4j ?? false,
    start_ner_training: payload?.startNerTraining ?? false,
    start_relation_training: payload?.startRelationTraining ?? false,
    training_dataset_source: payload?.trainingDatasetSource ?? "merged",
    training_epochs: payload?.trainingEpochs ?? 3,
    training_batch_size: payload?.trainingBatchSize ?? 4,
    training_learning_rate: payload?.trainingLearningRate ?? null,
    activate_training: payload?.activateTraining ?? false,
  });
  return response.data;
}

export async function predictNer(text: string) {
  const response = await apiClient.post<NerPrediction>("/model/ner/predict/", { text });
  return response.data;
}

export async function predictRelation(payload: {
  text: string;
  head: { text: string; type: string; start?: number; end?: number };
  tail: { text: string; type: string; start?: number; end?: number };
}) {
  const response = await apiClient.post<RelationPrediction>("/model/relation/predict/", payload);
  return response.data;
}

export async function askQuestion(question: string) {
  const response = await apiClient.post<QAAnswer>("/qa/ask/", { question });
  return response.data;
}

export async function saveAnnotationCandidate(payload: AnnotationCandidatePayload) {
  const response = await apiClient.post<AnnotationCandidateRecord>("/annotation/candidates/", payload);
  return response.data;
}

export async function fetchAnnotationCandidates(params?: {
  limit?: number;
  status?: string;
  page?: number;
  pageSize?: number;
  q?: string;
}) {
  const response = await apiClient.get<AnnotationCandidateListResponse>("/annotation/candidates/", {
    params: {
      limit: params?.limit ?? undefined,
      status: params?.status || undefined,
      page: params?.page ?? undefined,
      page_size: params?.pageSize ?? undefined,
      q: params?.q?.trim() || undefined,
    },
  });
  return response.data;
}

export async function fetchAnnotationCandidateDetail(recordId: string) {
  const encodedRecordId = encodeURIComponent(recordId);
  const response = await apiClient.get<AnnotationCandidateRecord>(`/annotation/candidates/${encodedRecordId}/`);
  return response.data;
}

export async function updateAnnotationCandidateStatus(recordId: string, payload: AnnotationCandidateStatusPayload) {
  const encodedRecordId = encodeURIComponent(recordId);
  const response = await apiClient.patch<AnnotationCandidateRecord>(`/annotation/candidates/${encodedRecordId}/`, payload);
  return response.data;
}

export async function updateAnnotationCandidate(recordId: string, payload: AnnotationCandidateUpdatePayload) {
  const encodedRecordId = encodeURIComponent(recordId);
  const response = await apiClient.patch<AnnotationCandidateRecord>(`/annotation/candidates/${encodedRecordId}/`, payload);
  return response.data;
}

export async function deleteAnnotationCandidate(recordId: string) {
  const encodedRecordId = encodeURIComponent(recordId);
  const response = await apiClient.delete<AnnotationCandidateDeleteResponse>(`/annotation/candidates/${encodedRecordId}/`);
  return response.data;
}

export async function batchUpdateAnnotationCandidateStatus(recordIds: string[], status: string) {
  const response = await apiClient.post<AnnotationCandidateBatchStatusResponse>("/annotation/candidates/batch-status/", {
    record_ids: recordIds,
    status,
  });
  return response.data;
}
