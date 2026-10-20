import { api } from './api';
import type { QueuedMessage, QueueStats } from '../types/delivery';

export interface MessageFilters {
  status?: string;
  rule_id?: number;
  source_chat_id?: string;
  message_type?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
}

export interface MessageResourceEdit {
  text: string;
  target_ids: number[];
  remove_resource_ids: number[];
  files: File[];
  push: boolean;
}

const base = '/api/messages';

export const messagesApi = {
  list: (filters: MessageFilters) => api.get<{
    success: boolean;
    messages: QueuedMessage[];
    pagination: { page: number; page_size: number; total: number };
  }>(base, filters as Record<string, unknown>),
  stats: async (): Promise<QueueStats> => {
    const response = await api.get<{ success: boolean; stats: QueueStats }>(`${base}/stats`);
    return response.stats;
  },
  get: async (id: number): Promise<QueuedMessage> => {
    const response = await api.get<{ success: boolean; message: QueuedMessage }>(`${base}/${id}`);
    return response.message;
  },
  update: (id: number, text: string, target_ids: number[], push = false) =>
    api.patch<{ success: boolean }>(`${base}/${id}`, { text, target_ids, push }),
  edit: (id: number, input: MessageResourceEdit) => {
    const data = new FormData();
    data.append('text', input.text);
    data.append('target_ids', JSON.stringify(input.target_ids));
    data.append('remove_resource_ids', JSON.stringify(input.remove_resource_ids));
    data.append('push', String(input.push));
    input.files.forEach(file => data.append('files', file, file.name));
    return api.postForm<{ success: boolean }>(`${base}/${id}/edit`, data);
  },
  preview: (previewUrl: string) => api.getBlob(previewUrl),
  approve: (id: number, target_ids?: number[]) =>
    api.post<{ success: boolean }>(`${base}/${id}/approve`, { target_ids }),
  reject: (id: number) => api.post<{ success: boolean }>(`${base}/${id}/reject`),
  retry: (id: number) => api.post<{ success: boolean; retried: number }>(`${base}/${id}/retry`),
  remove: (id: number) => api.delete<{ success: boolean }>(`${base}/${id}`),
  bulk: (message_ids: number[], action: 'approve' | 'reject' | 'retry' | 'delete') =>
    api.post<{ success: boolean; succeeded: number[]; failed: Array<{ id: number; error: string }> }>(
      `${base}/bulk/action`, { message_ids, action },
    ),
};
