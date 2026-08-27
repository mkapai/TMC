import type { DeliveryTarget, MessageResource, QueuedMessage } from '../../types/delivery';

export const isMessageEditable = (message?: QueuedMessage): boolean => Boolean(
  message && (typeof message.editable === 'boolean'
    ? message.editable
    : ['pending_review', 'queued', 'rejected'].includes(message.status)
      && !(message.deliveries || []).some(job => job.attempt_count > 0 || job.status === 'sent')),
);

export const messageTargetOptions = (
  targets: DeliveryTarget[],
  availableTargetIds: number[],
) => targets
  .filter(target => target.is_active && availableTargetIds.includes(target.id))
  .map(target => ({ value: target.id, label: `${target.name} (${target.target_type})` }));

export const mediaPreviewKind = (resource: MessageResource): 'image' | 'video' | undefined => {
  const mimeType = resource.mime_type?.toLowerCase() || '';
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType.startsWith('video/')) return 'video';

  const extension = resource.name.toLowerCase().split('.').pop();
  if (extension && ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(extension)) return 'image';
  if (extension && ['mp4', 'webm', 'mov', 'm4v', 'ogv'].includes(extension)) return 'video';
  return undefined;
};
