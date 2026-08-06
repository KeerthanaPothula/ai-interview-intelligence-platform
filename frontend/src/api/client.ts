import type {
  ActivityTimelineResponse,
  AdminActivityEvent,
  AdminOverviewResponse,
  AdminUserListResponse,
  AdminUserResponse,
  AnalyticsOverviewResponse,
  AudioResponseResponse,
  BenchmarkResponse,
  CandidateListResponse,
  CandidateResponse,
  ChangePasswordRequest,
  CoachingPlanResponse,
  ConversationTurnResponse,
  CreateOrganizationRequest,
  CreateRecruiterRequest,
  DetailResponse,
  EndInterviewResponse,
  FollowUpQuestionResponse,
  FollowUpRequest,
  ForgotPasswordRequest,
  HealthResponse,
  InsightsResponse,
  InterviewAnalysisResponse,
  InterviewReadinessResponse,
  JobRoleCount,
  LiveInterviewSessionResponse,
  OrganizationListResponse,
  OrganizationResponse,
  ProcessingStatusResponse,
  QuestionResponse,
  RAGQuestionsResponse,
  ReadinessResponse,
  RefreshRequest,
  ResetPasswordRequest,
  ResumeAnalysisResponse,
  ResumeDocumentResponse,
  SessionCreate,
  SessionDetailResponse,
  SessionListResponse,
  SessionReportResponse,
  SessionTrendResponse,
  Token,
  TranscriptResponse,
  UpdateCandidateStatusRequest,
  UpdateUserRoleRequest,
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

// ---------------------------------------------------------------------------
// Token storage — supports "remember me": persisted in localStorage when
// checked (survives closing the browser), sessionStorage (cleared when the
// tab closes) when not. Only one of the two ever holds a token pair at a
// time; storeTokens() always clears the other so a stale copy can't be read
// back after switching modes across logins.
// ---------------------------------------------------------------------------

const ACCESS_TOKEN_KEY = 'aiip_access_token';
const REFRESH_TOKEN_KEY = 'aiip_refresh_token';

function getActiveStorage(): Storage | null {
  if (localStorage.getItem(ACCESS_TOKEN_KEY)) return localStorage;
  if (sessionStorage.getItem(ACCESS_TOKEN_KEY)) return sessionStorage;
  return null;
}

export function storeTokens(tokens: Token, rememberMe: boolean): void {
  const target = rememberMe ? localStorage : sessionStorage;
  const other = rememberMe ? sessionStorage : localStorage;
  target.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  if (tokens.refresh_token) {
    target.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  }
  other.removeItem(ACCESS_TOKEN_KEY);
  other.removeItem(REFRESH_TOKEN_KEY);
}

export function readStoredAccessToken(): string | null {
  return getActiveStorage()?.getItem(ACCESS_TOKEN_KEY) ?? null;
}

function readStoredRefreshToken(): string | null {
  return getActiveStorage()?.getItem(REFRESH_TOKEN_KEY) ?? null;
}

export function clearStoredTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// Global auth event hooks. AuthContext registers these once on mount so a
// 401 (expired/invalid/revoked access token) or a successful silent refresh
// can update React state and redirect — without every page component that
// calls the API needing its own token-lifecycle handling.
// ---------------------------------------------------------------------------

let onUnauthorized: (() => void) | null = null;
let onTokenRefreshed: ((tokens: Token) => void) | null = null;

export function registerUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export function registerTokenRefreshedHandler(
  handler: ((tokens: Token) => void) | null,
): void {
  onTokenRefreshed = handler;
}

// Exchanges the stored refresh token for a new access/refresh pair. Returns
// the new access token on success, or null if there is no refresh token, it
// has expired, or the network call fails — any of which means the caller
// should fall back to treating the request as unauthorized.
async function performSilentRefresh(): Promise<string | null> {
  const refreshTokenValue = readStoredRefreshToken();
  if (!refreshTokenValue) {
    return null;
  }
  try {
    const tokens = await refreshAccessToken(refreshTokenValue);
    const rememberMe = localStorage.getItem(ACCESS_TOKEN_KEY) !== null;
    storeTokens(tokens, rememberMe);
    onTokenRefreshed?.(tokens);
    return tokens.access_token;
  } catch {
    return null;
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

// Client errors (4xx) carry a `detail` string the backend has already
// written to be safe and specific to show verbatim — e.g. "An account with
// this email already exists.", "Incorrect email or password.", "This reset
// link is invalid or has expired." (see the auth router's own docstrings:
// "intentionally vague", "deliberately generic to avoid leaking token
// validity" — the backend already decided what's safe to say). Preferring
// it over a blanket per-status message is what actually fixes a 409 duplicate
// -email registration showing "This action is not allowed in the current
// state." instead of the real reason.
//
// Server errors (5xx) and anything that isn't parseable JSON with a string
// `detail` fall back to the generic per-status message — those are never
// written with an end user in mind (stack traces, "Internal Server Error",
// upstream gateway text) and must not be surfaced verbatim.
async function extractErrorMessage(response: Response): Promise<string> {
  if (response.status >= 400 && response.status < 500) {
    try {
      const body: unknown = await response.json();
      const detail = (body as { detail?: unknown } | null)?.detail;
      if (typeof detail === 'string' && detail.trim()) {
        return detail;
      }
    } catch {
      // Not JSON (or no body) — fall through to the generic message.
    }
  }
  return friendlyMessage(response.status);
}

async function doFetch(path: string, options: RequestInit, headers: Headers): Promise<Response> {
  try {
    return await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(
      0,
      `Cannot connect to the backend at ${BASE_URL}. ` +
        'Make sure the backend server is running (see README → Quick Start) and try again.',
    );
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

  let response = await doFetch(path, options, headers);

  // A 401 on an authenticated request may just mean the access token
  // expired — silently exchange the refresh token for a new pair and retry
  // once before giving up. Never attempted for anonymous requests (no
  // token was supplied, so there is no session to refresh) and never
  // retried more than once, to avoid looping against a genuinely invalid
  // session (e.g. a revoked refresh token).
  if (response.status === 401 && token) {
    const newAccessToken = await performSilentRefresh();
    if (newAccessToken) {
      headers.set('Authorization', `Bearer ${newAccessToken}`);
      response = await doFetch(path, options, headers);
    }
  }

  if (!response.ok) {
    if (response.status === 401) {
      onUnauthorized?.();
    }
    throw new ApiError(response.status, await extractErrorMessage(response));
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

// /ready intentionally returns HTTP 503 when not ready — that's a valid,
// meaningful response body we want to read, not an error to throw away, so
// this bypasses request()'s throw-on-!ok behavior.
export async function getSystemReadiness(): Promise<ReadinessResponse> {
  const response = await fetch(`${BASE_URL}/ready`);
  return (await response.json()) as ReadinessResponse;
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

// Not called directly by page components — used internally by
// performSilentRefresh() above. Exported so tests can exercise it in
// isolation without going through a full 401-triggered retry.
export function refreshAccessToken(refreshTokenValue: string): Promise<Token> {
  return request<Token>('/api/v1/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshTokenValue } satisfies RefreshRequest),
  });
}

export function logoutRequest(refreshTokenValue: string): Promise<DetailResponse> {
  return request<DetailResponse>('/api/v1/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshTokenValue } satisfies RefreshRequest),
  });
}

// Clears the local session immediately (synchronous — the caller's UI
// reflects logout right away regardless of network state), then
// best-effort notifies the backend to revoke the refresh token so it can't
// be redeemed later. A failed/unreachable revocation call never blocks or
// reverts the local logout — the token is already gone from storage.
export function logoutAndClearTokens(): void {
  const refreshTokenValue = readStoredRefreshToken();
  clearStoredTokens();
  if (refreshTokenValue) {
    logoutRequest(refreshTokenValue).catch(() => {
      // See comment above.
    });
  }
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

// ---------------------------------------------------------------------------
// Activity Timeline
// ---------------------------------------------------------------------------

export function getActivityTimeline(token: string): Promise<ActivityTimelineResponse> {
  return request<ActivityTimelineResponse>('/api/v1/analytics/activity', {}, token);
}

// ---------------------------------------------------------------------------
// AI Insights
// ---------------------------------------------------------------------------

export function getInsights(token: string): Promise<InsightsResponse> {
  return request<InsightsResponse>('/api/v1/analytics/insights', {}, token);
}

// ---------------------------------------------------------------------------
// Resume Analysis
// ---------------------------------------------------------------------------

export function analyzeResume(token: string): Promise<ResumeAnalysisResponse> {
  return request<ResumeAnalysisResponse>('/api/v1/documents/resume/analysis', {}, token);
}

// ---------------------------------------------------------------------------
// Recruiter Dashboard
// ---------------------------------------------------------------------------

export interface ListCandidatesParams {
  search?: string;
  status?: string;
  sortBy?: string;
  sortDir?: 'asc' | 'desc';
  skip?: number;
  limit?: number;
}

export function listCandidates(
  token: string,
  params: ListCandidatesParams = {},
): Promise<CandidateListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  if (params.status) query.set('status', params.status);
  if (params.sortBy) query.set('sort_by', params.sortBy);
  if (params.sortDir) query.set('sort_dir', params.sortDir);
  if (params.skip != null) query.set('skip', String(params.skip));
  if (params.limit != null) query.set('limit', String(params.limit));
  const qs = query.toString();
  return request<CandidateListResponse>(
    `/api/v1/recruiter/candidates${qs ? `?${qs}` : ''}`,
    {},
    token,
  );
}

export function updateCandidateStatus(
  sessionId: string,
  data: UpdateCandidateStatusRequest,
  token: string,
): Promise<CandidateResponse> {
  return request<CandidateResponse>(
    `/api/v1/recruiter/candidates/${sessionId}/status`,
    { method: 'PATCH', body: JSON.stringify(data) },
    token,
  );
}

export function deleteResume(token: string): Promise<void> {
  return request<void>('/api/v1/documents/resume/current', { method: 'DELETE' }, token);
}

// ---------------------------------------------------------------------------
// Change Password
// ---------------------------------------------------------------------------

export function changePassword(data: ChangePasswordRequest, token: string): Promise<DetailResponse> {
  return request<DetailResponse>('/api/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify(data),
  }, token);
}

// ---------------------------------------------------------------------------
// Admin Dashboard
// ---------------------------------------------------------------------------

export function getAdminOverview(token: string): Promise<AdminOverviewResponse> {
  return request<AdminOverviewResponse>('/api/v1/admin/overview', {}, token);
}

export interface ListAdminUsersParams {
  search?: string;
  skip?: number;
  limit?: number;
}

export function listAdminUsers(
  token: string,
  params: ListAdminUsersParams = {},
): Promise<AdminUserListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  if (params.skip != null) query.set('skip', String(params.skip));
  if (params.limit != null) query.set('limit', String(params.limit));
  const qs = query.toString();
  return request<AdminUserListResponse>(`/api/v1/admin/users${qs ? `?${qs}` : ''}`, {}, token);
}

export function listAdminJobRoles(token: string): Promise<JobRoleCount[]> {
  return request<JobRoleCount[]>('/api/v1/admin/jobs', {}, token);
}

export function listAdminActivity(token: string, limit = 20): Promise<AdminActivityEvent[]> {
  return request<AdminActivityEvent[]>(`/api/v1/admin/activity?limit=${limit}`, {}, token);
}

// ---------------------------------------------------------------------------
// Organization management (Phase 9 — Admin/Super Admin only)
// ---------------------------------------------------------------------------

export function listOrganizations(token: string): Promise<OrganizationListResponse> {
  return request<OrganizationListResponse>('/api/v1/admin/organizations', {}, token);
}

export function createOrganization(
  data: CreateOrganizationRequest,
  token: string,
): Promise<OrganizationResponse> {
  return request<OrganizationResponse>('/api/v1/admin/organizations', {
    method: 'POST',
    body: JSON.stringify(data),
  }, token);
}

export function deactivateOrganization(orgId: string, token: string): Promise<OrganizationResponse> {
  return request<OrganizationResponse>(
    `/api/v1/admin/organizations/${orgId}/deactivate`,
    { method: 'PATCH' },
    token,
  );
}

export function activateOrganization(orgId: string, token: string): Promise<OrganizationResponse> {
  return request<OrganizationResponse>(
    `/api/v1/admin/organizations/${orgId}/activate`,
    { method: 'PATCH' },
    token,
  );
}

export function createRecruiter(
  data: CreateRecruiterRequest,
  token: string,
): Promise<AdminUserResponse> {
  return request<AdminUserResponse>('/api/v1/admin/recruiters', {
    method: 'POST',
    body: JSON.stringify(data),
  }, token);
}

export function deactivateUser(userId: string, token: string): Promise<DetailResponse> {
  return request<DetailResponse>(
    `/api/v1/admin/users/${userId}/deactivate`,
    { method: 'PATCH' },
    token,
  );
}

export function activateUser(userId: string, token: string): Promise<DetailResponse> {
  return request<DetailResponse>(
    `/api/v1/admin/users/${userId}/activate`,
    { method: 'PATCH' },
    token,
  );
}

export function updateUserRole(
  userId: string,
  data: UpdateUserRoleRequest,
  token: string,
): Promise<DetailResponse> {
  return request<DetailResponse>(`/api/v1/admin/users/${userId}/role`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  }, token);
}
