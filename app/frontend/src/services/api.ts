import axios, { type AxiosInstance, type AxiosResponse } from 'axios';
// import type { ApiResponse, PaginatedResponse } from '../types/api';

// 用于存储登出回调函数
let onUnauthorizedCallback: (() => void) | null = null;

// 【优化】用于防止重复触发 401 处理
let isHandling401 = false;

/**
 * 设置401未授权回调（由 AuthContext 调用）
 */
export const setUnauthorizedCallback = (callback: () => void) => {
  onUnauthorizedCallback = callback;
};

// 创建axios实例 - 简化版（参考v3.1）
const createApiClient = (): AxiosInstance => {
  // 默认使用同源地址；开发环境由 Vite 代理 /api 请求。
  const baseURL = import.meta.env.VITE_API_URL || '';
  
  const client = axios.create({
    baseURL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // 请求拦截器 - 简化版 + 认证token支持
  client.interceptors.request.use(
    (config) => {
      // 添加时间戳防止缓存
      if (config.method === 'get') {
        config.params = {
          ...config.params,
          _t: Date.now(),
        };
      }
      
      // 添加认证token
      const token = localStorage.getItem('access_token');
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      
      console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`, config.data);
      return config;
    },
    (error) => {
      console.error('[API] Request error:', error);
      return Promise.reject(error);
    }
  );

  // 响应拦截器 - 增强版，支持自动登出
  client.interceptors.response.use(
    (response: AxiosResponse) => {
      console.log(`[API] Response ${response.status}:`, response.data);
      return response;
    },
    (error) => {
      console.error('[API] Response error:', error.response?.data || error.message);
      
      // 处理特定HTTP状态码
      if (error.response?.status === 401) {
        // 【优化】防止重复处理（多个请求同时返回401时）
        if (!isHandling401) {
          isHandling401 = true;
          
          console.warn('⚠️ 登录状态已过期，即将跳转到登录页');
          
          // 清除本地token
          localStorage.removeItem('access_token');
          delete client.defaults.headers.common['Authorization'];
          
          // 调用登出回调（触发 AuthContext 清除状态并跳转）
          if (onUnauthorizedCallback) {
            onUnauthorizedCallback();
          } else {
            // 如果回调未设置，直接跳转到登录页（兜底）
            window.location.href = '/login';
          }
          
          // 【优化】延迟重置标志，避免短时间内的重复请求重复处理
          setTimeout(() => {
            isHandling401 = false;
          }, 1000);
        }
      } else if (error.response?.status === 403) {
        // 禁止访问
        console.error('访问被禁止');
      } else if (error.response?.status >= 500) {
        // 服务器错误
        console.error('服务器内部错误');
      }
      
      return Promise.reject(error);
    }
  );

  return client;
};

export const apiClient = createApiClient();

// 通用API响应处理函数
export const handleApiResponse = <T>(response: AxiosResponse<T>): T => {
  return response.data;
};

export const handleApiError = (error: unknown): never => {
  const apiError = error as { response?: { data?: { message?: string } }; message?: string };
  const message = apiError.response?.data?.message || apiError.message || '请求失败';
  throw new Error(message);
};

// 封装常用HTTP方法
export const api = {
  get: async <T>(url: string, params?: Record<string, unknown>): Promise<T> => {
    try {
      const response = await apiClient.get<T>(url, { params });
      return handleApiResponse(response);
    } catch (error) {
      return handleApiError(error);
    }
  },

  getBlob: async (url: string): Promise<Blob> => {
    try {
      const response = await apiClient.get<Blob>(url, { responseType: 'blob' });
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  post: async <T>(url: string, data?: unknown): Promise<T> => {
    try {
      const response = await apiClient.post<T>(url, data);
      return handleApiResponse(response);
    } catch (error) {
      return handleApiError(error);
    }
  },

  put: async <T>(url: string, data?: unknown): Promise<T> => {
    try {
      const response = await apiClient.put<T>(url, data);
      return handleApiResponse(response);
    } catch (error) {
      return handleApiError(error);
    }
  },

  patch: async <T>(url: string, data?: unknown): Promise<T> => {
    try {
      const response = await apiClient.patch<T>(url, data);
      return handleApiResponse(response);
    } catch (error) {
      return handleApiError(error);
    }
  },

  delete: async <T>(url: string): Promise<T> => {
    try {
      const response = await apiClient.delete<T>(url);
      return handleApiResponse(response);
    } catch (error) {
      return handleApiError(error);
    }
  },

  // 设置认证token
  setAuthToken: (token: string | null): void => {
    if (token) {
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete apiClient.defaults.headers.common['Authorization'];
    }
  },
};

export default api;
