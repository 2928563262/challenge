export interface CorpusEntry {
  id: number;
  text: string;
  formula_name: string | null;
  is_formula_related: boolean;
}

export interface CorpusOverview {
  project: {
    name: string;
    focus: string;
  };
  stats: {
    entry_count: number;
    formula_related_count: number;
    character_count: number;
  };
  samples: CorpusEntry[];
  formula_samples: CorpusEntry[];
}

export interface CorpusSearchResult {
  keyword: string;
  total: number;
  results: CorpusEntry[];
}

export interface GraphEntity {
  entity_id: string;
  entity_type: string;
  name: string;
  mention_count: number;
  record_count: number;
  first_record_id: string;
  entry_types: string[];
  labels: string[];
}

export interface GraphVersionRecord {
  id: string;
  run_name: string;
  source_input: string;
  source_type: string;
  output_dir: string;
  stats: Record<string, number>;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface GraphSummary {
  input_record_count: number;
  entity_node_count: number;
  clause_node_count: number;
  entity_relation_count: number;
  clause_mention_count: number;
  entity_type_breakdown: Record<string, number>;
  relation_type_breakdown: Record<string, number>;
  top_entities: GraphEntity[];
  graph_version: GraphVersionRecord;
}

export interface GraphEntitySearchResult {
  keyword: string;
  entity_type: string | null;
  total: number;
  results: GraphEntity[];
}

export interface GraphRelation {
  direction: "incoming" | "outgoing";
  relation_type: string;
  evidence_count: number;
  record_ids: string[];
  example_text: string;
  related_entity: GraphEntity;
}

export interface GraphMention {
  clause_id: string;
  record_id: string;
  entity_type: string;
  mention_text: string;
  start: number;
  end: number;
  clause_text: string;
  entry_type: string | null;
  line_number: number | null;
}

export interface GraphEntityDetail {
  entity: GraphEntity;
  outgoing_relations: GraphRelation[];
  incoming_relations: GraphRelation[];
  mentions: GraphMention[];
  stats: {
    outgoing_relation_count: number;
    incoming_relation_count: number;
    mention_count: number;
  };
}

export interface GraphPathwayRelation {
  relation_type: string;
  start_entity_id: string;
  end_entity_id: string;
  evidence_count: number;
}

export interface GraphPathwayNode {
  entity_id: string;
  entity_type: string;
  name: string;
}

export interface GraphPathway {
  path_type: string;
  nodes: GraphPathwayNode[];
  relations: GraphPathwayRelation[];
  evidence_score: number;
  chain_text: string;
}

export interface GraphEntityPathways {
  entity: Pick<GraphEntity, "entity_id" | "entity_type" | "name">;
  total: number;
  paths: GraphPathway[];
}

export interface GraphShowcaseCase {
  slug: string;
  title: string;
  description: string;
  focus: string;
  entity: GraphEntity;
  highlights: string[];
  relation_preview: GraphRelation[];
  evidence_preview: GraphMention[];
}

export interface GraphShowcaseResponse {
  cases: GraphShowcaseCase[];
}

export interface ReviewedGraphRefreshResponse {
  summary: Record<string, unknown>;
  registry: GraphRegistryStatus;
  graph_summary: GraphSummary;
  neo4j_sync?: GraphNeo4jSyncReport;
}

export interface GraphRegistryStatus {
  path: string;
  active: GraphVersionRecord;
  versions: GraphVersionRecord[];
}

export interface GraphActivationResponse {
  record: GraphVersionRecord;
  registry: GraphRegistryStatus;
}

export interface GraphNeo4jSyncReport {
  ok: boolean;
  detail: string;
  graph_version: GraphVersionRecord | Record<string, unknown>;
  graph_dir: string;
  uri: string;
  database: string;
  summary?: Record<string, number>;
  run_name?: string;
  entity_node_count?: number;
  entity_relation_count?: number;
}

export interface GraphNeo4jSyncStatus {
  exists: boolean;
  path: string;
  report: GraphNeo4jSyncReport | null;
}

export interface GraphNeo4jSyncResponse {
  sync: GraphNeo4jSyncReport;
  status: GraphNeo4jSyncStatus;
}

export interface DatasetSplitSummary {
  record_count?: number;
  token_count?: number;
  example_count?: number;
  positive_example_count?: number;
  negative_example_count?: number;
  entity_count_by_type?: Record<string, number>;
  label_count_by_type?: Record<string, number>;
  pair_count_by_type?: Record<string, number>;
  source_count_by_type?: Record<string, number>;
}

export interface ModelRuntimeStatus {
  ready: boolean;
  base_model_name: string;
  model_dir: string;
  checkpoint_exists: boolean;
  dataset_manifest_exists: boolean;
  dataset_manifest_path: string;
  missing_dependencies: string[];
  required_dependencies: string[];
  label_list: string[];
  dataset_summary: Record<string, DatasetSplitSummary> | null;
  commands: Record<string, string>;
  active_model: ModelRegistryRecord;
}

export interface ArtifactReport<T = Record<string, unknown> | null> {
  exists: boolean;
  path: string;
  updated_at: number | null;
  data: T | null;
}

export interface AcceptedPipelineStatus {
  accepted_report: ArtifactReport;
  incremental_report: ArtifactReport;
  merge_report: ArtifactReport;
  merged_ner_manifest: ArtifactReport;
  merged_relation_manifest: ArtifactReport;
}

export interface ModelRegistryRecord {
  id: string;
  task: "ner" | "relation";
  run_name: string;
  model_name: string;
  model_dir: string;
  dataset_dir: string;
  dataset_source: string;
  validation_metrics: Record<string, number>;
  train_metrics: Record<string, number>;
  test_metrics: Record<string, number>;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface ModelRegistryStatus {
  path: string;
  active: {
    ner: ModelRegistryRecord;
    relation: ModelRegistryRecord;
  };
  ner: ModelRegistryRecord[];
  relation: ModelRegistryRecord[];
}

export interface ModelSummary {
  ner: ModelRuntimeStatus;
  relation: ModelRuntimeStatus;
  accepted_pipeline: AcceptedPipelineStatus;
  registry: ModelRegistryStatus;
  training_jobs: TrainingJobsStatus;
}

export interface TrainingJobRecord {
  id: string;
  task: "ner" | "relation";
  status: "running" | "succeeded" | "failed";
  dataset_source: string;
  dataset_dir: string;
  run_name: string;
  epochs: number;
  batch_size: number;
  learning_rate: number | null;
  activate: boolean;
  command: string[];
  pid: number;
  log_path: string;
  expected_summary_path: string;
  summary: Record<string, unknown> | null;
  return_code: number | null;
  error_message: string | null;
  created_at: string;
  started_at: string;
  finished_at: string | null;
  updated_at: string;
}

export interface TrainingJobsStatus {
  path: string;
  running_count: number;
  jobs: TrainingJobRecord[];
}

export interface TrainingJobStartResponse {
  job: TrainingJobRecord;
  jobs: TrainingJobsStatus;
}

export interface NerPredictionEntity {
  type: string;
  text: string;
  start: number;
  end: number;
}

export interface NerPrediction {
  text: string;
  tokens: string[];
  labels: string[];
  entities: NerPredictionEntity[];
}

export interface RelationPredictionEntity {
  text: string;
  type: string;
  start: number;
  end: number;
}

export interface RelationPredictionScore {
  label: string;
  score: number;
}

export interface RelationPrediction {
  text: string;
  head: RelationPredictionEntity;
  tail: RelationPredictionEntity;
  sequence_text: string;
  label: string;
  confidence: number;
  top_predictions: RelationPredictionScore[];
  source_mode?: "model" | "manual";
}

export interface AnnotationCandidatePayload {
  source_text: string;
  source_page?: string;
  session_payload: Record<string, unknown>;
  ner_model_dir?: string;
  relation_model_dir?: string;
}

export interface AutoPipelineRefreshMeta {
  triggered: boolean;
  ok: boolean;
  detail: string;
  export_record_count?: number;
  merge_ner_added_count?: number;
  merge_relation_added_count?: number;
}

export interface AutoGraphRefreshMeta {
  triggered: boolean;
  ok: boolean;
  detail: string;
  run_name?: string;
  entity_node_count?: number;
  entity_relation_count?: number;
}

export interface AnnotationCandidateRecord {
  record_id: string;
  status: string;
  source_page: string;
  source_text: string;
  text_preview: string;
  node_count: number;
  edge_count: number;
  ner_model_dir: string;
  relation_model_dir: string;
  created_at: string;
  updated_at: string;
  session_payload?: Record<string, unknown>;
  auto_pipeline_refresh?: AutoPipelineRefreshMeta;
  auto_graph_refresh?: AutoGraphRefreshMeta;
}

export interface AnnotationCandidateStatusPayload {
  status: string;
}

export interface AnnotationCandidateUpdatePayload {
  status?: string;
  source_text?: string;
  session_payload?: Record<string, unknown>;
}

export interface AnnotationCandidateListResponse {
  total: number;
  limit: number;
  results: AnnotationCandidateRecord[];
}

export interface AcceptedPipelineRefreshResponse {
  export_report: Record<string, unknown>;
  incremental_report: Record<string, unknown>;
  merge_report: Record<string, unknown>;
  status: AcceptedPipelineStatus;
}

export interface ModelActivationResponse {
  task: "ner" | "relation";
  record: ModelRegistryRecord;
  registry: ModelRegistryStatus;
}
