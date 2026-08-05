// Mirrors backend/app/schemas/*.py response/request shapes.

// ---------------------------------------------------------------------------
// Health (/health — no auth required)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  environment: string;
  version: string;
  audio_processing_enabled: boolean;
}

export interface ReadinessCheck {
  ok: boolean;
  error?: string | null;
}

export interface ReadinessResponse {
  status: 'ready' | 'not_ready';
  checks: {
    database: ReadinessCheck;
    ai_provider_configured: ReadinessCheck;
  };
}

export type ResponseStatus = 'uploaded' | 'processing' | 'completed' | 'failed';

export type SessionStatus = 'draft' | 'in_progress' | 'processing' | 'completed';

// ---------------------------------------------------------------------------
// Auth (backend/app/schemas/auth.py)
// ---------------------------------------------------------------------------

export interface Token {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface UserCreate {
  email: string;
  password: string;
  full_name: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface DetailResponse {
  detail: string;
}

// ---------------------------------------------------------------------------
// Interviews (backend/app/schemas/interview.py)
// ---------------------------------------------------------------------------

export interface SessionCreate {
  title: string;
  job_role: string;
  job_description: string;
}

export interface QuestionResponse {
  id: string;
  body: string;
  sequence_order: number;
  category: string | null;
  source: string;
  created_at: string;
}

export interface SessionListResponse {
  id: string;
  title: string;
  job_role: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
}

export interface SessionDetailResponse {
  id: string;
  title: string;
  job_role: string;
  job_description: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  questions: QuestionResponse[];
  response_count: number;
}

// ---------------------------------------------------------------------------
// Responses / processing (backend/app/schemas/analysis.py)
// ---------------------------------------------------------------------------

export interface AudioResponseResponse {
  id: string;
  question_id: string;
  status: ResponseStatus;
  created_at: string;
}

export interface ProcessingStatusResponse {
  response_id: string;
  status: ResponseStatus;
  transcript_id: string | null;
  analysis_id: string | null;
  error_message: string | null;
}

export interface TranscriptResponse {
  id: string;
  audio_response_id: string;
  text: string;
  language: string | null;
  duration_seconds: number | null;
  word_count: number;
  created_at: string;
}

export interface InterviewAnalysisResponse {
  id: string;
  audio_response_id: string;
  transcript_id: string | null;
  // Decimal fields are serialized as strings by Pydantic, e.g. "7.5".
  overall_score: string;
  communication_score: string;
  technical_score: string;
  problem_solving_score: string;
  confidence_score: string;
  strengths: string | null;
  weaknesses: string | null;
  detailed_feedback: string | null;
  model_used: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Voice Analytics (backend/app/schemas/features.py)
// ---------------------------------------------------------------------------

export interface VoiceAnalysisResponse {
  id: string;
  audio_response_id: string;
  speaking_rate: number | null;
  average_pause_duration: number | null;
  total_pause_time: number | null;
  long_pause_count: number | null;
  filler_word_count: number | null;
  energy_consistency: number | null;
  confidence_score: number | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Analytics Dashboard (backend/app/schemas/features.py)
// ---------------------------------------------------------------------------

export interface AnalyticsOverviewResponse {
  total_sessions: number;
  completed_sessions: number;
  average_overall_score: number | null;
  total_responses_analyzed: number;
  strongest_skill: string | null;
  weakest_skill: string | null;
  improvement_score: number | null;
}

export interface SessionTrendResponse {
  session_id: string;
  session_title: string;
  created_at: string;
  average_overall_score: number | null;
  average_communication_score: number | null;
  average_technical_score: number | null;
  average_problem_solving_score: number | null;
  average_confidence_score: number | null;
}

// ---------------------------------------------------------------------------
// Follow-Up Questions (backend/app/schemas/features.py)
// ---------------------------------------------------------------------------

export interface FollowUpRequest {
  question_id: string;
  response_id: string;
}

export interface FollowUpQuestionResponse {
  id: string;
  session_id: string;
  original_question_id: string;
  parent_audio_response_id: string | null;
  body: string;
  depth: number;
  created_at: string;
}

export interface ConversationTurnResponse {
  question_id: string;
  question_body: string;
  sequence_order: number;
  follow_ups: FollowUpQuestionResponse[];
}

// ---------------------------------------------------------------------------
// Session Report (backend/app/schemas/features.py)
// ---------------------------------------------------------------------------

export interface SessionReportResponse {
  id: string;
  session_id: string;
  overall_performance: string | null;
  final_score: number | null;
  confidence_score: number | null;
  communication_score: number | null;
  technical_score: number | null;
  problem_solving_score: number | null;
  strengths: string | null;
  weaknesses: string | null;
  improvement_plan: string | null;
  readiness_level: string | null;
  model_used: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Live Conversational AI Interviewer (backend/app/schemas/conversation.py)
// ---------------------------------------------------------------------------

export interface LiveConversationTurnResponse {
  id: string;
  live_session_id: string;
  turn_number: number;
  question_text: string;
  difficulty_level: number;
  response_text: string | null;
  audio_response_id: string | null;
  created_at: string;
}

export interface LiveInterviewSessionResponse {
  id: string;
  user_id: string;
  job_role: string;
  job_description: string;
  status: 'active' | 'completed';
  current_turn: number;
  max_turns: number;
  created_at: string;
  completed_at: string | null;
  turns: LiveConversationTurnResponse[];
  current_question: LiveConversationTurnResponse | null;
}

export interface EndInterviewResponse {
  session_id: string;
  status: string;
  total_turns: number;
  summary: string;
  turns: LiveConversationTurnResponse[];
}

// ---------------------------------------------------------------------------
// Resume & RAG (backend/app/schemas/documents.py)
// ---------------------------------------------------------------------------

export interface ResumeDocumentResponse {
  id: string;
  user_id: string;
  filename: string;
  extracted_text: string | null;
  created_at: string;
  chunk_count: number;
}

export interface RAGQuestionItem {
  body: string;
  category: string;
  sequence_order: number;
}

export interface RAGQuestionsResponse {
  session_id: string;
  questions: RAGQuestionItem[];
  resume_context_used: boolean;
  chunks_retrieved: number;
}

// ---------------------------------------------------------------------------
// Readiness & Coaching (backend/app/schemas/prediction.py)
// ---------------------------------------------------------------------------

/**
 * Transparent weighted-average score, not a trained ML model's prediction —
 * see docs/AI_PIPELINE.md §9 for the exact formula.
 */
export interface InterviewReadinessResponse {
  id: string;
  session_id: string;
  readiness_score: number | null;
  percentile_rank: number | null;
  readiness_level: string | null;
  scoring_method: string | null;
  created_at: string;
}

export interface CoachingPlanResponse {
  id: string;
  session_id: string;
  plan_7_day: string[] | null;
  plan_14_day: string[] | null;
  plan_30_day: string[] | null;
  focus_areas: string[] | null;
  model_used: string | null;
  created_at: string;
}

export interface BenchmarkResponse {
  user_average_score: number | null;
  percentile_rank: number | null;
  total_platform_responses: number;
  user_responses_analyzed: number;
}

// ---------------------------------------------------------------------------
// Activity Timeline (backend/app/schemas/features.py)
// ---------------------------------------------------------------------------

export interface ActivityEvent {
  event_type: string;
  title: string;
  subtitle: string | null;
  created_at: string;
}

export interface ActivityTimelineResponse {
  events: ActivityEvent[];
}

// ---------------------------------------------------------------------------
// AI Insights (backend/app/schemas/features.py)
// ---------------------------------------------------------------------------

export interface InsightItem {
  text: string;
  kind: 'positive' | 'warning' | 'info';
}

export interface InsightsResponse {
  insights: InsightItem[];
}

// ---------------------------------------------------------------------------
// Resume Analysis (backend/app/schemas/documents.py)
// ---------------------------------------------------------------------------

export interface ResumeAnalysisResponse {
  ats_score: number;
  skills: string[];
  missing_skills: string[];
  keywords: string[];
  suggestions: string[];
  word_count: number;
}

// ---------------------------------------------------------------------------
// Change Password (backend/app/schemas/auth.py)
// ---------------------------------------------------------------------------

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

// ---------------------------------------------------------------------------
// Recruiter Dashboard (backend/app/schemas/recruiter.py)
// ---------------------------------------------------------------------------

export type CandidateStatus = 'shortlisted' | 'reviewing' | 'pending' | 'rejected';

export interface CandidateResponse {
  id: string;
  session_id: string;
  name: string;
  email: string;
  role: string;
  resume_score: number | null;
  interview_score: number;
  communication: number;
  technical: number;
  sessions_completed: number;
  status: CandidateStatus;
  applied_days: number;
}

export interface CandidateSummary {
  total_candidates: number;
  shortlisted_count: number;
  avg_resume_score: number | null;
  avg_interview_score: number | null;
}

export interface CandidateListResponse {
  items: CandidateResponse[];
  total: number;
  summary: CandidateSummary;
}

// ---------------------------------------------------------------------------
// Admin Dashboard (backend/app/schemas/admin.py)
// ---------------------------------------------------------------------------

export interface AdminUserResponse {
  id: string;
  full_name: string;
  email: string;
  created_at: string;
  sessions_completed: number;
  latest_session_at: string | null;
}

export interface AdminUserListResponse {
  items: AdminUserResponse[];
  total: number;
}

export interface AiUsageStats {
  questions_generated: number;
  transcriptions_completed: number;
  evaluations_completed: number;
  reports_generated: number;
  coaching_plans_generated: number;
  predictions_generated: number;
}

export interface StorageStats {
  audio_bytes: number;
  audio_file_count: number;
  resume_bytes: number;
  resume_file_count: number;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface AdminOverviewResponse {
  total_users: number;
  total_sessions: number;
  sessions_by_status: Record<string, number>;
  total_reports: number;
  avg_platform_score: number | null;
  total_resumes: number;
  ai_usage: AiUsageStats;
  storage: StorageStats;
  signups_last_30_days: DailyCount[];
  sessions_last_30_days: DailyCount[];
}

export interface JobRoleCount {
  role: string;
  session_count: number;
}

export interface AdminActivityEvent {
  event_type: string;
  title: string;
  subtitle: string | null;
  created_at: string;
}
