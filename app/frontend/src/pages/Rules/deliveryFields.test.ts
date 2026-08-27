import { describe, expect, it } from 'vitest';

import { buildRuleDeliveryFields } from './deliveryFields';

describe('rule delivery fields', () => {
  it('defaults imported-compatible rules to automatic delivery', () => {
    expect(buildRuleDeliveryFields({ destination_ids: [1, 2] })).toEqual({
      delivery_mode: 'auto',
      destination_ids: [1, 2],
    });
  });

  it('preserves manual review and selected destinations', () => {
    expect(buildRuleDeliveryFields({ delivery_mode: 'manual', destination_ids: [3] })).toEqual({
      delivery_mode: 'manual',
      destination_ids: [3],
    });
  });
});
