import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  Layout,
  Menu,
  Button,
  Avatar,
  Space,
  Dropdown,
  message,
  Drawer,
  Grid,
} from 'antd';
import { useQuery } from '@tanstack/react-query';
import {
  DashboardOutlined,
  SettingOutlined,
  MessageOutlined,
  TeamOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  ContainerOutlined,
  LogoutOutlined,
  SafetyOutlined,
  MenuOutlined,
  SendOutlined,
} from '@ant-design/icons';
import ThemeSwitcher from './ThemeSwitcher';
import { useAuth } from '../../contexts/AuthContext';

const { Header, Sider } = Layout;
const { useBreakpoint } = Grid;

const menuItems: any[] = [
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: '仪表板',
    path: '/dashboard',
    title: '📊 仪表板',
    description: '消息审核与多目标投递概览',
    group: 'overview',
  },
  
  {
    key: 'divider-1',
    type: 'divider',
  },
  {
    key: 'message-management',
    icon: <MessageOutlined />,
    label: '消息管理',
    type: 'group',
    title: '💬 消息管理',
    children: [
      {
        key: '/chats',
        icon: <MessageOutlined />,
        label: '聊天列表',
        path: '/chats',
        title: '💬 聊天列表',
        description: '管理群组和频道信息',
      },
      {
        key: '/rules',
        icon: <SettingOutlined />,
        label: '转发规则',
        path: '/rules',
        title: '⚙️ 转发规则',
        description: '配置和管理消息转发规则',
      },
      {
        key: '/messages',
        icon: <MessageOutlined />,
        label: '消息队列',
        path: '/messages',
        title: '消息队列',
        description: '审核消息并查看每个目标的投递状态',
      },
      {
        key: '/delivery-targets',
        icon: <SendOutlined />,
        label: '发送目标',
        path: '/delivery-targets',
        title: '发送目标',
        description: '管理 Telegram 与 Webhook 目标',
      },
    ],
  },
  
  {
    key: 'divider-2',
    type: 'divider',
  },
  {
    key: 'system',
    icon: <SettingOutlined />,
    label: '系统',
    type: 'group',
    title: '⚙️ 系统',
    children: [
      {
        key: '/clients',
        icon: <TeamOutlined />,
        label: '客户端',
        path: '/clients',
        title: '🤖 客户端',
        description: '管理Telegram客户端实例',
      },
      {
        key: '/settings',
        icon: <SettingOutlined />,
        label: '设置',
        path: '/settings',
        title: '⚙️ 设置',
        description: '配置系统参数和Bot设置',
      },
    ],
  },
];

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const screens = useBreakpoint();
  
  // 响应式状态管理
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    // 从 localStorage 恢复状态
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved ? JSON.parse(saved) : false;
  });
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  
  // 监听屏幕尺寸变化
  useEffect(() => {
    const mobile = Boolean(screens.xs && !screens.md);
    setIsMobile(mobile);
    
    // 移动端自动关闭抽屉
    if (mobile) {
      setDrawerVisible(false);
    }
  }, [screens]);
  
  // 持久化侧边栏状态
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', JSON.stringify(sidebarCollapsed));
  }, [sidebarCollapsed]);

  // 获取系统信息
  const { data: systemInfo } = useQuery({
    queryKey: ['systemInfo'],
    queryFn: async () => {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/system/enhanced-status', {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (!response.ok) {
        throw new Error('Failed to fetch system info');
      }
      return response.json();
    },
    refetchInterval: 30000, // 每30秒刷新一次
  });

  // 处理登出
  const handleLogout = async () => {
    try {
      await logout();
      message.success('已登出');
      navigate('/login');
    } catch (error) {
      console.error('登出失败:', error);
    }
  };

  // 用户菜单
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
      onClick: () => navigate('/profile'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
      danger: true,
    },
  ];

  // 菜单点击处理 - 支持子菜单
  const handleMenuClick = (key: string) => {
    // 先在顶级菜单中查找
    let targetItem = menuItems.find(item => item.key === key && item.type !== 'divider' && item.type !== 'group');
    
    // 如果没找到，在子菜单中查找
    if (!targetItem) {
      for (const item of menuItems) {
        if (item.type === 'group' && item.children) {
          targetItem = item.children.find(child => child.key === key);
          if (targetItem) break;
        }
      }
    }
    
    if (targetItem && 'path' in targetItem && targetItem.path) {
      navigate(targetItem.path);
      // 移动端点击菜单后关闭抽屉
      if (isMobile) {
        setDrawerVisible(false);
      }
    }
  };

  // 获取当前选中的菜单 - 支持子菜单
  const getSelectedKeys = () => {
    const path = location.pathname;
    
    // 先在顶级菜单中查找
    for (const item of menuItems) {
      if (item.type !== 'divider' && item.type !== 'group' && 'path' in item && item.key && path.startsWith(item.key)) {
        return [item.key];
      }
    }
    
    // 在子菜单中查找
    for (const item of menuItems) {
      if (item.type === 'group' && item.children) {
        for (const child of item.children) {
          if (child.key && path.startsWith(child.key)) {
            return [child.key];
          }
        }
      }
    }
    
    return ['/dashboard'];
  };

  // 获取当前页面信息 - 支持子菜单
  const getCurrentPageInfo = () => {
    const path = location.pathname;
    
    // 先在顶级菜单中查找
    for (const item of menuItems) {
      if (item.type !== 'divider' && item.type !== 'group' && 'path' in item && item.key && path.startsWith(item.key)) {
        return { title: item.title || '', description: item.description || '' };
      }
    }
    
    // 在子菜单中查找
    for (const item of menuItems) {
      if (item.type === 'group' && item.children) {
        for (const child of item.children) {
          if (child.key && path.startsWith(child.key)) {
            return { title: child.title || '', description: child.description || '' };
          }
        }
      }
    }
    
    return { title: '仪表板', description: '消息审核与多目标投递概览' };
  };

  const currentPageInfo = getCurrentPageInfo();

  // 渲染菜单组件（侧边栏和抽屉共享）
  const renderMenu = () => (
    <Menu
      mode="inline"
      selectedKeys={getSelectedKeys()}
      style={{
        border: 'none',
        background: 'transparent',
        height: '100%',
      }}
      items={menuItems.map(item => {
        // 处理分隔线
        if (item.type === 'divider') {
          return {
            key: item.key,
            type: 'divider' as const,
            style: { margin: '8px 0' },
          };
        }
        
        // 处理分组（子菜单）
        if (item.type === 'group' && item.children) {
          return {
            key: item.key,
            icon: item.icon,
            label: item.label,
            type: 'group' as const,
            children: item.children.map(child => ({
              key: child.key,
              icon: child.icon,
              label: child.label,
              onClick: () => handleMenuClick(child.key),
            })),
          };
        }
        
        // 处理普通菜单项
        return {
          key: item.key,
          icon: item.icon,
          label: item.label,
          onClick: () => handleMenuClick(item.key),
        };
      })}
    />
  );

  return (
    <div className="main-layout-wrapper" style={{ height: '100vh', overflow: 'hidden' }}>
      {/* 移动端抽屉式侧边栏 */}
      {isMobile && (
        <Drawer
          placement="left"
          open={drawerVisible}
          onClose={() => setDrawerVisible(false)}
          width={240}
          styles={{
            body: { padding: 0 },
          }}
          closeIcon={null}
        >
          {/* Logo区域 */}
          <div
            style={{
              minHeight: 88,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '16px 24px',
              gap: 4,
              borderBottom: '1px solid rgba(0,0,0,0.06)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 'bold',
                  fontSize: 16,
                  color: '#ffffff',
                  boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
                }}
              >
                TMC
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                <span style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.2, color: '#fff' }}>
                  TMC
                </span>
                <span style={{ fontSize: 10, fontWeight: 400, lineHeight: 1.2, color: 'var(--color-text-secondary)', opacity: 0.85 }}>
                  Message Central
                </span>
              </div>
            </div>
            <div style={{ fontSize: 11, opacity: 0.9, textAlign: 'center', fontWeight: 500 }}>
              v{systemInfo?.version || '1.1.0'}
            </div>
          </div>
          
          {/* 菜单区域 */}
          <div style={{ height: 'calc(100% - 88px)', overflow: 'auto' }}>
            {renderMenu()}
          </div>
        </Drawer>
      )}

      {/* 桌面端/平板固定侧边栏 */}
      {!isMobile && (
        <Sider
          className="fixed-sidebar"
          trigger={null}
          collapsible
          collapsed={sidebarCollapsed}
          width={240}
          collapsedWidth={80}
          breakpoint="lg"
          style={{
            position: 'fixed',
            left: 0,
            top: 0,
            height: '100vh',
            maxHeight: '100vh', // 最大高度限制
            zIndex: 10,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden', // 防止整体溢出
          }}
        >
        {/* Logo区域 (TMC v1.1) */}
        <div
          className="sidebar-logo"
          style={{
            minHeight: sidebarCollapsed ? 64 : 88,
            flexShrink: 0, // 不允许缩小
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: sidebarCollapsed ? '16px 8px' : '16px 24px',
            gap: 4,
          }}
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: sidebarCollapsed ? 0 : 12,
          }}>
            {/* TMC Logo */}
            <div
              className="sidebar-logo-icon"
              style={{
                width: sidebarCollapsed ? 32 : 36,
                height: sidebarCollapsed ? 32 : 36,
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 'bold',
                fontSize: sidebarCollapsed ? 14 : 16,
                color: '#ffffff',
                boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
              }}
            >
              <span style={{ color: '#ffffff', fontWeight: 'bold' }}>TMC</span>
            </div>
            {!sidebarCollapsed && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                <span className="sidebar-logo-text" style={{ 
                  fontSize: 16, 
                  fontWeight: 700,
                  lineHeight: 1.2,
                  color: '#fff', // TMC保持白色
                }}>
                  TMC
                </span>
                <span className="sidebar-logo-subtitle" style={{ 
                  fontSize: 10, 
                  fontWeight: 400,
                  lineHeight: 1.2,
                  // Message Central根据主题调整颜色
                  color: 'var(--color-text-secondary)',
                  opacity: 0.85,
                }}>
                  Message Central
                </span>
              </div>
            )}
          </div>
          
          <div className="sidebar-version" style={{ 
            fontSize: sidebarCollapsed ? 10 : 11, 
            opacity: 0.9, 
            textAlign: 'center',
            fontWeight: 500,
          }}>
            v{systemInfo?.version || '1.1.0'}
          </div>
        </div>

        {/* 菜单区域 - 占用剩余空间并可滚动 */}
        <div style={{ 
          flex: 1, 
          overflow: 'auto',
          minHeight: 0, // 允许flex子元素缩小
        }}>
          {renderMenu()}
        </div>

        {/* 折叠/展开按钮 - 固定在底部 */}
        <div
          className="sidebar-footer"
          style={{
            flexShrink: 0, // 不允许缩小
            padding: '16px',
            display: 'flex',
            justifyContent: 'center',
            borderTop: '1px solid rgba(0,0,0,0.06)',
          }}
        >
          <Button
            className="sidebar-collapse-btn"
            type="text"
            icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            style={{
              fontSize: 16,
              width: 40,
              height: 40,
              borderRadius: '8px',
              transition: 'all 0.3s ease',
            }}
          />
        </div>
        </Sider>
      )}

      {/* 右侧主区域：header + content */}
      <div
        style={{
          marginLeft: isMobile ? 0 : (sidebarCollapsed ? 80 : 240),
          width: isMobile ? '100vw' : `calc(100vw - ${sidebarCollapsed ? 80 : 240}px)`,
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          transition: 'margin-left 0.3s ease, width 0.3s ease',
        }}
      >
        {/* 顶部导航栏 - 不再fixed，在正常文档流中 */}
        <Header 
          className="layout-header"
          style={{
            height: 64,
            flexShrink: 0,
            zIndex: 11,
            padding: 0,
          }}
        >
          <div className="header-content" style={{ padding: isMobile ? '0 16px' : '0 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {/* 左侧：移动端汉堡菜单 + 页面信息 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 8 : 16, flex: 1, maxWidth: 'calc(100% - 200px)' }}>
              {/* 移动端汉堡菜单按钮 */}
              {isMobile && (
                <Button
                  type="text"
                  icon={<MenuOutlined />}
                  onClick={() => setDrawerVisible(true)}
                  style={{
                    fontSize: 18,
                    flexShrink: 0,
                  }}
                />
              )}
              
              {/* 页面信息 */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="header-title" style={{ 
                  fontSize: isMobile ? 16 : 20, 
                  fontWeight: 600,
                  display: 'block',
                  lineHeight: 1.2,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {currentPageInfo.title}
                </div>
                {!isMobile && (
                  <div className="header-description" style={{ 
                    fontSize: 13, 
                    opacity: 0.85, 
                    marginTop: 2,
                    lineHeight: 1.3,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {currentPageInfo.description}
                  </div>
                )}
              </div>
            </div>

            {/* 右侧：容器日志、主题切换器和用户信息 */}
            <Space align="center" size={isMobile ? 8 : 16}>
              {/* 容器日志按钮 - 移动端只显示图标 */}
              {!isMobile ? (
                <Button
                  type="text"
                  icon={<ContainerOutlined />}
                  onClick={() => navigate('/container-logs')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span>容器日志</span>
                </Button>
              ) : (
                <Button
                  type="text"
                  icon={<ContainerOutlined />}
                  onClick={() => navigate('/container-logs')}
                  style={{ fontSize: 18 }}
                />
              )}
              
              <ThemeSwitcher />
              
              {/* 用户信息下拉菜单 - 移动端简化显示 */}
              <Dropdown 
                menu={{ items: userMenuItems }}
                placement="bottomRight"
                trigger={['click']}
              >
                {isMobile ? (
                  <Avatar
                    size={32}
                    src={user?.avatar}
                    icon={<UserOutlined />}
                    style={{ 
                      cursor: 'pointer',
                      fontSize: 14,
                      backgroundColor: user?.is_admin ? '#f56a00' : '#1890ff',
                    }}
                  />
                ) : (
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 12, 
                    cursor: 'pointer',
                    padding: '4px 12px',
                    borderRadius: '8px',
                    transition: 'background 0.3s ease',
                  }}
                  className="user-info-dropdown">
                    <Avatar
                      size={36}
                      src={user?.avatar}
                      icon={<UserOutlined />}
                      style={{ 
                        fontSize: 16,
                        backgroundColor: user?.is_admin ? '#f56a00' : '#1890ff',
                      }}
                    />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontSize: 14, fontWeight: 500, lineHeight: 1.2 }}>
                        {user?.username || '用户'}
                      </span>
                      {user?.is_admin && (
                        <span style={{ 
                          fontSize: 11, 
                          opacity: 0.7, 
                          lineHeight: 1,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                        }}>
                          <SafetyOutlined style={{ fontSize: 10 }} />
                          管理员
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </Dropdown>
            </Space>
          </div>
        </Header>

        {/* 主内容区域 - 允许页面级滚动 */}
        <div
          className="main-content-area"
          style={{
            flex: 1,
            overflow: 'auto', // 🎯 允许页面级滚动
            padding: isMobile ? '16px' : '24px',
            background: 'transparent',
          }}
        >
          <div className="fade-in">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
};

export default MainLayout;
