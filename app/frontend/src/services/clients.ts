import { api } from './api';
import type { ClientsResponse } from '../types/rule';

export const clientsApi = {
  // 获取所有客户端
  getClients: async (): Promise<ClientsResponse> => {
    const response = await api.get<ClientsResponse>('/api/clients');
    return response;
  },

  // 启动客户端
  startClient: async (clientId: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post<{ success: boolean; message: string }>(`/api/clients/${encodeURIComponent(clientId)}/start`);
    return response;
  },

  // 停止客户端
  stopClient: async (clientId: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post<{ success: boolean; message: string }>(`/api/clients/${encodeURIComponent(clientId)}/stop`);
    return response;
  },

  // 添加客户端
  addClient: async (data: { 
    client_id: string; 
    client_type: 'user' | 'bot';
    // 机器人客户端字段
    bot_token?: string;
    admin_user_id?: string;
    // 用户客户端字段
    api_id?: string;
    api_hash?: string;
    phone?: string;
  }): Promise<{ 
    success: boolean; 
    message: string;
    need_verification?: boolean;
    client_id?: string;
  }> => {
    const response = await api.post<{ 
      success: boolean; 
      message: string;
      need_verification?: boolean;
      client_id?: string;
    }>('/api/clients', data);
    return response;
  },

  // 删除客户端
  removeClient: async (clientId: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.delete<{ success: boolean; message: string }>(`/api/clients/${encodeURIComponent(clientId)}`);
    return response;
  },

  // 获取增强版系统状态
  getEnhancedStatus: async (): Promise<{
    success: boolean;
    enhanced_mode: boolean;
    clients?: Record<string, unknown>;
    total_clients?: number;
    running_clients?: number;
    connected_clients?: number;
    message?: string;
  }> => {
    const response = await api.get<{
      success: boolean;
      enhanced_mode: boolean;
      clients?: Record<string, unknown>;
      total_clients?: number;
      running_clients?: number;
      connected_clients?: number;
      message?: string;
    }>('/api/system/enhanced-status');
    return response;
  },

  // 客户端登录流程
  clientLogin: async (clientId: string, loginData: {
    step: 'send_code' | 'submit_code' | 'submit_password';
    code?: string;
    password?: string;
  }): Promise<{
    success: boolean;
    message: string;
    step?: 'waiting_code' | 'waiting_password' | 'completed';
    user_info?: Record<string, unknown>;
    cooldown_seconds?: number;
    auto_started?: boolean;
    error_type?: string;
    remaining_seconds?: number;
  }> => {
    const response = await api.post<{
      success: boolean;
      message: string;
      step?: 'waiting_code' | 'waiting_password' | 'completed';
      user_info?: Record<string, unknown>;
      cooldown_seconds?: number;
      auto_started?: boolean;
      error_type?: string;
      remaining_seconds?: number;
    }>(`/api/clients/${encodeURIComponent(clientId)}/login`, loginData);
    return response;
  },

  // 切换自动启动
  toggleAutoStart: async (clientId: string, autoStart: boolean): Promise<{ success: boolean; message: string }> => {
    const response = await api.post<{ success: boolean; message: string }>(`/api/clients/${encodeURIComponent(clientId)}/auto-start`, {
      auto_start: autoStart
    });
    return response;
  },
};
