import { describe, expect, it } from 'vitest';

import type { DeliveryTarget, QueuedMessage } from '../../types/delivery';
import {
  albumTilePlacement, isImageOrVideoFile, isMessageEditable, limitMediaFiles, mediaPreviewKind,
  messageTargetOptions,
} from './helpers';

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

  it('limits combined image and video selections while retaining other files', () => {
    const files = [
      { name: 'one.jpg', type: 'image/jpeg' },
      { name: 'two.mp4', type: 'video/mp4' },
      { name: 'notes.pdf', type: 'application/pdf' },
    ];
    expect(isImageOrVideoFile(files[0])).toBe(true);
    expect(isImageOrVideoFile(files[2])).toBe(false);
    expect(limitMediaFiles(8, files)).toEqual({
      accepted: [files[0], files[2]],
      rejectedCount: 1,
    });
  });

  it('uses telegram-style album mosaics without incomplete rows', () => {
    expect([0, 1, 2].map(index => albumTilePlacement(3, index))).toEqual([
      { gridColumn: 'span 8', gridRow: 'span 2' },
      { gridColumn: 'span 4' },
      { gridColumn: 'span 4' },
    ]);
    expect([0, 1, 2, 3, 4].map(index => albumTilePlacement(5, index))).toEqual([
      { gridColumn: 'span 6' },
      { gridColumn: 'span 6' },
      { gridColumn: 'span 4' },
      { gridColumn: 'span 4' },
      { gridColumn: 'span 4' },
    ]);
    expect([0, 1, 2, 3, 4, 5, 6].map(index => albumTilePlacement(7, index))).toEqual([
      { gridColumn: 'span 4' },
      { gridColumn: 'span 4' },
      { gridColumn: 'span 4' },
      { gridColumn: 'span 3' },
      { gridColumn: 'span 3' },
      { gridColumn: 'span 3' },
      { gridColumn: 'span 3' },
    ]);
  });
});
