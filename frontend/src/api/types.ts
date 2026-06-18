// Mirrors backend/app/schemas/*.py response/request shapes.

export type ResponseStatus = 'uploaded' | 'processing' | 'completed' | 'failed';

export type SessionStatus = 'draft' | 'in_progress' | 'processing' | 'completed';

// ---------------------------------------------------------------------------
// Auth (backend/app/schemas/auth.py)
// ---------------------------------------------------------------------------

export interface Token {
  access_token: string;
  token_type: string;
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
