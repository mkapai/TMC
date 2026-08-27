import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Layout
import MainLayout from './components/common/MainLayout';

// Theme
import { ThemeProvider, useThemeContext } from './theme';

// Context
import { AuthProvider } from './contexts/AuthContext';

// Components
import PrivateRoute from './components/common/PrivateRoute';

// Pages
import Dashboard from './pages/Dashboard/IntegratedDashboard';
import RulesPage from './pages/Rules/index';
import SettingsPage from './pages/Settings/index';
import ChatsPage from './pages/Chats/index';
import ClientManagement from './pages/ClientManagement/index';
import UserManagement from './pages/UserManagement/index';
import LoginPage from './pages/Login/index';
import ContainerLogs from './pages/ContainerLogs/index';
import ProfilePage from './pages/Profile/index';
import MessageQueuePage from './pages/MessageQueue/index';
import DeliveryTargetsPage from './pages/DeliveryTargets/index';

// Styles
import './styles/index.css';

// 创建React Query客户端 - 修复缓存同步
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 0, // 立即过期，确保数据新鲜
      gcTime: 5 * 60 * 1000, // 5分钟垃圾回收
      refetchOnMount: true, // 组件挂载时总是重新获取
      refetchOnWindowFocus: true, // 窗口聚焦时重新获取
      refetchOnReconnect: true, // 网络重连时重新获取
    },
    mutations: {
      retry: 1,
    },
  },
});

// 内部App组件 - 使用主题
const AppContent: React.FC = () => {
  const { themeType, colors } = useThemeContext();
  
  // Ant Design主题配置
  const antdTheme = React.useMemo(() => ({
    algorithm: themeType === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: colors.primary,
      borderRadius: 6,
      ...(themeType === 'dark' ? {
        colorBgContainer: colors.bgContainer,
        colorBgElevated: colors.bgElevated,
        colorBgLayout: colors.bgLayout,
        colorBorder: colors.borderBase,
        colorText: colors.textPrimary,
        colorTextSecondary: colors.textSecondary,
      } : {}),
    },
  }), [themeType, colors]);

  return (
    <ConfigProvider 
      locale={zhCN}
      theme={antdTheme}
    >
      <AntApp>
        <AuthProvider>
          <Router>
            <Routes>
              {/* 登录页面 - 公开访问 */}
              <Route path="/login" element={<LoginPage />} />
              
              {/* 主应用路由 - 需要认证 */}
              <Route path="/" element={
                <PrivateRoute>
                  <MainLayout />
                </PrivateRoute>
              }>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="rules/*" element={<RulesPage />} />
                <Route path="messages" element={<MessageQueuePage />} />
                <Route path="delivery-targets" element={<DeliveryTargetsPage />} />
                <Route path="chats" element={<ChatsPage />} />
                <Route path="clients" element={<ClientManagement />} />
                <Route path="users" element={<UserManagement />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="container-logs" element={<ContainerLogs />} />
                <Route path="profile" element={<ProfilePage />} />
              </Route>
              
              {/* 404重定向 */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Router>
        </AuthProvider>
      </AntApp>
    </ConfigProvider>
  );
};

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AppContent />
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
