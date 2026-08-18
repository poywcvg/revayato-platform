/**
 * Formatting helpers for Persian (fa-IR) UI. Uses Hermes Intl on Android.
 */

const faNumber = new Intl.NumberFormat('fa-IR');

export function toFa(value: number): string {
  if (!Number.isFinite(value)) {return '۰';}
  return faNumber.format(value);
}

export function toFaOptional(value: number | null | undefined): string {
  return value ? toFa(value) : '';
}

/** 90 → «۱ ساعت و ۳۰ دقیقه». */
export function formatDuration(minutes: number): string {
  if (!minutes || minutes <= 0) {return '';}
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) {return `${toFa(m)} دقیقه`;}
  if (m === 0) {return `${toFa(h)} ساعت`;}
  return `${toFa(h)} ساعت و ${toFa(m)} دقیقه`;
}

/** 7350 → «۲:۰۲:۳۰» (Persian digits). Time can exceed an hour. */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(sec).padStart(2, '0');
  if (h > 0) {
    return `${toFa(h)}:${toFa(Number(mm))}:${toFa(Number(ss))}`;
  }
  return `${toFa(Number(mm))}:${toFa(Number(ss))}`;
}

/** Age rating token from backend strings like '18+' / '15+' / 'P'. */
export function ageRatingToken(age: string | null | undefined): string {
  if (!age) {return '';}
  const digits = String(age).match(/\d+/)?.[0];
  if (!digits) {return '';}
  return `${digits}+`;
}
