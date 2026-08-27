export const buildRuleDeliveryFields = (values: {
  delivery_mode?: 'auto' | 'manual';
  destination_ids?: number[];
}) => ({
  delivery_mode: values.delivery_mode || 'auto' as const,
  destination_ids: values.destination_ids || [],
});
