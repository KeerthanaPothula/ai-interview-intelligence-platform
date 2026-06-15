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
