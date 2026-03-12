export type AgentStatus = "OK" | "NEED_DATA" | "ERROR" | "CREATED";

export interface CreateSessionResponse {
  sessionId: string;
  createdAt: string;
}

export interface ChatResponse {
  sessionId: string;
  status: AgentStatus;
  reply: string;
  decision: AgentDecision | null;
  scientificScore: ScientificScore;
  evidenceStats: EvidenceStats;
  trace: TraceEvent[];
  missingEvidence: string[];
  blockingAgents: string[];
  state: Record<string, unknown>;
}

export interface AgentDecision {
  verdict: "BUY" | "WAIT" | "AVOID";
  finalTrust: number;
  confidence: number;
  topReasons: string[];
  riskFlags: string[];
  whyRankedHere: string[];
  selectedCandidate: CandidateProduct | null;
}

export interface ScientificScore {
  ratingReliability: number;
  spamAuthenticity: number;
  absaAlignment: number;
  visualReliability: number;
  finalTrust: number;
}

export interface EvidenceStats {
  sourceCoverage: number;
  freshnessSeconds: number;
  reviewCount: number;
  ratingCount: number;
  missingFields: string[];
}

export interface TraceEvent {
  agent?: string;
  step: string;
  status: string;
  detail?: string;
}

export interface SessionMessage {
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

export interface SessionSnapshotResponse {
  sessionId: string;
  createdAt: string;
  updatedAt: string;
  messages: SessionMessage[];
  checkpointState: Record<string, unknown> | null;
}

export interface SessionSummary {
  sessionId: string;
  createdAt: string;
  updatedAt: string;
  title: string;
  status: AgentStatus;
  verdict: "BUY" | "WAIT" | "AVOID" | null;
}

export interface SessionListResponse {
  items: SessionSummary[];
  nextCursor: string | null;
}

export interface IngredientSignal {
  ingredient: string;
  note: string;
}

export interface IngredientAnalysis {
  score: number;
  summary: string;
  proteinSource: string;
  beneficialSignals: IngredientSignal[];
  redFlags: IngredientSignal[];
  confidence: number;
  references: string[];
}

export interface CandidateProduct {
  title: string;
  sourceUrl: string;
  price: number;
  rating: number | null;
  shippingETA: string;
  returnPolicy: string;
  checkoutReady: boolean;
  evidenceRefs: string[];
}

export interface SessionProduct {
  productId: string;
  title: string;
  storeName: string;
  source: string;
  sourceUrl: string;
  price: number;
  rating: number | null;
  shippingETA: string;
  returnPolicy: string;
  checkoutReady: boolean;
  evidenceRefs: string[];
  pros: string[];
  cons: string[];
  ingredientAnalysis: IngredientAnalysis;
  scientificScore: ScientificScore;
  evidenceStats: EvidenceStats;
  trace: TraceEvent[];
}

export interface SessionProductsResponse {
  sessionId: string;
  items: SessionProduct[];
}
