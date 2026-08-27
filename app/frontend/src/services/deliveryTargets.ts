import { api } from './api';
import type { DeliveryTarget, DeliveryTargetInput } from '../types/delivery';

const base = '/api/delivery-targets';

export const deliveryTargetsApi = {
  list: async (): Promise<DeliveryTarget[]> => {
    const response = await api.get<{ success: boolean; targets: DeliveryTarget[] }>(base);
    return response.targets;
  },
  create: async (input: DeliveryTargetInput): Promise<DeliveryTarget> => {
    const response = await api.post<{ success: boolean; target: DeliveryTarget }>(base, input);
    return response.target;
  },
  update: async (id: number, input: DeliveryTargetInput): Promise<DeliveryTarget> => {
    const response = await api.put<{ success: boolean; target: DeliveryTarget }>(`${base}/${id}`, input);
    return response.target;
  },
  setActive: (id: number, is_active: boolean) =>
    api.patch<{ success: boolean }>(`${base}/${id}/status`, { is_active }),
  remove: (id: number) => api.delete<{ success: boolean }>(`${base}/${id}`),
  test: (id: number) => api.post<{ success: boolean; message: string }>(`${base}/${id}/test`),
};
