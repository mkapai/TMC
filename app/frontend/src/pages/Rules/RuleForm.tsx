import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Switch,
  Select,
  Button,
  Space,
  Typography,
  Row,
  Col,
  Divider,
  message,
  Spin,
  DatePicker
} from 'antd';
import {
  SaveOutlined,
  ArrowLeftOutlined
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rulesApi } from '../../services/rules';
import { chatsApi } from '../../services/chats';
import { clientsApi } from '../../services/clients';
import { deliveryTargetsApi } from '../../services/deliveryTargets';
import type { CreateRuleDto, UpdateRuleDto } from '../../types/rule';
import type { ApiError } from '../../types/client';
import { buildRuleDeliveryFields } from './deliveryFields';
// z-index问题已在 styles/components/modal.css 中解决

const { Title } = Typography;
const { Option } = Select;

const RuleForm: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const isEdit = Boolean(id);
  const ruleId = id ? parseInt(id, 10) : undefined;

  // 获取聊天列表
  const { data: chatsData } = useQuery({
    queryKey: ['chats'],
    queryFn: chatsApi.getChats
  });

  // 获取客户端列表
  const { data: clientsData } = useQuery({
    queryKey: ['clients'],
    queryFn: clientsApi.getClients
  });

  const { data: deliveryTargets = [] } = useQuery({
    queryKey: ['delivery-targets'],
    queryFn: deliveryTargetsApi.list,
  });

  // 获取规则详情（编辑模式）
  const { data: ruleData, isLoading: isLoadingRule, error: ruleError } = useQuery({
    queryKey: ['rule', ruleId],
    queryFn: () => rulesApi.get(ruleId!),
    enabled: isEdit && !!ruleId,
    retry: 2,
  });

  // 调试日志
  React.useEffect(() => {
    console.log('RuleForm - 路由参数:', { id, ruleId, isEdit });
    console.log('RuleForm - 规则数据:', ruleData);
    console.log('RuleForm - 加载状态:', isLoadingRule);
    if (ruleError) {
      console.error('RuleForm - 加载错误:', ruleError);
    }
  }, [id, ruleId, isEdit, ruleData, isLoadingRule, ruleError]);

  // 创建规则
  const createMutation = useMutation({
    mutationFn: (data: CreateRuleDto) => rulesApi.create(data),
    onSuccess: () => {
      message.success('规则创建成功');
      queryClient.invalidateQueries({ queryKey: ['rules'] });
      navigate('/rules');
    },
    onError: (error: ApiError) => {
      message.error(error.response?.data?.message || '创建规则失败');
    }
  });

  // 更新规则
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateRuleDto }) => 
      rulesApi.update(id, data),
    onSuccess: () => {
      message.success('规则更新成功');
      queryClient.invalidateQueries({ queryKey: ['rules'] });
      queryClient.invalidateQueries({ queryKey: ['rule', ruleId] });
      navigate('/rules');
    },
    onError: (error: ApiError) => {
      message.error(error.response?.data?.message || '更新规则失败');
    }
  });

  // 填充表单数据（编辑模式）
  useEffect(() => {
    if (ruleData) {
      console.log('设置表单数据:', ruleData);
      form.setFieldsValue({
        name: ruleData.name,
        source_chat_id: ruleData.source_chat_id,
        delivery_mode: ruleData.delivery_mode,
        destination_ids: ruleData.destination_ids,
        enable_keyword_filter: ruleData.enable_keyword_filter,
        enable_regex_replace: ruleData.enable_regex_replace,
        forward_delay: ruleData.forward_delay,
        enable_link_preview: ruleData.enable_link_preview,
        enable_text: ruleData.enable_text,
        enable_photo: ruleData.enable_photo,
        enable_video: ruleData.enable_video,
        enable_document: ruleData.enable_document,
        enable_audio: ruleData.enable_audio,
        enable_voice: ruleData.enable_voice,
        enable_sticker: ruleData.enable_sticker,
        enable_animation: ruleData.enable_animation,
        enable_webpage: ruleData.enable_webpage,
        time_filter_type: ruleData.time_filter_type,
        start_time: ruleData.start_time ? dayjs(ruleData.start_time) : null,
        end_time: ruleData.end_time ? dayjs(ruleData.end_time) : null,
        client_id: ruleData.client_id || 'main_user',
        client_type: ruleData.client_type === 'user' ? '用户' : ruleData.client_type === 'bot' ? '机器人' : ruleData.client_type || 'user'
      });
    }
  }, [ruleData, form]);

  // 监听客户端数据变化，为新建规则设置默认值
  useEffect(() => {
    if (!isEdit && clientsData?.clients) {
      // 为新建规则设置默认客户端
      const availableClients = Object.entries(clientsData.clients);
      if (availableClients.length > 0) {
        const [defaultClientId, defaultClient] = availableClients[0];
        const currentClientId = form.getFieldValue('client_id');
        
        if (!currentClientId) {
          const displayType = defaultClient.client_type === 'user' ? '用户' : '机器人';
          form.setFieldsValue({ 
            client_id: defaultClientId,
            client_type: displayType
          });
        }
      }
    }
  }, [clientsData, form, isEdit]);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    try {
      // 从聊天列表中查找对应的聊天名称 (处理字符串和数字类型匹配)
      const sourceChat = chats.find(chat => String(chat.id) === String(values.source_chat_id));
      const sourceChatName = sourceChat ? (sourceChat.title || sourceChat.id) : '';

      const ruleData = {
        name: values.name,
        source_chat_id: values.source_chat_id,
        source_chat_name: sourceChatName,
        ...buildRuleDeliveryFields(values),
        
        // 功能开关
        enable_keyword_filter: values.enable_keyword_filter || false,
        enable_regex_replace: values.enable_regex_replace || false,
        
        // 消息类型过滤
        enable_text: values.enable_text !== false,
        enable_photo: values.enable_photo !== false,
        enable_video: values.enable_video !== false,
        enable_document: values.enable_document !== false,
        enable_audio: values.enable_audio !== false,
        enable_voice: values.enable_voice !== false,
        enable_sticker: values.enable_sticker || false,
        enable_animation: values.enable_animation !== false,
        enable_webpage: values.enable_webpage !== false,
        
        // 高级设置
        forward_delay: values.forward_delay || 0,
        enable_link_preview: values.enable_link_preview !== false,
        
        // 时间过滤
        time_filter_type: values.time_filter_type || 'after_start',
        start_time: values.start_time,
        end_time: values.end_time,
        
        // 客户端选择
        client_id: values.client_id || 'main_user',
        client_type: values.client_type === '用户' ? 'user' : values.client_type === '机器人' ? 'bot' : values.client_type || 'user',
        
        // 【新功能】消息去重
        enable_deduplication: values.enable_deduplication || false,
        dedup_time_window: values.dedup_time_window || 3600,
        dedup_check_content: values.dedup_check_content !== false,
        dedup_check_media: values.dedup_check_media !== false,
        
        // 【新功能】发送者过滤
        enable_sender_filter: values.enable_sender_filter || false,
        sender_filter_mode: values.sender_filter_mode || 'whitelist',
        sender_whitelist: values.sender_whitelist || null,
        sender_blacklist: values.sender_blacklist || null
      };

      if (isEdit && ruleId) {
        updateMutation.mutate({ id: ruleId, data: ruleData });
      } else {
        createMutation.mutate(ruleData);
      }
    } catch (error) {
      console.error('提交失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    navigate('/rules');
  };

  if (isEdit && isLoadingRule) {
    return (
      <Card className="glass-card">
        <div style={{ textAlign: 'center', padding: '50px' }}>
          <Spin size="large" />
          <div style={{ marginTop: '16px', color: 'var(--color-text-primary)' }}>加载规则数据...</div>
        </div>
      </Card>
    );
  }

  const chats = chatsData?.chats || [];

  return (
    <Card className="glass-card">
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Button 
            icon={<ArrowLeftOutlined />}
            onClick={handleBack}
            style={{ marginRight: '16px' }}
          >
            返回
          </Button>
          <Title level={2} style={{ margin: 0, color: 'var(--color-text-primary)' }}>
            {isEdit ? '编辑转发规则' : '创建转发规则'}
          </Title>
        </div>
      </div>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          enable_text: true,
          enable_photo: true,
          enable_video: true,
          enable_document: true,
          enable_audio: true,
          enable_voice: true,
          enable_sticker: false,
          enable_animation: true,
          enable_webpage: true,
          enable_link_preview: true,
          forward_delay: 0,
          client_id: 'main_user',
          client_type: 'user',
          delivery_mode: 'auto',
          destination_ids: [],
          time_filter_type: 'after_start',
          // 新功能默认值
          enable_deduplication: false,
          dedup_time_window: 3600,
          dedup_check_content: true,
          dedup_check_media: true,
          enable_sender_filter: false,
          sender_filter_mode: 'whitelist'
        }}
      >
        <Row gutter={24}>
          <Col span={24}>
            <Form.Item
              label="规则名称"
              name="name"
              rules={[{ required: true, message: '请输入规则名称' }]}
            >
              <Input placeholder="为这个转发规则起一个易识别的名称" />
            </Form.Item>
          </Col>
        </Row>

        <Divider orientation="left">转发配置</Divider>

        <Row gutter={24}>
          <Col span={12}>
            <Form.Item
              label="源聊天"
              name="source_chat_id"
              rules={[{ required: true, message: '请选择或输入源聊天ID' }]}
            >
              <Select
                showSearch
                placeholder="选择源聊天或输入聊天ID"
                allowClear
                dropdownStyle={{ zIndex: 1051 }}
                getPopupContainer={(triggerNode) => triggerNode.parentNode as HTMLElement}
                filterOption={(input, option) =>
                  String(option?.children || '').toLowerCase().includes(input.toLowerCase())
                }
              >
                {chats.map(chat => (
                  <Option key={chat.id} value={chat.id}>
                    {chat.title || chat.first_name || chat.name} ({chat.id})
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="发送模式"
              name="delivery_mode"
              rules={[{ required: true, message: '请选择发送模式' }]}
            >
              <Select options={[{ value: 'auto', label: '自动发送' }, { value: 'manual', label: '人工审核' }]} />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          label="发送目标"
          name="destination_ids"
          rules={[{ required: true, type: 'array', min: 1, message: '至少选择一个发送目标' }]}
        >
          <Select
            mode="multiple"
            placeholder="选择一个或多个 Telegram / Webhook 目标"
            optionFilterProp="label"
            options={deliveryTargets.filter(target => target.is_active || ruleData?.destination_ids.includes(target.id)).map(target => ({
              value: target.id,
              label: `${target.name} (${target.target_type})`,
            }))}
          />
        </Form.Item>

        <Divider orientation="left">客户端选择</Divider>
        
        <Row gutter={24}>
          <Col span={12}>
            <Form.Item
              label="使用的客户端"
              name="client_id"
              rules={[{ required: true, message: '请选择客户端' }]}
            >
              <Select
                placeholder="选择要使用的客户端"
                allowClear
                dropdownStyle={{ zIndex: 1051 }}
                getPopupContainer={(triggerNode) => triggerNode.parentNode as HTMLElement}
                onChange={(value) => {
                  // 当选择客户端时，自动设置客户端类型
                  if (value && clientsData?.clients?.[value]) {
                    const clientType = clientsData.clients[value].client_type;
                    const displayType = clientType === 'user' ? '用户' : '机器人';
                    form.setFieldsValue({ client_type: displayType });
                  }
                }}
              >
                {clientsData?.clients && Object.entries(clientsData.clients).map(([clientId, client]) => (
                  <Option key={clientId} value={clientId}>
                    {clientId} ({client.client_type === 'user' ? '用户' : '机器人'}) 
                    {client.connected ? ' ✅' : ' ❌'}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="客户端类型"
              name="client_type"
            >
              <Input
                placeholder="将根据选择的客户端自动设置"
                readOnly
                disabled
              />
            </Form.Item>
          </Col>
        </Row>

        <Divider orientation="left">消息类型过滤</Divider>

        <Row gutter={24}>
          <Col span={6}>
            <Form.Item label="转发文本消息" name="enable_text" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="转发图片" name="enable_photo" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="转发视频" name="enable_video" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="转发文档" name="enable_document" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={24}>
          <Col span={6}>
            <Form.Item label="转发音频" name="enable_audio" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="转发语音" name="enable_voice" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="转发贴纸" name="enable_sticker" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="转发动图" name="enable_animation" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={24}>
          <Col span={6}>
            <Form.Item label="转发网页" name="enable_webpage" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="启用关键词过滤" name="enable_keyword_filter" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="启用正则替换" name="enable_regex_replace" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="启用链接预览" name="enable_link_preview" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Divider orientation="left">高级设置</Divider>

        <Row gutter={24}>
          <Col span={12}>
            <Form.Item
              label="转发延迟 (秒)"
              name="forward_delay"
              tooltip="消息转发前的延迟时间，0表示立即转发"
            >
              <InputNumber min={0} max={3600} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="时间过滤"
              name="time_filter_type"
              tooltip={
                <div style={{ maxWidth: '400px' }}>
                  <div><strong>时间过滤规则详解：</strong></div>
                  <div style={{ marginTop: '8px' }}>
                    <div><strong>1. 仅转发启动后的消息</strong>：从启动或开启转发功能的那一刻起，只转发之后产生的新消息</div>
                    <div><strong>2. 不限制时间</strong>：对收到的实时消息不增加时间条件</div>
                    <div><strong>3. 仅转发当天消息</strong>：以自然日(0点-24点)为标准，只转发当天的消息</div>
                    <div><strong>4. 从指定时间开始</strong>：回填并转发从自定义日期时间点开始的历史及新消息</div>
                    <div><strong>5. 指定时间段内</strong>：回填并转发设定时间段内的历史消息</div>
                  </div>
                </div>
              }
            >
              <Select>
                <Option value="after_start">仅转发启动后的消息</Option>
                <Option value="all_messages">实时消息不限制时间</Option>
                <Option value="today_only">仅转发当天消息</Option>
                <Option value="from_time">从指定时间开始</Option>
                <Option value="time_range">指定时间段内</Option>
              </Select>
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          noStyle
          shouldUpdate={(prevValues, currentValues) =>
            prevValues.time_filter_type !== currentValues.time_filter_type
          }
        >
          {({ getFieldValue }) => {
            const timeFilterType = getFieldValue('time_filter_type');
            const showStartTime = timeFilterType === 'from_time' || timeFilterType === 'time_range';
            const showEndTime = timeFilterType === 'time_range';
            
            return (showStartTime || showEndTime) ? (
              <Row gutter={24} style={{ marginTop: '16px' }}>
                {showStartTime && (
                  <Col span={showEndTime ? 12 : 24}>
                    <Form.Item
                      label={timeFilterType === 'from_time' ? "开始时间" : "起始时间"}
                      name="start_time"
                      rules={[{ required: true, message: '请选择开始时间' }]}
                      tooltip={
                        timeFilterType === 'from_time' 
                          ? "从这个时间点开始转发所有消息" 
                          : "时间段的开始时间"
                      }
                    >
                      <DatePicker 
                        showTime
                        style={{ width: '100%' }} 
                        format="YYYY-MM-DD HH:mm:ss"
                        placeholder="选择开始日期时间"
                      />
                    </Form.Item>
                  </Col>
                )}
                {showEndTime && (
                  <Col span={12}>
                    <Form.Item
                      label="结束时间"
                      name="end_time"
                      rules={[{ required: true, message: '请选择结束时间' }]}
                      tooltip="时间段的结束时间，超过此时间的消息不会被转发"
                    >
                      <DatePicker 
                        showTime
                        style={{ width: '100%' }} 
                        format="YYYY-MM-DD HH:mm:ss"
                        placeholder="选择结束日期时间"
                      />
                    </Form.Item>
                  </Col>
                )}
              </Row>
            ) : null;
          }}
        </Form.Item>

        <Divider orientation="left">消息去重</Divider>

        <Row gutter={24}>
          <Col span={6}>
            <Form.Item 
              label="启用消息去重" 
              name="enable_deduplication" 
              valuePropName="checked"
              tooltip="防止重复消息被多次转发，有效减少刷屏"
            >
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item noStyle shouldUpdate={(prevValues, currentValues) => 
          prevValues.enable_deduplication !== currentValues.enable_deduplication
        }>
          {({ getFieldValue }) => {
            const enableDedup = getFieldValue('enable_deduplication');
            return enableDedup ? (
              <>
                <Row gutter={24}>
                  <Col span={8}>
                    <Form.Item
                      label="去重时间窗口 (秒)"
                      name="dedup_time_window"
                      tooltip="在此时间窗口内，相同的消息只转发一次。默认3600秒(1小时)"
                    >
                      <InputNumber 
                        min={60} 
                        max={86400} 
                        style={{ width: '100%' }}
                        placeholder="3600"
                      />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item 
                      label="检查消息内容" 
                      name="dedup_check_content" 
                      valuePropName="checked"
                      tooltip="根据消息文本内容判断是否重复"
                    >
                      <Switch />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item 
                      label="检查媒体文件" 
                      name="dedup_check_media" 
                      valuePropName="checked"
                      tooltip="根据媒体文件判断是否重复（图片、视频等）"
                    >
                      <Switch />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            ) : null;
          }}
        </Form.Item>

        <Divider orientation="left">发送者过滤</Divider>

        <Row gutter={24}>
          <Col span={6}>
            <Form.Item 
              label="启用发送者过滤" 
              name="enable_sender_filter" 
              valuePropName="checked"
              tooltip="只转发特定发送者的消息，或阻止特定发送者"
            >
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item noStyle shouldUpdate={(prevValues, currentValues) => 
          prevValues.enable_sender_filter !== currentValues.enable_sender_filter
        }>
          {({ getFieldValue }) => {
            const enableFilter = getFieldValue('enable_sender_filter');
            return enableFilter ? (
              <>
                <Row gutter={24}>
                  <Col span={8}>
                    <Form.Item
                      label="过滤模式"
                      name="sender_filter_mode"
                      tooltip="白名单：只转发名单中的发送者；黑名单：阻止名单中的发送者"
                    >
                      <Select placeholder="选择过滤模式">
                        <Option value="whitelist">白名单模式</Option>
                        <Option value="blacklist">黑名单模式</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={24}>
                  <Col span={12}>
                    <Form.Item
                      label="白名单"
                      name="sender_whitelist"
                      tooltip="输入允许转发的发送者，每行一个或用逗号分隔。支持用户名（@username）或用户ID（数字）"
                      help={
                        <div style={{ fontSize: '12px', color: '#8c8c8c' }}>
                          💡 支持多种格式：
                          <br />• 用户名：<code>@username1, @username2</code>
                          <br />• 用户ID：<code>123456, 789012</code>
                          <br />• 混合：<code>@alice, 123456, @bob</code>
                        </div>
                      }
                    >
                      <Input.TextArea
                        rows={4}
                        placeholder="@username1, @username2, 123456"
                      />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item
                      label="黑名单"
                      name="sender_blacklist"
                      tooltip="输入要阻止的发送者，每行一个或用逗号分隔。支持用户名（@username）或用户ID（数字）"
                      help={
                        <div style={{ fontSize: '12px', color: '#8c8c8c' }}>
                          💡 支持多种格式：
                          <br />• 用户名：<code>@spammer1, @spammer2</code>
                          <br />• 用户ID：<code>987654, 321098</code>
                          <br />• 混合：<code>@spam_bot, 999999</code>
                        </div>
                      }
                    >
                      <Input.TextArea
                        rows={4}
                        placeholder="@spammer, 987654"
                      />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            ) : null;
          }}
        </Form.Item>

        <div style={{ textAlign: 'right', marginTop: '32px' }}>
          <Space>
            <Button onClick={handleBack}>
              取消
            </Button>
            <Button
              type="primary"
              htmlType="submit"
              icon={<SaveOutlined />}
              loading={loading || createMutation.isPending || updateMutation.isPending}
            >
              {isEdit ? '更新规则' : '创建规则'}
            </Button>
          </Space>
        </div>
      </Form>
    </Card>
  );
};

export default RuleForm;
