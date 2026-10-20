import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  getBlob: vi.fn(),
  postForm: vi.fn(),
}));

vi.mock('../api', () => ({ api }));

import { deliveryTargetsApi } from '../deliveryTargets';
import { messagesApi } from '../messages';

describe('delivery workflow API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('edits and reviews a queued message', async () => {
    api.patch.mockResolvedValue({ success: true });
    api.post.mockResolvedValue({ success: true });
    await messagesApi.update(7, 'edited', [2, 3]);
    await messagesApi.update(9, 'push now', [2], true);
    await messagesApi.approve(7, [2]);
    await messagesApi.reject(8);
    expect(api.patch).toHaveBeenCalledWith('/api/messages/7', {
      text: 'edited',
      target_ids: [2, 3],
      push: false,
    });
    expect(api.patch).toHaveBeenCalledWith('/api/messages/9', {
      text: 'push now',
      target_ids: [2],
      push: true,
    });
    expect(api.post).toHaveBeenCalledWith('/api/messages/7/approve', { target_ids: [2] });
    expect(api.post).toHaveBeenCalledWith('/api/messages/8/reject');
  });

  it('loads a protected media preview', async () => {
    const blob = new Blob(['image'], { type: 'image/png' });
    api.getBlob.mockResolvedValue(blob);
    await expect(messagesApi.preview('/api/messages/resources/11/preview')).resolves.toBe(blob);
    expect(api.getBlob).toHaveBeenCalledWith('/api/messages/resources/11/preview');
  });

  it('submits resource edits as multipart form data', async () => {
    const file = new File(['image'], 'added.jpg', { type: 'image/jpeg' });
    api.postForm.mockResolvedValue({ success: true });

    await messagesApi.edit(7, {
      text: 'edited',
      target_ids: [2],
      remove_resource_ids: [11],
      files: [file],
      push: false,
    });

    expect(api.postForm).toHaveBeenCalledWith('/api/messages/7/edit', expect.any(FormData));
    const form = api.postForm.mock.calls[0][1] as FormData;
    expect(form.get('text')).toBe('edited');
    expect(form.get('target_ids')).toBe('[2]');
    expect(form.get('remove_resource_ids')).toBe('[11]');
    const submittedFile = form.get('files') as File;
    expect(submittedFile.name).toBe('added.jpg');
    expect(submittedFile.type).toBe('image/jpeg');
    expect(submittedFile.size).toBe(file.size);
  });

  it('submits batch operations', async () => {
    api.post.mockResolvedValue({ success: true, succeeded: [1, 2], failed: [] });
    await messagesApi.bulk([1, 2], 'retry');
    expect(api.post).toHaveBeenCalledWith('/api/messages/bulk/action', {
      message_ids: [1, 2],
      action: 'retry',
    });
  });

  it('creates and tests a delivery target', async () => {
    const input = {
      name: 'Project',
      target_type: 'webhook' as const,
      config: { url: 'https://example.test/events' },
      is_active: true,
    };
    api.post
      .mockResolvedValueOnce({ success: true, target: { id: 4 } })
      .mockResolvedValueOnce({ success: true, message: 'ok' });
    await deliveryTargetsApi.create(input);
    await deliveryTargetsApi.test(4);
    expect(api.post).toHaveBeenNthCalledWith(1, '/api/delivery-targets', input);
    expect(api.post).toHaveBeenNthCalledWith(2, '/api/delivery-targets/4/test');
  });
});
