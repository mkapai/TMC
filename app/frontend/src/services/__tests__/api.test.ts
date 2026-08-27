import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
}));
const state = vi.hoisted(() => ({ clientConfig: undefined as unknown }));

vi.mock('axios', () => ({
  default: {
    create: (config: unknown) => {
      state.clientConfig = config;
      return {
        ...mocks,
        defaults: { headers: { common: {} } },
        interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      };
    },
  },
}));

import { api, handleApiError } from '../api';

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
});
