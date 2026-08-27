import { describe, expect, it } from 'vitest';

import { buildDeliveryTargetInput } from './helpers';

describe('delivery target form', () => {
  it('builds Telegram configuration', () => {
    expect(buildDeliveryTargetInput({
      name: 'Archive',
      target_type: 'telegram',
      is_active: true,
      client_id: 'account-a',
      chat_id: '-1001',
    })).toEqual({
      name: 'Archive',
      target_type: 'telegram',
      is_active: true,
      config: { client_id: 'account-a', chat_id: '-1001' },
    });
  });

  it('builds Webhook headers and secret configuration', () => {
    expect(buildDeliveryTargetInput({
      name: 'Project',
      target_type: 'webhook',
      is_active: true,
      url: 'https://example.test/events',
      hmac_secret: 'secret',
      headers: [{ key: ' X-Project-Key ', value: 'value' }, { key: '', value: 'ignored' }],
    }).config).toEqual({
      url: 'https://example.test/events',
      hmac_secret: 'secret',
      headers: { 'X-Project-Key': 'value' },
    });
  });
});
