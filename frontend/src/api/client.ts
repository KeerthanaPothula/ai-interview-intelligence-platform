import type {
  AnalyticsOverviewResponse,
  AudioResponseResponse,
  BenchmarkResponse,
  CoachingPlanResponse,
  ConversationTurnResponse,
  DetailResponse,
  EndInterviewResponse,
  FollowUpQuestionResponse,
  FollowUpRequest,
  ForgotPasswordRequest,
  HealthResponse,
  InterviewAnalysisResponse,
  InterviewReadinessResponse,
  LiveInterviewSessionResponse,
  ProcessingStatusResponse,
  QuestionResponse,
  RAGQuestionsResponse,
  ResetPasswordRequest,
  ResumeDocumentResponse,
  SessionCreate,
  SessionDetailResponse,
  SessionListResponse,
  SessionReportResponse,
  SessionTrendResponse,
  Token,
  TranscriptResponse,
  UserCreate,
  UserResponse,
  VoiceAnalysisResponse,
} from './types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// ApiError — a deliberately generic, user-facing message. Raw response
// bodies (FastAPI's `detail` field, stack traces, etc.) are never surfaced.
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function friendlyMessage(status: number): string {
  switch (status) {
    case 401:
      return 'Your session has expired. Please log in again.';
    case 403:
      return 'You do not have permission to perform this action.';
    case 404:
      return 'The requested item could not be found.';
    case 409:
      return 'This action is not allowed in the current state.';
    case 413:
      return 'The file is too large to upload.';
    case 415:
      return 'This file type is not supported.';
    case 422:
      return 'The submitted data is invalid. Please check the form and try again.';
    case 502:
    case 503:
      return 'The AI service is temporarily unavailable. Please try again later.';
    default:
      return 'Something went wrong. Please try again.';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers);

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const isFormLike =
    options.body instanceof FormData || options.body instanceof URLSearchParams;
  if (options.body && !isFormLike && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(
      0,
      `Cannot connect to the backend at ${BASE_URL}. ` +
        'Make sure the backend server is running (see README → Quick Start) and try again.',
    );
  }

  if (!response.ok) {
    throw new ApiError(response.status, friendlyMessage(response.status));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Health / features (no auth)
// ---------------------------------------------------------------------------

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function login(email: string, password: string): Promise<Token> {
  const body = new URLSearchParams();
  body.set('username', email);
  body.set('password', password);
  return request<Token>('/api/v1/auth/login', { method: 'POST', body });
}

export function register(data: UserCreate): Promise<UserResponse> {
  return request<UserResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function getMe(token: string): Promise<UserResponse> {
  return request<UserResponse>('/api/v1/auth/me', {}, token);
}

export function forgotPassword(data: ForgotPasswordRequest): Promise<DetailResponse> {
  return request<DetailResponse>('/api/v1/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function resetPassword(data: ResetPasswordRequest): Promise<DetailResponse> {
  return request<DetailResponse>('/api/v1/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ---------------------------------------------------------------------------
// Interview sessions & questions
// ---------------------------------------------------------------------------

export function listSessions(token: string): Promise<SessionListResponse[]> {
  return request<SessionListResponse[]>('/api/v1/interviews/', {}, token);
}

export function createSession(
  data: SessionCreate,
  token: string,
): Promise<SessionDetailResponse> {
  return request<SessionDetailResponse>('/api/v1/interviews/', {
    method: 'POST',
    body: JSON.stringify(data),
  }, token);
}

export function getSession(sessionId: string, token: string): Promise<SessionDetailResponse> {
  return request<SessionDetailResponse>(`/api/v1/interviews/${sessionId}`, {}, token);
}

export function generateQuestions(
  sessionId: string,
  token: string,
): Promise<QuestionResponse[]> {
  return request<QuestionResponse[]>(
    `/api/v1/interviews/${sessionId}/questions/generate`,
    { method: 'POST' },
    token,
  );
}

// ---------------------------------------------------------------------------
// Audio responses, processing status, transcript, analysis
// ---------------------------------------------------------------------------

export function listResponses(
  sessionId: string,
  token: string,
): Promise<AudioResponseResponse[]> {
  return request<AudioResponseResponse[]>(
    `/api/v1/interviews/${sessionId}/responses`,
    {},
    token,
  );
}

export function uploadResponse(
  sessionId: string,
  questionId: string,
  file: File,
  token: string,
): Promise<AudioResponseResponse> {
  const formData = new FormData();
  formData.append('question_id', questionId);
  formData.append('file', file);
  return request<AudioResponseResponse>(
    `/api/v1/interviews/${sessionId}/responses`,
    { method: 'POST', body: formData },
    token,
  );
}

export function getProcessingStatus(
  responseId: string,
  token: string,
): Promise<ProcessingStatusResponse> {
  return request<ProcessingStatusResponse>(
    `/api/v1/responses/${responseId}/processing-status`,
    {},
    token,
  );
}

export function getTranscript(responseId: string, token: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/api/v1/responses/${responseId}/transcript`, {}, token);
}

export function getAnalysis(
  responseId: string,
  token: string,
): Promise<InterviewAnalysisResponse> {
  return request<InterviewAnalysisResponse>(`/api/v1/responses/${responseId}/analysis`, {}, token);
}

export function getVoiceAnalysis(
  responseId: string,
  token: string,
): Promise<VoiceAnalysisResponse> {
  return request<VoiceAnalysisResponse>(
    `/api/v1/responses/${responseId}/voice-analysis`,
    {},
    token,
  );
}

// ---------------------------------------------------------------------------
// Analytics Dashboard
// ---------------------------------------------------------------------------

export function getAnalyticsOverview(token: string): Promise<AnalyticsOverviewResponse> {
  return request<AnalyticsOverviewResponse>('/api/v1/analytics/overview', {}, token);
}

export function getAnalyticsTrends(token: string): Promise<SessionTrendResponse[]> {
  return request<SessionTrendResponse[]>('/api/v1/analytics/trends', {}, token);
}

// ---------------------------------------------------------------------------
// Follow-Up Questions
// ---------------------------------------------------------------------------

export function generateFollowUp(
  sessionId: string,
  body: FollowUpRequest,
  token: string,
): Promise<FollowUpQuestionResponse> {
  return request<FollowUpQuestionResponse>(
    `/api/v1/interviews/${sessionId}/follow-up-question`,
    { method: 'POST', body: JSON.stringify(body) },
    token,
  );
}

export function getConversationHistory(
  sessionId: string,
  token: string,
): Promise<ConversationTurnResponse[]> {
  return request<ConversationTurnResponse[]>(
    `/api/v1/interviews/${sessionId}/conversation-history`,
    {},
    token,
  );
}

// ---------------------------------------------------------------------------
// Session Reports
// ---------------------------------------------------------------------------

export function generateReport(sessionId: string, token: string): Promise<SessionReportResponse> {
  return request<SessionReportResponse>(
    `/api/v1/interviews/${sessionId}/report/generate`,
    { method: 'POST' },
    token,
  );
}

export function getReport(sessionId: string, token: string): Promise<SessionReportResponse> {
  return request<SessionReportResponse>(
    `/api/v1/interviews/${sessionId}/report`,
    {},
    token,
  );
}

// ---------------------------------------------------------------------------
// Live Conversational AI Interviewer
// ---------------------------------------------------------------------------

export function startLiveInterview(
  data: { job_role: string; job_description: string; max_turns: number },
  token: string,
): Promise<LiveInterviewSessionResponse> {
  return request<LiveInterviewSessionResponse>(
    '/api/v1/live-interviews/',
    { method: 'POST', body: JSON.stringify(data) },
    token,
  );
}

export function nextLiveQuestion(
  sessionId: string,
  body: { response_text?: string; audio_response_id?: string },
  token: string,
): Promise<LiveInterviewSessionResponse> {
  return request<LiveInterviewSessionResponse>(
    `/api/v1/live-interviews/${sessionId}/next-question`,
    { method: 'POST', body: JSON.stringify(body) },
    token,
  );
}

export function getLiveConversation(
  sessionId: string,
  token: string,
): Promise<LiveInterviewSessionResponse> {
  return request<LiveInterviewSessionResponse>(
    `/api/v1/live-interviews/${sessionId}/conversation`,
    {},
    token,
  );
}

export function endLiveInterview(
  sessionId: string,
  token: string,
): Promise<EndInterviewResponse> {
  return request<EndInterviewResponse>(
    `/api/v1/live-interviews/${sessionId}/end`,
    { method: 'POST' },
    token,
  );
}

// ---------------------------------------------------------------------------
// Resume & RAG
// ---------------------------------------------------------------------------

export function uploadResume(file: File, token: string): Promise<ResumeDocumentResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return request<ResumeDocumentResponse>('/api/v1/documents/resume/upload', {
    method: 'POST',
    body: formData,
  }, token);
}

export function getCurrentResume(token: string): Promise<ResumeDocumentResponse> {
  return request<ResumeDocumentResponse>('/api/v1/documents/resume/current', {}, token);
}

export function generateRagQuestions(
  sessionId: string,
  count: number,
  token: string,
): Promise<RAGQuestionsResponse> {
  return request<RAGQuestionsResponse>(
    `/api/v1/documents/interviews/${sessionId}/generate-rag-questions`,
    { method: 'POST', body: JSON.stringify({ count }) },
    token,
  );
}

// ---------------------------------------------------------------------------
// Readiness & Coaching
// ---------------------------------------------------------------------------

export function generateReadiness(
  sessionId: string,
  token: string,
): Promise<InterviewReadinessResponse> {
  return request<InterviewReadinessResponse>(
    `/api/v1/interviews/${sessionId}/readiness`,
    { method: 'POST' },
    token,
  );
}

export function getReadiness(
  sessionId: string,
  token: string,
): Promise<InterviewReadinessResponse> {
  return request<InterviewReadinessResponse>(
    `/api/v1/interviews/${sessionId}/readiness`,
    {},
    token,
  );
}

export function generateCoachingPlan(
  sessionId: string,
  token: string,
): Promise<CoachingPlanResponse> {
  return request<CoachingPlanResponse>(
    `/api/v1/interviews/${sessionId}/coaching-plan`,
    { method: 'POST' },
    token,
  );
}

export function getCoachingPlan(
  sessionId: string,
  token: string,
): Promise<CoachingPlanResponse> {
  return request<CoachingPlanResponse>(
    `/api/v1/interviews/${sessionId}/coaching-plan`,
    {},
    token,
  );
}

export function getBenchmarks(token: string): Promise<BenchmarkResponse> {
  return request<BenchmarkResponse>('/api/v1/analytics/benchmarks', {}, token);
}
