import axios from "axios";

import type {
  AnnotationCandidateListResponse,
  AnnotationCandidatePayload,
  AnnotationCandidateRecord,
  AnnotationCandidateStatusPayload,
  AnnotationCandidateUpdatePayload,
  CorpusOverview,
  CorpusSearchResult,
  GraphEntityDetail,
  GraphEntitySearchResult,
  GraphShowcaseResponse,
  GraphSummary,
  ModelSummary,
  NerPrediction,
  RelationPrediction,
  AcceptedPipelineRefreshResponse,
} from "../types/api";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1",
  timeout: 10000,
});

export async function fetchOverview() {
  const response = await apiClient.get<CorpusOverview>("/corpus/overview/");
  return response.data;
}

export async function searchCorpus(keyword: string) {
  const response = await apiClient.get<CorpusSearchResult>("/corpus/search/", {
    params: { keyword },
  });
  return response.data;
}

export async function fetchGraphSummary() {
  const response = await apiClient.get<GraphSummary>("/graph/summary/");
  return response.data;
}

export async function fetchGraphShowcase() {
  const response = await apiClient.get<GraphShowcaseResponse>("/graph/showcase/");
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

export async function saveAnnotationCandidate(payload: AnnotationCandidatePayload) {
  const response = await apiClient.post<AnnotationCandidateRecord>("/annotation/candidates/", payload);
  return response.data;
}

export async function fetchAnnotationCandidates(limit = 20, status?: string) {
  const response = await apiClient.get<AnnotationCandidateListResponse>("/annotation/candidates/", {
    params: { limit, status: status || undefined },
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
