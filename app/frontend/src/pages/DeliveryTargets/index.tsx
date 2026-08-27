import React, { useEffect } from 'react';
import { Button, Form, Input, Modal, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { chatsApi } from '../../services/chats';
import { clientsApi } from '../../services/clients';
import { deliveryTargetsApi } from '../../services/deliveryTargets';
import type { DeliveryTarget, DeliveryTargetInput } from '../../types/delivery';
import { buildDeliveryTargetInput, type DeliveryTargetFormValues } from './helpers';

const { Title, Text } = Typography;
const MASK = '********';

const DeliveryTargetsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const targetType = Form.useWatch('target_type', form);
  const [editing, setEditing] = React.useState<DeliveryTarget>();
  const [open, setOpen] = React.useState(false);
  const targets = useQuery({ queryKey: ['delivery-targets'], queryFn: deliveryTargetsApi.list });
  const clients = useQuery({ queryKey: ['clients'], queryFn: clientsApi.getClients });
  const chats = useQuery({ queryKey: ['chats'], queryFn: chatsApi.getChats });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['delivery-targets'] });
  const save = useMutation({
    mutationFn: (input: DeliveryTargetInput) => editing ? deliveryTargetsApi.update(editing.id, input) : deliveryTargetsApi.create(input),
    onSuccess: () => { message.success('发送目标已保存'); setOpen(false); refresh(); },
    onError: (error: Error) => message.error(error.message),
  });
  const toggle = useMutation({ mutationFn: ({ id, active }: { id: number; active: boolean }) => deliveryTargetsApi.setActive(id, active), onSuccess: refresh, onError: (error: Error) => message.error(error.message) });
  const test = useMutation({ mutationFn: deliveryTargetsApi.test, onSuccess: result => message.success(result.message), onError: (error: Error) => message.error(error.message) });
  const remove = useMutation({ mutationFn: deliveryTargetsApi.remove, onSuccess: () => { message.success('发送目标已删除'); refresh(); }, onError: (error: Error) => message.error(error.message) });

  useEffect(() => {
    if (!open) return;
    if (!editing) {
      form.resetFields();
      form.setFieldsValue({ target_type: 'telegram', is_active: true, headers: [] });
      return;
    }
    form.setFieldsValue({
      name: editing.name,
      target_type: editing.target_type,
      is_active: editing.is_active,
      client_id: editing.config.client_id,
      chat_id: editing.config.chat_id,
      url: editing.config.url,
      hmac_secret: editing.config.has_hmac_secret ? MASK : '',
      headers: Object.entries(editing.config.headers || {}).map(([key, value]) => ({ key, value })),
    });
  }, [editing, form, open]);

  const submit = (values: DeliveryTargetFormValues) => {
    save.mutate(buildDeliveryTargetInput(values));
  };

  return <div style={{ padding: 24 }}>
    <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
      <Title level={2} style={{ margin: 0 }}>发送目标</Title>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(undefined); setOpen(true); }}>新增目标</Button>
    </Space>
    <Table rowKey="id" loading={targets.isLoading} dataSource={targets.data || []} columns={[
      { title: '名称', dataIndex: 'name' },
      { title: '类型', dataIndex: 'target_type', width: 110, render: value => <Tag color={value === 'telegram' ? 'blue' : 'green'}>{value}</Tag> },
      { title: '地址', render: (_: unknown, row: DeliveryTarget) => row.target_type === 'telegram' ? `${row.config.client_id} / ${row.config.chat_id}` : row.config.url },
      { title: '关联规则', dataIndex: 'rule_count', width: 100 },
      { title: '启用', dataIndex: 'is_active', width: 90, render: (active: boolean, row: DeliveryTarget) => <Switch checked={active} loading={toggle.isPending} onChange={value => toggle.mutate({ id: row.id, active: value })} /> },
      { title: '操作', width: 230, render: (_: unknown, row: DeliveryTarget) => <Space><Button size="small" onClick={() => test.mutate(row.id)} loading={test.isPending}>测试</Button><Button size="small" icon={<EditOutlined />} onClick={() => { setEditing(row); setOpen(true); }}>编辑</Button><Button size="small" danger icon={<DeleteOutlined />} onClick={() => Modal.confirm({ title: '删除发送目标？', content: `目标已关联 ${row.rule_count} 条规则，删除后会解除这些绑定。`, okButtonProps: { danger: true }, onOk: () => remove.mutateAsync(row.id) })} /></Space> },
    ]} />

    <Modal title={editing ? '编辑发送目标' : '新增发送目标'} open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={save.isPending} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={submit}>
        <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item label="类型" name="target_type" rules={[{ required: true }]}><Select disabled={Boolean(editing)} options={[{ value: 'telegram', label: 'Telegram' }, { value: 'webhook', label: 'Webhook' }]} /></Form.Item>
        <Form.Item label="启用" name="is_active" valuePropName="checked"><Switch /></Form.Item>
        {targetType === 'telegram' ? <>
          <Form.Item label="发送客户端" name="client_id" rules={[{ required: true }]}><Select options={Object.entries(clients.data?.clients || {}).map(([id, client]) => ({ value: id, label: `${id} (${client.client_type})` }))} /></Form.Item>
          <Form.Item label="目标聊天" name="chat_id" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={(chats.data?.chats || []).map(chat => ({ value: String(chat.id), label: `${chat.title || chat.first_name || chat.name || chat.id} (${chat.id})` }))} /></Form.Item>
        </> : <>
          <Form.Item label="Webhook URL" name="url" rules={[{ required: true, type: 'url' }]}><Input placeholder="https://example.com/tmc/events" /></Form.Item>
          <Form.Item label="HMAC 密钥" name="hmac_secret"><Input.Password placeholder={editing?.config.has_hmac_secret ? '留空以保留现有密钥' : '可选'} /></Form.Item>
          <Text strong>自定义请求头</Text>
          <Form.List name="headers">{(fields, { add, remove: removeHeader }) => <div>{fields.map(field => <Space key={field.key} align="baseline" style={{ display: 'flex', marginTop: 8 }}><Form.Item {...field} name={[field.name, 'key']} rules={[{ required: true }]}><Input placeholder="Header-Name" /></Form.Item><Form.Item {...field} name={[field.name, 'value']}><Input.Password placeholder="值" /></Form.Item><Button danger onClick={() => removeHeader(field.name)}>删除</Button></Space>)}<Button type="dashed" onClick={() => add()} block>添加请求头</Button></div>}</Form.List>
        </>}
      </Form>
    </Modal>
  </div>;
};

export default DeliveryTargetsPage;
