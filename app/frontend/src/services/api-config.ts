export const API_VERSION = { V1: 'v1', CURRENT: 'v1' } as const;
export const API_BASE = '/api';

export function getVersionedApiBase(version: string = API_VERSION.CURRENT): string {
  return `${API_BASE}/${version}`;
}

export const API_ROUTES = {
  system: {
    base: `${API_BASE}/system`,
    status: `${API_BASE}/system/status`,
    enhancedStatus: `${API_BASE}/system/enhanced-status`,
    containerLogs: `${API_BASE}/system/container-logs/stream`,
    logs: `${API_BASE}/system/logs`,
    stats: `${API_BASE}/stats`,
    telegram: {
      status: `${API_BASE}/telegram/status`, restart: `${API_BASE}/telegram/restart`,
      testCredentials: `${API_BASE}/telegram/test-credentials`, login: `${API_BASE}/telegram/login`,
      submitPassword: `${API_BASE}/telegram/submit-password`,
    },
    config: {
      current: `${API_BASE}/config/current`, forceReload: `${API_BASE}/config/force-reload`,
      syncStatus: `${API_BASE}/config/sync-status`,
    },
  },
  rules: {
    base: `${API_BASE}/rules`, list: `${API_BASE}/rules`, create: `${API_BASE}/rules`,
    get: (id: number) => `${API_BASE}/rules/${id}`,
    update: (id: number) => `${API_BASE}/rules/${id}`,
    delete: (id: number) => `${API_BASE}/rules/${id}`,
  },
  chats: {
    base: `${API_BASE}/chats`, list: `${API_BASE}/chats`, refresh: `${API_BASE}/chats/refresh`,
    export: `${API_BASE}/chats/export`, import: `${API_BASE}/chats/import`,
  },
  clients: { base: `${API_BASE}/clients`, list: `${API_BASE}/clients`, create: `${API_BASE}/clients` },
  settings: {
    base: `${API_BASE}/settings`, get: `${API_BASE}/settings`, save: `${API_BASE}/settings`,
    testProxy: `${API_BASE}/settings/test-proxy`,
    telegram: {
      login: `${API_BASE}/telegram/login`, logout: `${API_BASE}/telegram/logout`,
      status: `${API_BASE}/telegram/status`, testCredentials: `${API_BASE}/telegram/test-credentials`,
      restartClient: `${API_BASE}/telegram/restart-client`, restart: `${API_BASE}/telegram/restart`,
    },
    config: { forceReload: `${API_BASE}/config/force-reload`, syncStatus: `${API_BASE}/config/sync-status` },
    logs: { testCleanup: `${API_BASE}/test-log-cleanup` },
  },
  dashboard: { base: `${API_BASE}/dashboard`, overview: `${API_BASE}/dashboard/overview` },
  messages: { base: `${API_BASE}/messages`, stats: `${API_BASE}/messages/stats` },
  deliveryTargets: { base: `${API_BASE}/delivery-targets` },
  health: '/health',
} as const;

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export interface ApiEndpoint { method: HttpMethod; path: string; description?: string }

export const API_ENDPOINTS: Record<string, Record<string, ApiEndpoint>> = {
  system: { status: { method: 'GET', path: API_ROUTES.system.status } },
  rules: { list: { method: 'GET', path: API_ROUTES.rules.list }, create: { method: 'POST', path: API_ROUTES.rules.create } },
  settings: { get: { method: 'GET', path: API_ROUTES.settings.get }, save: { method: 'POST', path: API_ROUTES.settings.save } },
};

export function buildApiUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL || '';
  return `${base}${path}`;
}

export function isValidApiPath(path: string): boolean {
  const check = (value: unknown): boolean => {
    if (typeof value === 'string') return value === path;
    if (value && typeof value === 'object') return Object.values(value).some(check);
    return false;
  };
  return check(API_ROUTES);
}

export default API_ROUTES;
