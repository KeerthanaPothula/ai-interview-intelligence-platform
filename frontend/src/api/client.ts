import type {
  AudioResponseResponse,
  InterviewAnalysisResponse,
  ProcessingStatusResponse,
  QuestionResponse,
  SessionCreate,
  SessionDetailResponse,
  SessionListResponse,
  Token,
  TranscriptResponse,
  UserCreate,
  UserResponse,
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
    throw new ApiError(0, 'Unable to reach the server. Please check your connection and try again.');
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
