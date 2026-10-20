// 转发规则相关类型定义

export interface ForwardRule {
  id: number;
  name: string;
  source_chat_id: string;
  source_chat_name?: string;
  delivery_mode: 'auto' | 'manual';
  destination_ids: number[];
  delivery_targets: Array<{ id: number; name: string; target_type: 'telegram' | 'webhook' }>;
  
  // 功能开关
  is_active: boolean;
  enable_keyword_filter: boolean;
  enable_regex_replace: boolean;
  
  // 客户端选择
  client_id: string;
  client_type: 'user' | 'bot';
  
  // 消息类型支持
  enable_text: boolean;
  enable_media: boolean;
  enable_photo: boolean;
  enable_video: boolean;
  enable_document: boolean;
  enable_audio: boolean;
  enable_voice: boolean;
  enable_sticker: boolean;
  enable_animation: boolean;
  enable_webpage: boolean;
  
  // 高级设置
  forward_delay: number;
  enable_link_preview: boolean;
  
  // 时间过滤设置
  time_filter_type: 'after_start' | 'all_messages' | 'today_only' | 'from_time' | 'time_range';
  start_time?: string;
  end_time?: string;

  enable_deduplication: boolean;
  dedup_time_window: number;
  dedup_check_content: boolean;
  dedup_check_media: boolean;
  enable_sender_filter: boolean;
  sender_filter_mode: 'whitelist' | 'blacklist';
  sender_whitelist?: string;
  sender_blacklist?: string;
  
  // 时间戳
  created_at: string;
  updated_at: string;
  
  // 关联数据
  keywords?: Keyword[];
  replace_rules?: ReplaceRule[];
}

export interface Keyword {
  id: number;
  rule_id: number;
  keyword: string;
  is_blacklist: boolean;
  created_at: string;
}

export interface ReplaceRule {
  id: number;
  rule_id: number;
  name?: string;
  pattern: string;
  replacement: string;
  priority: number;
  is_regex: boolean;
  is_active: boolean;
  created_at: string;
}

// 表单数据类型
export interface CreateRuleDto {
  name: string;
  source_chat_id: string;
  source_chat_name?: string;
  delivery_mode: 'auto' | 'manual';
  destination_ids: number[];
  
  // 功能开关
  is_active?: boolean;
  enable_keyword_filter?: boolean;
  enable_regex_replace?: boolean;
  
  // 客户端选择
  client_id?: string;
  client_type?: 'user' | 'bot';
  
  // 消息类型支持
  enable_text?: boolean;
  enable_media?: boolean;
  enable_photo?: boolean;
  enable_video?: boolean;
  enable_document?: boolean;
  enable_audio?: boolean;
  enable_voice?: boolean;
  enable_sticker?: boolean;
  enable_animation?: boolean;
  enable_webpage?: boolean;
  
  // 高级设置
  forward_delay?: number;
  enable_link_preview?: boolean;
  
  // 时间过滤设置
  time_filter_type?: 'after_start' | 'all_messages' | 'time_range' | 'from_time' | 'today_only';
  start_time?: string;
  end_time?: string;
  enable_deduplication?: boolean;
  dedup_time_window?: number;
  dedup_check_content?: boolean;
  dedup_check_media?: boolean;
  enable_sender_filter?: boolean;
  sender_filter_mode?: 'whitelist' | 'blacklist';
  sender_whitelist?: string | null;
  sender_blacklist?: string | null;
}

export interface UpdateRuleDto extends Partial<CreateRuleDto> {
}

export interface CreateKeywordDto {
  rule_id: number;
  keyword: string;
  is_blacklist?: boolean;
}

export interface CreateReplaceRuleDto {
  rule_id: number;
  name?: string;
  pattern: string;
  replacement: string;
  priority?: number;
  is_regex?: boolean;
  is_active?: boolean;
}

// 规则筛选器
export interface RuleFilters {
  search?: string;
  is_active?: boolean;
  source_chat?: string;
  page?: number;
  pageSize?: number;
}

// 客户端相关类型
export interface TelegramClient {
  client_id: string;
  client_type: 'user' | 'bot';
  running: boolean;
  connected: boolean;
  user_info?: {
    id?: number;
    username?: string;
    first_name?: string;
    last_name?: string;
    phone?: string;
    bot?: boolean;
  };
  monitored_chats: string[];
  thread_alive: boolean;
  auto_start?: boolean;
}

export interface ClientsResponse {
  success: boolean;
  clients: Record<string, TelegramClient>;
  message?: string;
}
