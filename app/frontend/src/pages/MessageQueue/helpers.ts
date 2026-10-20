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

export const isImageOrVideoFile = (file: { name: string; type?: string }): boolean => Boolean(
  mediaPreviewKind({ name: file.name, mime_type: file.type } as MessageResource),
);

export const limitMediaFiles = <T extends { name: string; type?: string }>(
  retainedMediaCount: number,
  files: T[],
  maxMediaCount = 9,
): { accepted: T[]; rejectedCount: number } => {
  let mediaCount = retainedMediaCount;
  let rejectedCount = 0;
  const accepted = files.filter(file => {
    if (!isImageOrVideoFile(file)) return true;
    if (mediaCount >= maxMediaCount) {
      rejectedCount += 1;
      return false;
    }
    mediaCount += 1;
    return true;
  });
  return { accepted, rejectedCount };
};

export const albumTilePlacement = (
  count: number,
  index: number,
): { gridColumn: string; gridRow?: string } => {
  if (count <= 1) return { gridColumn: 'span 12' };
  if (count === 2) return { gridColumn: 'span 6' };
  if (count === 3) {
    return index === 0
      ? { gridColumn: 'span 8', gridRow: 'span 2' }
      : { gridColumn: 'span 4' };
  }
  if (count === 4) return { gridColumn: 'span 6' };
  if (count === 5) return { gridColumn: index < 2 ? 'span 6' : 'span 4' };
  if (count === 6) return { gridColumn: 'span 4' };
  if (count === 7) return { gridColumn: index < 3 ? 'span 4' : 'span 3' };
  if (count === 8) return { gridColumn: 'span 3' };
  return { gridColumn: 'span 4' };
};
