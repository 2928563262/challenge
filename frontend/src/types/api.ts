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
  first_clause_text?: string;
  entry_types: string[];
  labels: string[];
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

// Stats Overview (新统计接口)
export interface StatsOverview {
  kpi: {
    article_count: number;
    entity_count: number;
    relation_count: number;
    clause_mention_count: number;
  };
  entity_type_breakdown: Record<string, number>;
  relation_type_breakdown: Record<string, number>;
  top_entities_by_type: {
    FORMULA: Array<{ name: string; mention_count: number }>;
    HERB: Array<{ name: string; mention_count: number }>;
    SYNDROME: Array<{ name: string; mention_count: number }>;
    SYMPTOM: Array<{ name: string; mention_count: number }>;
    THERAPY: Array<{ name: string; mention_count: number }>;
    ADMINISTRATION: Array<{ name: string; mention_count: number }>;
  };
}

export interface HerbAnalysis {
  top_herbs: Array<{ name: string; count: number; formulas: string[] }>;
  cooccurrence_matrix: Record<string, Record<string, number>>;
}

export interface FormulaAnalysis {
  top_formulas: Array<{ name: string; herb_count: number; mention_count: number }>;
  formula_herb_network: {
    nodes: Array<{ id: string; name: string; type: "formula" | "herb" }>;
    edges: Array<{ source: string; target: string }>;
  };
}

export interface ClinicalPath {
  symptom_to_syndrome: Array<{ from: string; to: string; weight: number }>;
  syndrome_to_formula: Array<{ from: string; to: string; weight: number }>;
  full_sankey: {
    nodes: Array<{ id: string; name: string; category: string }>;
    links: Array<{ source: string; target: string; value: number }>;
  };
}

export interface TextAnalysis {
  article_lengths: Array<{ id: string; length: number; entities: number }>;
  entity_density: Array<{ article_id: string; density: number }>;
  entity_matrix: {
    articles: string[];
    entities: string[];
    matrix: number[][];
  };
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
}

export interface ModelSummary {
  ner: ModelRuntimeStatus;
  relation: ModelRuntimeStatus;
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
}

export interface AnnotationCandidatePayload {
  source_text: string;
  source_page?: string;
  session_payload: Record<string, unknown>;
  ner_model_dir?: string;
  relation_model_dir?: string;
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
}

export interface AnnotationCandidateStatusPayload {
  status: string;
}

export interface AnnotationCandidateListResponse {
  total: number;
  limit: number;
  results: AnnotationCandidateRecord[];
}

export interface QAAnswer {
  answer: string;
  confidence: number;
  entities?: NerPredictionEntity[];
  related_entities?: GraphEntity[];
  cypher?: string | null;
}
