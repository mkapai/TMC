import type { DeliveryTargetInput, DeliveryTargetType } from '../../types/delivery';

export interface DeliveryTargetFormValues {
  name: string;
  target_type: DeliveryTargetType;
  is_active: boolean;
  client_id?: string;
  chat_id?: string;
  url?: string;
  hmac_secret?: string;
  headers?: Array<{ key?: string; value?: string }>;
}

export const buildDeliveryTargetInput = (
  values: DeliveryTargetFormValues,
): DeliveryTargetInput => {
  const config = values.target_type === 'telegram'
    ? { client_id: values.client_id, chat_id: values.chat_id }
    : {
        url: values.url,
        hmac_secret: values.hmac_secret,
        headers: Object.fromEntries(
          (values.headers || [])
            .filter(item => item?.key)
            .map(item => [item.key!.trim(), item.value || '']),
        ),
      };
  return {
    name: values.name,
    target_type: values.target_type,
    config,
    is_active: values.is_active,
  };
};
