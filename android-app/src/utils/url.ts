/**
 * URL helpers. The backend already returns ABSOLUTE media URLs (poster,
 * backdrop, video_url, subtitle src) — this module only guards edge cases.
 */
import {API_BASE_URL} from '../config';

function apiOrigin(): string {
  try {
    return new URL(API_BASE_URL).origin;
  } catch {
    return '';
  }
}

/** Pass absolute + protocol-relative through; resolve /media/ against API origin. */
export function normalizeMediaUrl(url: string | null | undefined): string {
  if (!url) {return '';}
  const trimmed = url.trim();
  if (!trimmed) {return '';}
  if (trimmed.startsWith('https://') || trimmed.startsWith('http://')) {
    return trimmed;
  }
  if (trimmed.startsWith('//')) {
    return `https:${trimmed}`;
  }
  if (trimmed.startsWith('/')) {
    const origin = apiOrigin();
    return origin ? `${origin}${trimmed}` : trimmed;
  }
  return trimmed;
}

/** Poster placeholders used by the backend/media pipeline must render as blank. */
export function isPlaceholderPoster(url: string | null | undefined): boolean {
  if (!url) {return true;}
  return /placeholder-poster|poster-orbit/i.test(url);
}

export function isHlsUrl(url: string | null | undefined): boolean {
  return /\.m3u8(?:\?|$)/i.test(url ?? '');
}

/** A URL we are willing to hand to the video player. */
export function isPlayableUrl(url: string | null | undefined): boolean {
  if (!url) {return false;}
  const trimmed = url.trim();
  if (!/^https?:\/\//i.test(trimmed)) {return false;}
  // Reject non-video extensions and dead hosts (web playable-URL guard).
  if (/\.(?:vtt|srt|ass|aac|mp3|zip|jpg|jpeg|png|webp|txt)$/i.test(trimmed)) {
    return false;
  }
  return true;
}

/** First playable URL from a list, else ''. */
export function firstPlayable(...urls: Array<string | null | undefined>): string {
  for (const u of urls) {
    if (isPlayableUrl(u)) {return u as string;}
  }
  return '';
}
