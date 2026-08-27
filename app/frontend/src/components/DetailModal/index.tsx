import React from 'react';
import { Modal, Descriptions, Tag, Typography, Space, Divider } from 'antd';
import {
  UserOutlined,
  TeamOutlined,
  GlobalOutlined,
  LockOutlined,
  ClockCircleOutlined,
  LinkOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MessageOutlined,
  RobotOutlined,
  IdcardOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import './styles.css';

const { Text, Paragraph } = Typography;

interface DetailItem {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  span?: number;
}

interface DetailModalProps {
  visible: boolean;
  onClose: () => void;
  title: string;
  icon?: React.ReactNode;
  items: DetailItem[];
  extra?: React.ReactNode;
}

export const DetailModal: React.FC<DetailModalProps> = ({
  visible,
  onClose,
  title,
  icon,
  items,
  extra,
}) => {
  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      width={600}
      title={
        <Space>
          {icon}
          <Text strong style={{ fontSize: 16 }}>
            {title}
          </Text>
        </Space>
      }
      className="detail-modal"
    >
      <Descriptions
        bordered
        column={1}
        size="small"
        labelStyle={{
          width: '120px',
          fontWeight: 500,
          backgroundColor: 'var(--detail-label-bg)',
        }}
        contentStyle={{
          backgroundColor: 'var(--detail-content-bg)',
        }}
      >
        {items.map((item, index) => (
          <Descriptions.Item
            key={index}
            label={
              <Space size={4}>
                {item.icon}
                {item.label}
              </Space>
            }
            span={item.span || 1}
          >
            {item.value}
          </Descriptions.Item>
        ))}
      </Descriptions>
      {extra && (
        <>
          <Divider style={{ margin: '16px 0' }} />
          {extra}
        </>
      )}
    </Modal>
  );
};

// 预定义的详情卡片配置函数

export const createChatDetailItems = (record: any): DetailItem[] => {
  const chatTypeText =
    record.type === 'private' ? '私聊' :
    record.type === 'group' ? '群组' :
    record.type === 'supergroup' ? '超级群组' :
    record.type === 'channel' ? '频道' : record.type;

  const isPrivateGroup = record.type === 'group' || record.type === 'supergroup';
  const hasInviteLink = !!record.invite_link;
  const isPublic = record.username || hasInviteLink;
  let privacyStatus = '';

  if (record.type === 'private') {
    privacyStatus = '私聊';
  } else if (record.type === 'channel') {
    privacyStatus = isPublic ? '公开频道' : '私密频道';
  } else if (isPrivateGroup) {
    privacyStatus = isPublic ? '公开群组' : '私密群组';
  }

  const items: DetailItem[] = [
    {
      label: '聊天名称',
      icon: <MessageOutlined />,
      value: <Text strong>{record.title || record.first_name || '未知聊天'}</Text>,
    },
  ];

  if (record.username) {
    items.push({
      label: '用户名',
      icon: <UserOutlined />,
      value: <Text copyable code>@{record.username}</Text>,
    });
  }

  items.push(
    {
      label: 'ID',
      icon: <IdcardOutlined />,
      value: <Text copyable code>{record.id}</Text>,
    },
    {
      label: '类型',
      icon: <GlobalOutlined />,
      value: (
        <Tag color={
          record.type === 'private' ? 'blue' :
          record.type === 'channel' ? 'purple' :
          'green'
        }>
          {chatTypeText}
        </Tag>
      ),
    },
    {
      label: '隐私状态',
      icon: isPublic ? <GlobalOutlined /> : <LockOutlined />,
      value: (
        <Tag color={isPublic ? 'success' : 'warning'}>
          {privacyStatus}
        </Tag>
      ),
    }
  );

  if (record.description) {
    items.push({
      label: '描述',
      icon: <MessageOutlined />,
      value: <Paragraph ellipsis={{ rows: 3, expandable: true }}>{record.description}</Paragraph>,
    });
  }

  if (record.type !== 'private' && record.members_count) {
    items.push({
      label: '成员数',
      icon: <TeamOutlined />,
      value: <Text>{record.members_count.toLocaleString()}</Text>,
    });
  }

  items.push(
    {
      label: '状态',
      icon: record.is_active !== false ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
      value: (
        <Tag color={record.is_active !== false ? 'success' : 'default'}>
          {record.is_active !== false ? '活跃' : '非活跃'}
        </Tag>
      ),
    },
    {
      label: '最后活动',
      icon: <ClockCircleOutlined />,
      value: <Text>{record.last_activity ? dayjs(record.last_activity).format('YYYY-MM-DD HH:mm:ss') : '未知'}</Text>,
    }
  );

  if (record.invite_link) {
    items.push({
      label: '邀请链接',
      icon: <LinkOutlined />,
      value: (
        <Text copyable ellipsis style={{ maxWidth: 400 }}>
          {record.invite_link}
        </Text>
      ),
    });
  }

  return items;
};

export const createClientDetailItems = (record: any): DetailItem[] => {
  const items: DetailItem[] = [
    {
      label: '客户端ID',
      icon: <IdcardOutlined />,
      value: <Text copyable code>{record.client_id}</Text>,
    },
    {
      label: '类型',
      icon: record.client_type === 'bot' ? <RobotOutlined /> : <UserOutlined />,
      value: (
        <Tag color={record.client_type === 'bot' ? 'blue' : 'green'}>
          {record.client_type === 'bot' ? '机器人' : '用户'}
        </Tag>
      ),
    },
    {
      label: '运行状态',
      icon: record.running ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
      value: (
        <Tag color={record.running ? 'success' : 'default'}>
          {record.running ? '运行中' : '已停止'}
        </Tag>
      ),
    },
    {
      label: '连接状态',
      icon: record.connected ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
      value: (
        <Tag color={record.connected ? 'success' : 'error'}>
          {record.connected ? '已连接' : '未连接'}
        </Tag>
      ),
    },
    {
      label: '线程状态',
      icon: record.thread_alive ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
      value: (
        <Tag color={record.thread_alive ? 'success' : 'error'}>
          {record.thread_alive ? '活跃' : '停止'}
        </Tag>
      ),
    },
  ];

  if (record.user_info) {
    const userInfo = record.user_info;
    if (userInfo.id) {
      items.push({
        label: '用户ID',
        icon: <IdcardOutlined />,
        value: <Text copyable code>{userInfo.id}</Text>,
      });
    }
    if (userInfo.username) {
      items.push({
        label: '用户名',
        icon: <UserOutlined />,
        value: <Text copyable>@{userInfo.username}</Text>,
      });
    }
    if (userInfo.first_name || userInfo.last_name) {
      items.push({
        label: '姓名',
        icon: <UserOutlined />,
        value: <Text>{[userInfo.first_name, userInfo.last_name].filter(Boolean).join(' ')}</Text>,
      });
    }
    if (userInfo.phone) {
      items.push({
        label: '电话',
        icon: <UserOutlined />,
        value: <Text copyable>{userInfo.phone}</Text>,
      });
    }
  }

  items.push({
    label: '监控聊天',
    icon: <TeamOutlined />,
    value: <Text>{record.monitored_chats?.length || 0} 个</Text>,
  });

  return items;
};
