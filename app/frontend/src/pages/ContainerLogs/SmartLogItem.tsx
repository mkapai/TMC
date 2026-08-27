import React, { useState } from 'react';
import { Tag, Space, Typography, Tooltip, Button } from 'antd';
import { 
  DownOutlined, 
  UpOutlined, 
  CopyOutlined, 
  LinkOutlined,
  ClockCircleOutlined 
} from '@ant-design/icons';
import { useThemeContext } from '../../theme';
import LogHighlighter from './LogHighlighter';

const { Text } = Typography;

interface LogEntry {
  type: 'log' | 'connected' | 'error';
  message: string;
  timestamp?: string;
  source?: string;
  level?: string;
  module?: string;
  function?: string;
  line_number?: number;
  emoji?: string;
  action_type?: string;
  entities?: Record<string, any>;
  severity_score?: number;
  content_types?: string[];
  special_content?: Record<string, any>;
  formatted_message?: string;
  raw?: string;
}

interface SmartLogItemProps {
  log: LogEntry;
  index: number;
  showSource?: boolean;
  isStructured?: boolean;
  onCopyLog?: (log: LogEntry) => void;
  onShowContext?: (log: LogEntry) => void;
}

/**
 * 智能日志条目组件
 * 支持自动折叠长日志、展示结构化信息、语法高亮等
 */
