export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || value < 0) {
    return "";
  }
  if (value < 10_000) {
    return String(value);
  }
  if (value < 100_000_000) {
    const scaled = value / 10_000;
    return `${scaled >= 100 ? Math.round(scaled) : scaled.toFixed(1).replace(/\.0$/, "")}万`;
  }
  const scaled = value / 100_000_000;
  return `${scaled.toFixed(1).replace(/\.0$/, "")}亿`;
}

export function formatRelativeTime(timestamp: number, now = Date.now() / 1000): string {
  if (!timestamp) {
    return "";
  }
  const seconds = Math.max(0, now - timestamp);
  if (seconds < 60) {
    return "刚刚";
  }
  if (seconds < 3_600) {
    return `${Math.floor(seconds / 60)}分钟前`;
  }
  if (seconds < 86_400) {
    return `${Math.floor(seconds / 3_600)}小时前`;
  }
  if (seconds < 7 * 86_400) {
    return `${Math.floor(seconds / 86_400)}天前`;
  }
  const date = new Date(timestamp * 1000);
  const month = date.getMonth() + 1;
  const day = date.getDate();
  if (date.getFullYear() === new Date(now * 1000).getFullYear()) {
    return `${month}月${day}日`;
  }
  return `${date.getFullYear()}年${month}月${day}日`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || !Number.isFinite(seconds) || seconds < 0) {
    return "0:00";
  }
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

export interface CaptionPart {
  text: string;
  tag?: string;
}

// A hashtag runs until whitespace or the next hashtag, matching how captions
// are typed on the source platforms.
const HASHTAG = /#[^\s#@，。！？、,.!?]+/gu;

export function splitCaption(caption: string): CaptionPart[] {
  const parts: CaptionPart[] = [];
  let cursor = 0;
  for (const match of caption.matchAll(HASHTAG)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      parts.push({ text: caption.slice(cursor, start) });
    }
    parts.push({ text: match[0], tag: match[0].slice(1) });
    cursor = start + match[0].length;
  }
  if (cursor < caption.length) {
    parts.push({ text: caption.slice(cursor) });
  }
  return parts;
}

export function initialOf(name: string): string {
  return Array.from(name.trim())[0]?.toUpperCase() ?? "?";
}
