export type AgentStatus = "OK" | "NEED_DATA" | "ERROR" | "CREATED";
export type ConversationMode = "concierge" | "shopping_analysis";
export type ReplyKind = "answer" | "discovery" | "confirmation_request" | "status_update" | "analysis_result";
export type SupportLevel = "live_analysis" | "discovery_only" | "unsupported";
export type CoverageConfidence = "strong" | "limited" | "weak";

export interface ClarificationPending {
  field: string;
  prompt: string;
  example?: string | null;
}

export interface NextAction {
  id: string;
  label: string;
  message: string;
  kind: "reply" | "confirm" | "cancel" | "continue";
  style: "primary" | "secondary" | "subtle";
  requiresConfirmation: boolean;
}

export interface PendingAction {
  type: "crawl_more" | "enable_autofill" | "resume_analysis";
  status: "awaiting_user" | "confirmed" | "cancelled";
  prompt: string;
  expiresAfterTurn?: number | null;
}

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
  coverageAudit: CoverageAudit;
  trace: TraceEvent[];
  missingEvidence: string[];
  blockingAgents: string[];
  conversationMode: ConversationMode;
  conversationIntent: string;
  replyKind: ReplyKind;
  handledBy: string;
  supportLevel: SupportLevel;
  nextActions: NextAction[];
  pendingAction: PendingAction | null;
  coverageConfidence: CoverageConfidence;
  checkoutReadiness: string;
  clarificationPending: ClarificationPending | null;
  sourceHealth: Record<string, unknown>;
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
  commerceSourceCoverage: number;
  freshnessSeconds: number;
  reviewCount: number;
  ratingCount: number;
  candidateCount?: number;
  blockedCommerceSources?: string[];
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
  meta?: AssistantMessageMeta | null;
}

export interface AssistantMessageMeta {
  summary?: string;
  verdict?: string | null;
  trust?: number | null;
  topReasons?: string[];
  missingEvidence?: string[];
  blockingAgents?: string[];
  traceRef?: string;
  traceCount?: number;
  conversationMode?: ConversationMode;
  conversationIntent?: string;
  replyKind?: ReplyKind;
  handledBy?: string;
  supportLevel?: SupportLevel;
  nextActions?: NextAction[];
  pendingAction?: PendingAction | null;
  clarificationPending?: ClarificationPending | null;
  coverageConfidence?: CoverageConfidence;
  checkoutReadiness?: string;
  sourceHealth?: Record<string, unknown>;
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

export interface ProductInsightAttribute {
  label: string;
  value: string;
}

export interface ProductInsight {
  analysisMode: "supplement" | "furniture" | "generic";
  headline: string;
  strengths: string[];
  cautions: string[];
  keyAttributes: ProductInsightAttribute[];
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
  canonicalProductId?: string;
  title: string;
  storeName: string;
  source: string;
  sourceUrl: string;
  imageUrl?: string | null;
  price: number;
  rating: number | null;
  shippingETA: string;
  returnPolicy: string;
  checkoutReady: boolean;
  constraintTier?: "strict" | "soft_5" | "soft_10" | "soft_15";
  constraintRelaxed?: boolean;
  evidenceRefs: string[];
  primaryOffer?: Offer;
  offers?: Offer[];
  sourceBreakdown?: SourceBreakdownItem[];
  ratingCoverage?: RatingCoverage;
  pros: string[];
  cons: string[];
  evidenceRows?: EvidenceRow[];
  ingredientAnalysis: IngredientAnalysis;
  productInsight: ProductInsight;
  scientificScore: ScientificScore;
  evidenceStats: EvidenceStats;
  trace: TraceEvent[];
}

export interface Offer {
  source: string;
  storeName: string;
  sourceUrl: string;
  price: number;
  rating: number | null;
  ratingCount: number;
  shippingETA: string;
  returnPolicy: string;
  imageUrl?: string | null;
}

export interface SourceBreakdownItem {
  source: string;
  count: number;
}

export interface RatingCoverage {
  ratedOfferCount: number;
  totalOfferCount: number;
}

export interface EvidenceRow {
  docId: string;
  source: string;
  qualityScore: number;
  promoSignals: string[];
  excerpt: string;
  positiveSignals: string[];
  negativeSignals: string[];
  sentimentScore: number;
}

export interface SessionProductsResponse {
  sessionId: string;
  items: SessionProduct[];
}

export interface CoverageAudit {
  isSufficient: boolean;
  missing: string[];
  sourceCoverage: number;
  commerceSourceCoverage?: number;
  reviewCount: number;
  ratingCount: number;
  candidateCount?: number;
  freshnessSeconds: number;
  blockedCommerceSources?: string[];
  cacheStatus?: string;
  catalogStatus?: string;
  crawlPerformed?: boolean;
}

export interface RecommendationResponse {
  sessionId: string;
  status: AgentStatus;
  reply: string;
  decision: AgentDecision | null;
  scientificScore: ScientificScore;
  evidenceStats: EvidenceStats;
  coverageAudit: CoverageAudit;
  trace: TraceEvent[];
  missingEvidence: string[];
  blockingAgents: string[];
  conversationMode: ConversationMode;
  conversationIntent: string;
  replyKind: ReplyKind;
  handledBy: string;
  supportLevel: SupportLevel;
  nextActions: NextAction[];
  pendingAction: PendingAction | null;
  coverageConfidence: CoverageConfidence;
  checkoutReadiness: string;
  clarificationPending: ClarificationPending | null;
  sourceHealth: Record<string, unknown>;
  state: Record<string, unknown>;
}

export interface CatalogMetricsResponse {
  totalRecords: number;
  sourceCounts: Record<string, number>;
  latestRetrievedAt: string | null;
  freshnessSeconds: number;
}
