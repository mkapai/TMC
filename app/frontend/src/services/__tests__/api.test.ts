import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
}));
const state = vi.hoisted(() => ({
  clientConfig: undefined as unknown,
  responseErrorHandler: undefined as undefined | ((error: unknown) => Promise<never>),
}));

vi.mock('axios', () => ({
  default: {
    create: (config: unknown) => {
      state.clientConfig = config;
      return {
        ...mocks,
        defaults: { headers: { common: {} } },
        interceptors: {
          request: { use: vi.fn() },
          response: {
            use: (_success: unknown, onError: (error: unknown) => Promise<never>) => {
              state.responseErrorHandler = onError;
            },
          },
        },
      };
    },
  },
}));

import { api, handleApiError, setUnauthorizedCallback } from '../api';

describe('API Service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses same-origin requests without cookie credentials by default', () => {
    expect(state.clientConfig).toEqual(expect.objectContaining({ baseURL: '' }));
    expect(state.clientConfig).not.toHaveProperty('withCredentials');
  });

  it('returns GET response data', async () => {
    mocks.get.mockResolvedValue({ data: { id: 1 } });
    await expect(api.get('/test')).resolves.toEqual({ id: 1 });
    expect(mocks.get).toHaveBeenCalledWith('/test', { params: undefined });
  });

  it('sends POST request data', async () => {
    mocks.post.mockResolvedValue({ data: { success: true } });
    await expect(api.post('/test', { name: 'value' })).resolves.toEqual({ success: true });
    expect(mocks.post).toHaveBeenCalledWith('/test', { name: 'value' });
  });

  it('uses API and generic error messages', () => {
    expect(() => handleApiError({ response: { data: { message: 'API error' } } })).toThrow('API error');
    expect(() => handleApiError(new Error('Unknown error'))).toThrow('Unknown error');
  });

  it('shows the server IP ban message on login', async () => {
    const detail = '登录失败次数过多，IP 已临时封禁，请在 900 秒后重试';
    mocks.post.mockRejectedValue({ response: { status: 429, data: { detail } } });
    await expect(api.post('/api/auth/login', {})).rejects.toThrow(detail);
  });

  it('does not treat incorrect login credentials as an expired session', async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedCallback(onUnauthorized);
    localStorage.setItem('access_token', 'existing-token');
    const error = { response: { status: 401 }, config: { url: '/api/auth/login' } };
    try {
      await expect(state.responseErrorHandler!(error)).rejects.toBe(error);
      expect(onUnauthorized).not.toHaveBeenCalled();
      expect(localStorage.getItem('access_token')).toBe('existing-token');
    } finally {
      localStorage.removeItem('access_token');
    }
  });

  it('still clears expired sessions for protected endpoints', async () => {
    vi.useFakeTimers();
    const onUnauthorized = vi.fn();
    setUnauthorizedCallback(onUnauthorized);
    localStorage.setItem('access_token', 'expired-token');
    const error = { response: { status: 401 }, config: { url: '/api/auth/me' } };
    try {
      await expect(state.responseErrorHandler!(error)).rejects.toBe(error);
      expect(onUnauthorized).toHaveBeenCalledOnce();
      expect(localStorage.getItem('access_token')).toBeNull();
    } finally {
      vi.runAllTimers();
      vi.useRealTimers();
    }
  });
});