const SmartLogItem: React.FC<SmartLogItemProps> = ({
  log,
  index,
  showSource = false,
  isStructured = true,
  onCopyLog,
  onShowContext
}) => {
  void index;
  const { colors } = useThemeContext();
  const [isExpanded, setIsExpanded] = useState(false);
  
  // 判断是否为长日志（超过200字符）
  const isLongLog = log.message && log.message.length > 200;
  
  // 判断消息是否应该被截断
  const shouldTruncate = isLongLog && !isExpanded;
  
  // 显示的消息内容
  const displayMessage = shouldTruncate 
    ? log.message.substring(0, 200) + '...' 
    : log.message;

  /**
   * 获取操作类型的颜色
   */
  const getActionTypeColor = (actionType?: string): string => {
    const colorMap: Record<string, string> = {
      'error': 'red',
      'forward': 'blue',
      'create': 'green',
      'delete': 'orange',
      'query': 'cyan',
      'auth': 'purple',
      'update': 'geekblue',
      'startup': 'lime',
      'shutdown': 'volcano'
    };
    return colorMap[actionType || ''] || 'default';
  };

  /**
   * 获取日志级别的样式
   */
  const getLevelStyle = (level?: string) => {
    const styleMap: Record<string, any> = {
      'DEBUG': { color: '#8c8c8c', bg: 'rgba(128, 128, 128, 0.1)' },
      'INFO': { color: '#1890ff', bg: 'rgba(24, 144, 255, 0.1)' },
      'WARNING': { color: '#faad14', bg: 'rgba(250, 173, 20, 0.1)' },
      'ERROR': { color: '#ff4d4f', bg: 'rgba(255, 77, 79, 0.1)' },
      'CRITICAL': { color: '#cf1322', bg: 'rgba(207, 19, 34, 0.2)' }
    };
    return styleMap[level || 'INFO'] || styleMap['INFO'];
  };

  /**
   * 复制日志到剪贴板
   */
  const handleCopy = () => {
    const textToCopy = log.raw || log.message;
    navigator.clipboard.writeText(textToCopy);
    if (onCopyLog) {
      onCopyLog(log);
    }
  };

  /**
   * 格式化时间戳
   */
  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    } catch {
      return timestamp;
    }
  };

  const levelStyle = getLevelStyle(log.level);

  return (
    <div 
      className="smart-log-item"
      style={{
        padding: '10px 14px',
        marginBottom: '6px',
        borderRadius: '6px',
        background: colors.bgContainer,
        border: `1px solid ${colors.borderLight}`,
        transition: 'all 0.2s',
        position: 'relative'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = colors.info;
        e.currentTarget.style.boxShadow = `0 2px 8px ${colors.info}20`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = colors.borderLight;
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {isStructured && log.action_type ? (
        /* 结构化日志展示 */
        <>
          {/* 头部：时间、级别、操作类型、emoji */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            {/* Emoji */}
            {log.emoji && (
              <span style={{ fontSize: '18px' }}>{log.emoji}</span>
            )}
            
            {/* 时间戳 */}
            <Tooltip title={log.timestamp}>
              <Text type="secondary" style={{ fontSize: '11px', minWidth: '60px' }}>
                <ClockCircleOutlined style={{ marginRight: '4px' }} />
                {formatTimestamp(log.timestamp)}
              </Text>
            </Tooltip>
            
            {/* 级别标签 */}
            <Tag 
              style={{ 
                fontSize: '11px', 
                padding: '0 8px',
                margin: 0,
                color: levelStyle.color,
                background: levelStyle.bg,
                border: `1px solid ${levelStyle.color}`
              }}
            >
              {log.level}
            </Tag>
            
            {/* 操作类型标签 */}
            <Tag 
              color={getActionTypeColor(log.action_type)}
              style={{ fontSize: '11px', padding: '0 8px', margin: 0 }}
            >
              {log.action_type}
            </Tag>
            
            {/* 来源标签 */}
            {showSource && log.source && (
              <Tag color="purple" style={{ fontSize: '11px', padding: '0 6px', margin: 0 }}>
                {log.source}
              </Tag>
            )}
            
            {/* 模块信息 */}
            {log.module && (
              <Text type="secondary" style={{ fontSize: '11px', fontFamily: 'Monaco, Consolas, monospace' }}>
                {log.module}:{log.function}
              </Text>
            )}
            
            {/* 严重性分数（高分数时显示）*/}
            {log.severity_score && log.severity_score >= 70 && (
              <Tooltip title={`严重性分数: ${log.severity_score}/100`}>
                <Tag color="red" style={{ fontSize: '10px', padding: '0 6px', margin: 0 }}>
                  ⚠️ {log.severity_score}
                </Tag>
              </Tooltip>
            )}
            
            {/* 操作按钮 */}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px' }}>
              <Tooltip title="复制">
                <Button 
                  type="text" 
                  size="small" 
                  icon={<CopyOutlined />}
                  onClick={handleCopy}
                  style={{ padding: '2px 4px', height: '24px' }}
                />
              </Tooltip>
              {onShowContext && (
                <Tooltip title="查看上下文">
                  <Button 
                    type="text" 
                    size="small" 
                    icon={<LinkOutlined />}
                    onClick={() => onShowContext(log)}
                    style={{ padding: '2px 4px', height: '24px' }}
                  />
                </Tooltip>
              )}
            </div>
          </div>
          
          {/* 消息内容 */}
          <div style={{ marginLeft: '26px', marginBottom: '8px' }}>
            <LogHighlighter 
              content={displayMessage}
              contentTypes={log.content_types}
              specialContent={log.special_content}
            />
            
            {/* 展开/收起按钮（长日志） */}
            {isLongLog && (
              <Button 
                type="link" 
                size="small"
                onClick={() => setIsExpanded(!isExpanded)}
                style={{ padding: '4px 0', height: 'auto', fontSize: '12px' }}
              >
                {isExpanded ? <UpOutlined /> : <DownOutlined />}
                {isExpanded ? ' 收起' : ` 展开 (${log.message.length} 字符)`}
              </Button>
            )}
          </div>
          
          {/* 实体信息（如果有） */}
          {log.entities && Object.keys(log.entities).length > 0 && (
            <div style={{ marginLeft: '26px', marginTop: '8px' }}>
              <Space size="small" wrap>
                {Object.entries(log.entities).map(([key, value]) => (
                  <Tag 
                    key={key} 
                    style={{ 
                      fontSize: '10px',
                      background: colors.bgLayout,
                      border: `1px solid ${colors.border}`
                    }}
                  >
                    <Text type="secondary" style={{ fontSize: '10px' }}>
                      {key}:
                    </Text>{' '}
                    <Text strong style={{ fontSize: '10px' }}>
                      {String(value)}
                    </Text>
                  </Tag>
                ))}
              </Space>
            </div>
          )}
        </>
      ) : (
        /* 传统日志展示 */
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
          {/* 时间戳 */}
          <Text type="secondary" style={{ fontSize: '11px', minWidth: '60px' }}>
            {formatTimestamp(log.timestamp)}
          </Text>
          
          {/* 来源 */}
          {showSource && log.source && (
            <Tag color="purple" style={{ fontSize: '11px', padding: '0 6px' }}>
              {log.source}
            </Tag>
          )}
          
          {/* 消息 */}
          <div style={{ flex: 1 }}>
            <LogHighlighter content={displayMessage} />
            {isLongLog && (
              <Button 
                type="link" 
                size="small"
                onClick={() => setIsExpanded(!isExpanded)}
                style={{ padding: '4px 0', height: 'auto', fontSize: '12px' }}
              >
                {isExpanded ? <UpOutlined /> : <DownOutlined />}
                {isExpanded ? ' 收起' : ` 展开`}
              </Button>
            )}
          </div>
          
          {/* 操作按钮 */}
          <Button 
            type="text" 
            size="small" 
            icon={<CopyOutlined />}
            onClick={handleCopy}
            style={{ padding: '2px 4px', height: '24px' }}
          />
        </div>
      )}
    </div>
  );
};

export default SmartLogItem;
