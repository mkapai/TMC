/**
 * 统一服务导出
 * 提供集中的API服务入口
 */

// 核心API客户端
export { api, apiClient } from './api';

// API路由配置
export { API_ROUTES, buildApiUrl, isValidApiPath } from './api-config';

// 各模块API服务
export { settingsApi } from './settings';
export { rulesApi, keywordsApi, replaceRulesApi } from './rules';
export { chatsApi } from './chats';
export { clientsApi } from './clients';
export { systemApi } from './system';
export { dashboardApi } from './dashboard';
export { messagesApi } from './messages';
export { deliveryTargetsApi } from './deliveryTargets';

// 类型定义
export type * from './settings';
export type * from './rules';
export type * from './chats';
export type * from './clients';

/**
 * 统一的API服务对象
 * 便于使用和管理
 */
export const apiService = {
  settings: () => import('./settings').then(m => m.settingsApi),
  rules: () => import('./rules').then(m => m.rulesApi),
  chats: () => import('./chats').then(m => m.chatsApi),
  clients: () => import('./clients').then(m => m.clientsApi),
  system: () => import('./system').then(m => m.systemApi),
  dashboard: () => import('./dashboard').then(m => m.dashboardApi),
  messages: () => import('./messages').then(m => m.messagesApi),
  deliveryTargets: () => import('./deliveryTargets').then(m => m.deliveryTargetsApi),
};

export default apiService;
