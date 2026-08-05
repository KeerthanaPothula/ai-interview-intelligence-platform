import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  clearStoredTokens,
  getMe,
  readStoredAccessToken,
  register,
  registerTokenRefreshedHandler,
  registerUnauthorizedHandler,
  storeTokens,
} from './client';

const MOCK_USER = {
  id: 'user-1',
  email: 'jane@example.com',
  full_name: 'Jane Smith',
  created_at: '2026-01-01T00:00:00Z',
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Node 22+'s built-in `localStorage`/`sessionStorage` globals shadow
// jsdom's implementation in this Vitest/Node combination, and Node's
// version throws on .clear() without a `--localstorage-file` backing file.
// A minimal in-memory Storage polyfill sidesteps the collision entirely —
// this file only needs get/set/removeItem/clear, which is all client.ts
// itself calls.
class FakeStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

let fakeLocalStorage: FakeStorage;
let fakeSessionStorage: FakeStorage;

beforeEach(() => {
  fakeLocalStorage = new FakeStorage();
  fakeSessionStorage = new FakeStorage();
  vi.stubGlobal('localStorage', fakeLocalStorage);
  vi.stubGlobal('sessionStorage', fakeSessionStorage);
  registerUnauthorizedHandler(null);
  registerTokenRefreshedHandler(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
  registerUnauthorizedHandler(null);
  registerTokenRefreshedHandler(null);
});

describe('token storage', () => {
  it('storeTokens(rememberMe=true) writes to localStorage, not sessionStorage', () => {
    storeTokens({ access_token: 'a1', refresh_token: 'r1', token_type: 'bearer' }, true);
    expect(localStorage.getItem('aiip_access_token')).toBe('a1');
    expect(localStorage.getItem('aiip_refresh_token')).toBe('r1');
    expect(sessionStorage.getItem('aiip_access_token')).toBeNull();
  });

  it('storeTokens(rememberMe=false) writes to sessionStorage, not localStorage', () => {
    storeTokens({ access_token: 'a1', refresh_token: 'r1', token_type: 'bearer' }, false);
    expect(sessionStorage.getItem('aiip_access_token')).toBe('a1');
    expect(localStorage.getItem('aiip_access_token')).toBeNull();
  });

  it('switching remember-me mode clears the previous storage', () => {
    storeTokens({ access_token: 'a1', refresh_token: 'r1', token_type: 'bearer' }, true);
    storeTokens({ access_token: 'a2', refresh_token: 'r2', token_type: 'bearer' }, false);
    expect(localStorage.getItem('aiip_access_token')).toBeNull();
    expect(sessionStorage.getItem('aiip_access_token')).toBe('a2');
  });

  it('readStoredAccessToken finds a token in either storage', () => {
    expect(readStoredAccessToken()).toBeNull();
    storeTokens({ access_token: 'a1', refresh_token: 'r1', token_type: 'bearer' }, false);
    expect(readStoredAccessToken()).toBe('a1');
  });

  it('clearStoredTokens wipes both storages', () => {
    storeTokens({ access_token: 'a1', refresh_token: 'r1', token_type: 'bearer' }, true);
    clearStoredTokens();
    expect(localStorage.getItem('aiip_access_token')).toBeNull();
    expect(sessionStorage.getItem('aiip_access_token')).toBeNull();
  });
});

describe('request() silent refresh-and-retry on 401', () => {
  it('transparently refreshes and retries once, returning the retried result', async () => {
    storeTokens({ access_token: 'expired-token', refresh_token: 'valid-refresh', token_type: 'bearer' }, true);

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void init; // present only so .mock.calls[i][1] below is typed, not `never`
      const url = String(input);
      if (url.includes('/auth/me')) {
        // First call: expired token -> 401. Second call (after refresh):
        // succeeds because doFetch() re-reads the Authorization header,
        // which by then carries the refreshed token.
        if (fetchMock.mock.calls.filter((c) => String(c[0]).includes('/auth/me')).length === 1) {
          return Promise.resolve(jsonResponse(401, { detail: 'expired' }));
        }
        return Promise.resolve(jsonResponse(200, MOCK_USER));
      }
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(
          jsonResponse(200, {
            access_token: 'new-token',
            refresh_token: 'new-refresh',
            token_type: 'bearer',
          }),
        );
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onUnauthorized = vi.fn();
    const onTokenRefreshed = vi.fn();
    registerUnauthorizedHandler(onUnauthorized);
    registerTokenRefreshedHandler(onTokenRefreshed);

    const result = await getMe('expired-token');

    expect(result).toEqual(MOCK_USER);
    expect(onTokenRefreshed).toHaveBeenCalledWith(
      expect.objectContaining({ access_token: 'new-token' }),
    );
    expect(onUnauthorized).not.toHaveBeenCalled();
    // Access token in storage is now the refreshed one.
    expect(readStoredAccessToken()).toBe('new-token');

    const meCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/auth/me'));
    expect(meCalls).toHaveLength(2);
    const secondCallHeaders = meCalls[1][1]?.headers as Headers;
    expect(secondCallHeaders.get('Authorization')).toBe('Bearer new-token');
  });

  it('falls back to unauthorized when there is no refresh token to use', async () => {
    // No storeTokens() call — nothing in storage to refresh with.
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(401, { detail: 'expired' })));
    vi.stubGlobal('fetch', fetchMock);

    const onUnauthorized = vi.fn();
    registerUnauthorizedHandler(onUnauthorized);

    await expect(getMe('stale-token')).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
    // Only the original call was attempted — no refresh endpoint to call.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('falls back to unauthorized when the refresh token itself is rejected', async () => {
    storeTokens({ access_token: 'expired-token', refresh_token: 'revoked-refresh', token_type: 'bearer' }, true);

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(jsonResponse(401, { detail: 'refresh token revoked' }));
      }
      return Promise.resolve(jsonResponse(401, { detail: 'expired' }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const onUnauthorized = vi.fn();
    registerUnauthorizedHandler(onUnauthorized);

    await expect(getMe('expired-token')).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it('never attempts a refresh for anonymous (no-token) requests', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(401, { detail: 'nope' })));
    vi.stubGlobal('fetch', fetchMock);

    // getHealth() is called with no token — simulate by importing it fresh.
    const { getHealth } = await import('./client');
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('error messages surface the backend\'s actual detail for 4xx, not a generic string', () => {
  // Regression coverage for the bug where registering with a duplicate
  // email showed "This action is not allowed in the current state."
  // instead of the backend's real "An account with this email already
  // exists." — request() was discarding the response body entirely for
  // every error and substituting a blanket per-status-code message.

  it('a 409 with a string detail is shown verbatim (the duplicate-email regression)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(409, { detail: 'An account with this email already exists.' }),
        ),
      ),
    );

    await expect(
      register({ email: 'jane@example.com', password: 'password123', full_name: 'Jane Smith' }),
    ).rejects.toMatchObject({
      status: 409,
      message: 'An account with this email already exists.',
    });
  });

  it('a 401 with a string detail is shown verbatim (e.g. "Incorrect email or password.")', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(401, { detail: 'Incorrect email or password.' }))),
    );

    await expect(getMe('some-token')).rejects.toMatchObject({
      message: 'Incorrect email or password.',
    });
  });

  it('falls back to the generic message for a 500, never surfacing backend internals', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse(500, { detail: 'Traceback (most recent call last): ...' })),
      ),
    );

    await expect(getMe('some-token')).rejects.toMatchObject({
      status: 500,
      message: 'Something went wrong. Please try again.',
    });
  });

  it('falls back to the generic message when the body is not valid JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response('<html>502 Bad Gateway</html>', {
            status: 502,
            headers: { 'Content-Type': 'text/html' },
          }),
        ),
      ),
    );

    await expect(getMe('some-token')).rejects.toMatchObject({
      status: 502,
      message: 'The AI service is temporarily unavailable. Please try again later.',
    });
  });

  it('falls back to the generic message when detail is not a string (FastAPI 422 validation errors)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(422, {
            detail: [{ loc: ['body', 'email'], msg: 'field required', type: 'value_error' }],
          }),
        ),
      ),
    );

    await expect(getMe('some-token')).rejects.toMatchObject({
      status: 422,
      message: 'The submitted data is invalid. Please check the form and try again.',
    });
  });
});
