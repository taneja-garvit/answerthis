// Mirrors the backend's Pydantic response schemas (backend/app/schemas/*).

export type Verdict = "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED" | "UNVERIFIABLE";
export type ConfidenceLevel = "LOW" | "MEDIUM" | "HIGH";
export type ReviewDecision = "KEEP" | "QUALIFY" | "REPLACE" | "REMOVE";
export type ReviewStatus = "NEEDS_REVIEW" | "REVIEWED";
export type ClaimStatus = "PENDING" | "PROCESSING" | "READY" | "ERROR";
export type AccessLevel = "FULL_TEXT" | "ABSTRACT" | "USER_PROVIDED";
export type EvidenceAvailability = AccessLevel | "UNAVAILABLE";
export type SourceAccessStatus = "AVAILABLE" | "ABSTRACT_ONLY" | "UNAVAILABLE";
export type DraftAnalysisStatus = "NOT_ANALYZED" | "ANALYZING" | "ANALYZED" | "FAILED";
export type IssueType =
  | "FIGURE_MISMATCH"
  | "POPULATION_MISMATCH"
  | "OUTCOME_MISMATCH"
  | "OVERGENERALIZATION"
  | "CAUSAL_OVERSTATEMENT"
  | "WORDING_STRENGTH"
  | "SOURCE_MISMATCH"
  | "INSUFFICIENT_EVIDENCE"
  | "EVIDENCE_UNAVAILABLE"
  | "OTHER";

/** Crossref/seed authors use given/family; OpenAlex uses name. */
export interface Author {
  given?: string | null;
  family?: string | null;
  name?: string | null;
  orcid?: string | null;
}

export interface Issue {
  type: IssueType;
  description: string;
  claim_value: string | null;
  evidence_value: string | null;
}

export interface SourceSummary {
  id: string;
  doi: string | null;
  title: string;
  authors: Author[];
  journal: string | null;
  publication_year: number | null;
  open_access_url: string | null;
  access_status: SourceAccessStatus;
  citation_marker: string | null;
}

export interface Evidence {
  id: string;
  source_id: string;
  passage: string;
  location: string | null;
  access_level: AccessLevel;
  retrieval_method: string;
  /** Lexical relevance to the claim; never a measure of support. */
  retrieval_score: number | null;
  rank: number;
  is_synthetic: boolean;
}

export interface Assessment {
  id: string;
  verdict: Verdict;
  /** Confidence in the claim-vs-evidence classification; null when no model judged. */
  confidence_level: ConfidenceLevel | null;
  confidence: number | null;
  issues: Issue[];
  explanation: string;
  suggested_revision: string | null;
  evidence_ids: string[];
  provider: string;
  model: string | null;
  prompt_version: string | null;
  generation_metadata: Record<string, unknown>;
  created_at: string;
}

export interface Review {
  id: string;
  decision: ReviewDecision;
  reviewer_note: string | null;
  revised_claim: string | null;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
}

export interface Claim {
  id: string;
  draft_id: string;
  project_id: string;
  order: number;
  claim_text: string;
  original_sentence: string;
  citation_marker: string | null;
  status: ClaimStatus;
  processing_error: string | null;
  source: SourceSummary | null;
  sources: SourceSummary[];
  evidence: Evidence[];
  evidence_availability: { status: EvidenceAvailability; message: string };
  assessment: Assessment | null;
  review: Review | null;
  review_status: ReviewStatus;
}

export interface DraftClaims {
  draft_id: string;
  project_id: string;
  claims: Claim[];
}

export interface DraftSummary {
  id: string;
  char_count: number;
  claim_count: number;
  analysis_status: DraftAnalysisStatus;
  created_at: string;
}

export interface Project {
  id: string;
  title: string;
  description: string | null;
  status: "ACTIVE" | "ARCHIVED";
  is_demo: boolean;
  drafts: DraftSummary[];
  created_at: string;
  updated_at: string;
}

export interface Draft {
  id: string;
  project_id: string;
  original_text: string;
  char_count: number;
  analysis_status: DraftAnalysisStatus;
  analyzed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Progress {
  project_id: string;
  total_claims: number;
  reviewed_claims: number;
  remaining_claims: number;
  completion_percentage: number;
  is_complete: boolean;
  human_decisions: Record<ReviewDecision, number>;
  ai_verdicts: Record<Verdict | "NOT_ASSESSED", number>;
}

export interface AnalysisResult {
  draft_id: string;
  project_id: string;
  analysis_status: DraftAnalysisStatus;
  rerun: boolean;
  claims_extracted: number;
  claims_processed: number;
  claims_reused: number;
  claims_assessed: number;
  claims_unverifiable: number;
  claims_failed: number;
  llm_provider: string;
  llm_model: string | null;
  llm_calls: number;
  claims: Claim[];
}

export interface ReviewInput {
  decision: ReviewDecision;
  reviewer_note: string | null;
  revised_claim: string | null;
}

export interface ApiErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string | null; details?: ApiErrorDetail[] };
}
