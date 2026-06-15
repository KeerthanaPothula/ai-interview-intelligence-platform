import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import * as client from '../api/client';
import { POLL_INTERVAL_MS, useProcessingStatus } from './useProcessingStatus';

describe('useProcessingStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('polls every 3 seconds and stops once status is completed', async () => {
    const getProcessingStatusSpy = vi
      .spyOn(client, 'getProcessingStatus')
      .mockResolvedValueOnce({
        response_id: 'r-1',
        status: 'processing',
        transcript_id: null,
        analysis_id: null,
        error_message: null,
      })
      .mockResolvedValueOnce({
        response_id: 'r-1',
        status: 'completed',
        transcript_id: 't-1',
        analysis_id: 'a-1',
        error_message: null,
      });

    const { result } = renderHook(() => useProcessingStatus('r-1', 'uploaded', 'token-123'));

    expect(getProcessingStatusSpy).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(getProcessingStatusSpy).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('processing');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(getProcessingStatusSpy).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe('completed');
    expect(result.current.transcriptId).toBe('t-1');
    expect(result.current.analysisId).toBe('a-1');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(getProcessingStatusSpy).toHaveBeenCalledTimes(2);
  });

  it('does not poll when the initial status is already terminal', async () => {
    const getProcessingStatusSpy = vi.spyOn(client, 'getProcessingStatus');

    renderHook(() => useProcessingStatus('r-1', 'failed', 'token-123'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(getProcessingStatusSpy).not.toHaveBeenCalled();
  });

  it('sets pollError without changing status when a poll request fails', async () => {
    vi.spyOn(client, 'getProcessingStatus').mockRejectedValueOnce(new Error('network error'));

    const { result } = renderHook(() => useProcessingStatus('r-1', 'processing', 'token-123'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.pollError).toBe(true);
    expect(result.current.status).toBe('processing');
  });
});
