export type DeliveryTargetType = 'telegram' | 'webhook';

export interface DeliveryTarget {
  id: number;
  name: string;
  target_type: DeliveryTargetType;
  config: {
    client_id?: string;
    chat_id?: string;
    chat_name?: string;
    url?: string;
    headers?: Record<string, string>;
    has_hmac_secret?: boolean;
  };
  is_active: boolean;
  rule_count: number;
  created_at: string;
  updated_at: string;
}

export interface DeliveryTargetInput {
  name: string;
  target_type: DeliveryTargetType;
  config: Record<string, unknown>;
  is_active: boolean;
}

export type QueueMessageStatus =
  | 'ingesting' | 'ingest_failed' | 'pending_review' | 'queued' | 'sending'
  | 'partially_sent' | 'sent' | 'failed' | 'rejected';

export interface MessageResource {
  id: number;
  name: string;
  mime_type?: string;
  size: number;
  sha256: string;
  url: string;
  preview_url: string;
}

export interface DeliveryJob {
  id: number;
  delivery_id: string;
  target_id: number;
  target_name: string;
  target_type: DeliveryTargetType;
  status: string;
  attempt_count: number;
  next_retry_at?: string;
  last_error?: string;
  response_status?: number;
  response_body?: string;
  sent_at?: string;
}

export interface QueuedMessage {
  id: number;
  rule_id?: number;
  rule_name: string;
  client_id: string;
  source_chat_id: string;
  source_chat_name?: string;
  source_message_id: number;
  sender_id?: string;
  sender_username?: string;
  sender_name?: string;
  original_text?: string;
  processed_text?: string;
  message_type: string;
  delivery_mode: 'auto' | 'manual';
  selected_target_ids: number[];
  available_target_ids: number[];
  status: QueueMessageStatus;
  editable: boolean;
  error_message?: string;
  source_created_at?: string;
  created_at: string;
  updated_at: string;
  resources: MessageResource[];
  delivery_summary: Record<string, number>;
  deliveries?: DeliveryJob[];
}

export interface QueueStats {
  pending_review?: number;
  queued?: number;
  sending?: number;
  partially_sent?: number;
  sent?: number;
  failed?: number;
  ingest_failed?: number;
  today_sent: number;
  cache_bytes: number;
}
