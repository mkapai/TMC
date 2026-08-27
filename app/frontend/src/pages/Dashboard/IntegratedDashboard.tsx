import React from 'react';
import { Button, Col, Progress, Row, Space, Statistic, Typography } from 'antd';
import { ArrowRightOutlined, CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, SendOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { dashboardApi } from '../../services/dashboard';

const { Title, Text } = Typography;

const IntegratedDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: dashboardApi.getOverview,
    refetchInterval: 10000,
  });
  const cachePercent = data?.cache_limit_bytes
    ? Math.min(100, data.cache_bytes / data.cache_limit_bytes * 100)
    : 0;
  const statStyle: React.CSSProperties = {
    padding: 18, border: '1px solid var(--color-border-base)', borderRadius: 6,
    background: 'var(--color-bg-container)', minHeight: 112,
  };

  return <div style={{ padding: 24 }}>
    <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 20 }}>
      <div><Title level={2} style={{ margin: 0 }}>投递概览</Title><Text type="secondary">实时消息队列与目标投递状态</Text></div>
      <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate('/messages')}>查看消息队列</Button>
    </Space>
    <Row gutter={[16, 16]}>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="待审核" value={data?.pending_review || 0} prefix={<ClockCircleOutlined />} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="待发送" value={data?.queued || 0} prefix={<SendOutlined />} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="发送中" value={data?.sending || 0} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="部分成功" value={data?.partially_sent || 0} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="失败" value={data?.failed || 0} prefix={<ExclamationCircleOutlined />} valueStyle={{ color: data?.failed ? '#cf1322' : undefined }} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="今日成功" value={data?.today_sent || 0} prefix={<CheckCircleOutlined />} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="启用规则" value={data?.active_rules || 0} suffix={`/ ${data?.total_rules || 0}`} /></div></Col>
      <Col xs={12} md={6}><div style={statStyle}><Statistic loading={isLoading} title="启用目标" value={data?.active_targets || 0} /></div></Col>
    </Row>
    <div style={{ marginTop: 24, maxWidth: 620 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }}><Text strong>消息附件缓存</Text><Text type="secondary">{((data?.cache_bytes || 0) / 1024 ** 3).toFixed(2)} / {((data?.cache_limit_bytes || 0) / 1024 ** 3).toFixed(0)} GB</Text></Space>
      <Progress percent={Number(cachePercent.toFixed(1))} status={cachePercent >= 90 ? 'exception' : 'normal'} />
    </div>
  </div>;
};

export default IntegratedDashboard;
