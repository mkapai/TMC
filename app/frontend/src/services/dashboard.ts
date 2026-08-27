import { api } from './api';

export interface DashboardOverview {
  total_rules: number;
  active_rules: number;
  active_targets: number;
  pending_review: number;
  queued: number;
  sending: number;
  partially_sent: number;
  failed: number;
  today_sent: number;
  cache_bytes: number;
  cache_limit_bytes: number;
}

export const dashboardApi = {
  getOverview: async (): Promise<DashboardOverview> => {
    const response = await api.get<{ success: boolean; data: DashboardOverview }>('/api/dashboard/overview');
    return response.data;
  },
};
