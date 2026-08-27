import React, { useEffect, useState } from 'react';
import {
  Alert, Button, DatePicker, Descriptions, Drawer, Form, Image, Input, Modal, Select, Space,
  Table, Tag, Typography, message as notice,
} from 'antd';
import { CheckOutlined, DeleteOutlined, EditOutlined, ReloadOutlined, SendOutlined, StopOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';

import { deliveryTargetsApi } from '../../services/deliveryTargets';
import { messagesApi, type MessageFilters } from '../../services/messages';
import type { MessageResource, QueuedMessage, QueueMessageStatus } from '../../types/delivery';
import { isMessageEditable, mediaPreviewKind, messageTargetOptions } from './helpers';

const { Title, Text, Paragraph, Link } = Typography;

const statusLabels: Record<QueueMessageStatus, { text: string; color: string }> = {
  ingesting: { text: '摄取中', color: 'processing' },
  ingest_failed: { text: '摄取失败', color: 'error' },
  pending_review: { text: '待审核', color: 'gold' },
  queued: { text: '待发送', color: 'blue' },
  sending: { text: '发送中', color: 'processing' },
  partially_sent: { text: '部分成功', color: 'orange' },
  sent: { text: '已发送', color: 'success' },
  failed: { text: '失败', color: 'error' },
  rejected: { text: '已拒绝', color: 'default' },
};

const MediaPreview: React.FC<{ resource: MessageResource }> = ({ resource }) => {
  const kind = mediaPreviewKind(resource);
  const previewQuery = useQuery({
    queryKey: ['message-resource-preview', resource.id],
    queryFn: () => messagesApi.preview(resource.preview_url),
    enabled: Boolean(kind),
    staleTime: Infinity,
  });
  const [objectUrl, setObjectUrl] = useState<string>();

  useEffect(() => {
    if (!previewQuery.data) return undefined;
    const url = URL.createObjectURL(previewQuery.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [previewQuery.data]);

  return (
    <div style={{ marginBottom: 16 }}>
      {kind && (
        <div style={{ width: '100%', aspectRatio: '16 / 9', maxHeight: 380, display: 'grid', placeItems: 'center', overflow: 'hidden', background: '#000' }}>
          {previewQuery.isLoading && <Text style={{ color: '#fff' }}>加载预览...</Text>}
          {previewQuery.isError && <Alert type="error" showIcon message="媒体预览加载失败" />}
          {kind === 'image' && objectUrl && (
            <Image src={objectUrl} alt={resource.name} style={{ maxWidth: '100%', maxHeight: 380, objectFit: 'contain' }} />
          )}
          {kind === 'video' && objectUrl && (
            <video src={objectUrl} controls preload="metadata" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
          )}
        </div>
      )}
      <div style={{ marginTop: kind ? 8 : 0 }}>
        <Link href={resource.url} target="_blank" rel="noreferrer">{resource.name}</Link>{' '}
        <Text type="secondary">{(resource.size / 1024 / 1024).toFixed(2)} MB</Text>
      </div>
    </div>
  );
};

const MessageQueuePage: React.FC = () => {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<MessageFilters>({ page: 1, page_size: 20 });
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [detailId, setDetailId] = useState<number>();
  const [editing, setEditing] = useState(false);
  const [form] = Form.useForm();

  const listQuery = useQuery({ queryKey: ['messages', filters], queryFn: () => messagesApi.list(filters) });
  const targetsQuery = useQuery({ queryKey: ['delivery-targets'], queryFn: deliveryTargetsApi.list });
  const detailQuery = useQuery({
    queryKey: ['message', detailId],
    queryFn: () => messagesApi.get(detailId!),
    enabled: Boolean(detailId),
  });

  useEffect(() => {
    if (detailQuery.data) {
      form.setFieldsValue({
        text: detailQuery.data.processed_text || '',
        target_ids: detailQuery.data.selected_target_ids,
      });
    }
  }, [detailQuery.data, form]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['messages'] });
    queryClient.invalidateQueries({ queryKey: ['message', detailId] });
    queryClient.invalidateQueries({ queryKey: ['queue-stats'] });
  };
  const openMessage = (id: number, edit = false) => {
    setEditing(edit);
    setDetailId(id);
  };
  const action = useMutation({
    mutationFn: async ({ id, kind }: { id: number; kind: 'approve' | 'reject' | 'retry' | 'delete' }) => {
      if (kind === 'approve') return messagesApi.approve(id);
      if (kind === 'reject') return messagesApi.reject(id);
      if (kind === 'retry') return messagesApi.retry(id);
      return messagesApi.remove(id);
    },
    onSuccess: () => { notice.success('操作成功'); refresh(); },
    onError: (error: Error) => notice.error(error.message),
  });
  const save = useMutation({
    mutationFn: async ({ values, push }: { values: { text: string; target_ids: number[] }; push: boolean }) => {
      await messagesApi.update(detailId!, values.text, values.target_ids, push);
    },
    onSuccess: (_, variables) => {
      notice.success(variables.push ? '消息已更新并加入发送队列' : '消息已更新');
      setEditing(false);
      refresh();
    },
    onError: (error: Error) => notice.error(error.message),
  });
  const submitEdit = async (push: boolean) => {
    try {
      const values = await form.validateFields();
      save.mutate({ values, push });
    } catch {
      // Form.Item renders field-level validation feedback.
    }
  };
  const bulk = useMutation({
    mutationFn: (kind: 'approve' | 'reject' | 'retry' | 'delete') =>
      messagesApi.bulk(selected.map(Number), kind),
    onSuccess: result => {
      if (result.failed.length) notice.warning(`${result.succeeded.length} 条成功，${result.failed.length} 条失败`);
      else notice.success(`已处理 ${result.succeeded.length} 条消息`);
      setSelected([]);
      refresh();
    },
    onError: (error: Error) => notice.error(error.message),
  });

  const confirmDelete = (id: number) => Modal.confirm({
    title: '删除消息及缓存资源？',
    content: '投递记录和附件文件会一并删除，所有公开资源链接将立即失效。',
    okText: '删除', okButtonProps: { danger: true }, cancelText: '取消',
    onOk: () => action.mutateAsync({ id, kind: 'delete' }),
  });

  const columns = [
    { title: '状态', dataIndex: 'status', width: 100, render: (value: QueueMessageStatus) => <Tag color={statusLabels[value]?.color}>{statusLabels[value]?.text || value}</Tag> },
    { title: '规则', dataIndex: 'rule_name', width: 150 },
    { title: '来源', width: 190, render: (_: unknown, row: QueuedMessage) => <div>{row.source_chat_name || row.source_chat_id}<br /><Text type="secondary">#{row.source_message_id}</Text></div> },
    { title: '类型', dataIndex: 'message_type', width: 90 },
    { title: '最终文本', dataIndex: 'processed_text', ellipsis: true },
    { title: '资源', dataIndex: 'resources', width: 70, render: (value: QueuedMessage['resources']) => value.length },
    { title: '时间', dataIndex: 'created_at', width: 170, render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
    {
      title: '操作', width: 330, fixed: 'right' as const,
      render: (_: unknown, row: QueuedMessage) => (
        <Space size="small">
          <Button size="small" onClick={() => openMessage(row.id)}>详情</Button>
          {isMessageEditable(row) && <Button size="small" icon={<EditOutlined />} onClick={() => openMessage(row.id, true)}>编辑</Button>}
          {row.status === 'pending_review' && <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => action.mutate({ id: row.id, kind: 'approve' })}>批准</Button>}
          {row.status === 'pending_review' && <Button size="small" icon={<StopOutlined />} onClick={() => action.mutate({ id: row.id, kind: 'reject' })}>拒绝</Button>}
          {['failed', 'partially_sent', 'ingest_failed'].includes(row.status) && <Button size="small" icon={<ReloadOutlined />} onClick={() => action.mutate({ id: row.id, kind: 'retry' })}>重试</Button>}
          {row.status !== 'sending' && <Button size="small" danger icon={<DeleteOutlined />} onClick={() => confirmDelete(row.id)} />}
        </Space>
      ),
    },
  ];

  const detail = detailQuery.data;
  const editable = isMessageEditable(detail);

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={2} style={{ margin: 0 }}>消息队列</Title>
        <Button icon={<ReloadOutlined />} onClick={() => refresh()}>刷新</Button>
      </Space>
      <Form layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item><Input.Search allowClear placeholder="关键词、来源或发送者" onSearch={search => setFilters(value => ({ ...value, search, page: 1 }))} /></Form.Item>
        <Form.Item><Select allowClear placeholder="状态" style={{ width: 130 }} onChange={status => setFilters(value => ({ ...value, status, page: 1 }))} options={Object.entries(statusLabels).map(([value, item]) => ({ value, label: item.text }))} /></Form.Item>
        <Form.Item><Select allowClear placeholder="消息类型" style={{ width: 130 }} onChange={message_type => setFilters(value => ({ ...value, message_type, page: 1 }))} options={['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation', 'webpage'].map(value => ({ value, label: value }))} /></Form.Item>
        <Form.Item><DatePicker.RangePicker onChange={dates => setFilters(value => ({ ...value, page: 1, start_date: dates?.[0]?.startOf('day').toISOString(), end_date: dates?.[1]?.endOf('day').toISOString() }))} /></Form.Item>
      </Form>
      {selected.length > 0 && <Space style={{ marginBottom: 12 }}>
        <Text>已选择 {selected.length} 条</Text>
        <Button onClick={() => bulk.mutate('approve')}>批量批准</Button>
        <Button onClick={() => bulk.mutate('reject')}>批量拒绝</Button>
        <Button onClick={() => bulk.mutate('retry')}>批量重试</Button>
        <Button danger onClick={() => Modal.confirm({ title: '批量删除消息？', content: '缓存资源和公开链接也会被删除。', okButtonProps: { danger: true }, onOk: () => bulk.mutateAsync('delete') })}>批量删除</Button>
      </Space>}
      <Table rowKey="id" loading={listQuery.isLoading} dataSource={listQuery.data?.messages || []} columns={columns} scroll={{ x: 1200 }} rowSelection={{ selectedRowKeys: selected, onChange: setSelected }} pagination={{ current: filters.page, pageSize: filters.page_size, total: listQuery.data?.pagination.total, showSizeChanger: true, onChange: (page, page_size) => setFilters(value => ({ ...value, page, page_size })) }} />

      <Drawer title={detail ? `消息 #${detail.id}` : '消息详情'} open={Boolean(detailId)} width={720} onClose={() => { setDetailId(undefined); setEditing(false); }} extra={editable && <Button icon={<EditOutlined />} onClick={() => setEditing(value => !value)}>{editing ? '取消编辑' : '编辑'}</Button>}>
        {detail && <>
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="状态"><Tag color={statusLabels[detail.status].color}>{statusLabels[detail.status].text}</Tag></Descriptions.Item>
            <Descriptions.Item label="规则">{detail.rule_name}</Descriptions.Item>
            <Descriptions.Item label="来源">{detail.source_chat_name || detail.source_chat_id}</Descriptions.Item>
            <Descriptions.Item label="消息 ID">{detail.source_message_id}</Descriptions.Item>
            <Descriptions.Item label="发送者">{detail.sender_name || detail.sender_username || detail.sender_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="模式">{detail.delivery_mode === 'manual' ? '人工审核' : '自动发送'}</Descriptions.Item>
          </Descriptions>
          {editing ? <Form form={form} layout="vertical" style={{ marginTop: 20 }}>
            <Form.Item label="最终文本" name="text"><Input.TextArea rows={8} /></Form.Item>
            <Form.Item label="发送目标" name="target_ids" rules={[{ required: true, type: 'array', min: 1, message: '至少选择一个目标' }]}><Select mode="multiple" options={messageTargetOptions(targetsQuery.data || [], detail.available_target_ids)} /></Form.Item>
            <Space>
              <Button onClick={() => submitEdit(false)} loading={save.isPending}>保存</Button>
              <Button type="primary" icon={<SendOutlined />} onClick={() => submitEdit(true)} loading={save.isPending}>保存并推送</Button>
            </Space>
          </Form> : <div style={{ marginTop: 20 }}><Text strong>最终文本</Text><Paragraph style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{detail.processed_text || '(空)'}</Paragraph></div>}
          {detail.error_message && <Paragraph type="danger">{detail.error_message}</Paragraph>}
          <Title level={5}>附件</Title>
          {detail.resources.length ? detail.resources.map(resource => <MediaPreview key={resource.id} resource={resource} />) : <Text type="secondary">无附件</Text>}
          <Title level={5} style={{ marginTop: 20 }}>投递记录</Title>
          <Table size="small" rowKey="id" pagination={false} dataSource={detail.deliveries || []} columns={[
            { title: '目标', dataIndex: 'target_name' }, { title: '类型', dataIndex: 'target_type' },
            { title: '状态', dataIndex: 'status', render: value => <Tag>{value}</Tag> },
            { title: '尝试', dataIndex: 'attempt_count' }, { title: '错误', dataIndex: 'last_error', ellipsis: true },
          ]} />
        </>}
      </Drawer>
    </div>
  );
};

export default MessageQueuePage;
