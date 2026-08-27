import { describe, expect, it } from 'vitest';

import type { DeliveryTarget, QueuedMessage } from '../../types/delivery';
import { isMessageEditable, mediaPreviewKind, messageTargetOptions } from './helpers';

const baseMessage = {
  status: 'pending_review',
  deliveries: [],
} as unknown as QueuedMessage;

describe('message review helpers', () => {
  it('allows editing before delivery and locks after an attempt', () => {
    expect(isMessageEditable(baseMessage)).toBe(true);
    expect(isMessageEditable({
      ...baseMessage,
      deliveries: [{ attempt_count: 1, status: 'retry_wait' }],
    } as QueuedMessage)).toBe(false);
    expect(isMessageEditable({ ...baseMessage, editable: false } as QueuedMessage)).toBe(false);
    expect(isMessageEditable({ ...baseMessage, status: 'sent' })).toBe(false);
  });

  it('offers only active targets bound to the message rule', () => {
    const targets = [
      { id: 1, name: 'Telegram', target_type: 'telegram', is_active: true },
      { id: 2, name: 'Webhook', target_type: 'webhook', is_active: true },
      { id: 3, name: 'Disabled', target_type: 'webhook', is_active: false },
    ] as DeliveryTarget[];
    expect(messageTargetOptions(targets, [2, 3])).toEqual([
      { value: 2, label: 'Webhook (webhook)' },
    ]);
  });

  it('recognizes previewable images and videos by MIME type or extension', () => {
    expect(mediaPreviewKind({ name: 'photo.bin', mime_type: 'image/jpeg' } as never)).toBe('image');
    expect(mediaPreviewKind({ name: 'clip.MP4' } as never)).toBe('video');
    expect(mediaPreviewKind({ name: 'archive.zip', mime_type: 'application/zip' } as never)).toBeUndefined();
  });
});
