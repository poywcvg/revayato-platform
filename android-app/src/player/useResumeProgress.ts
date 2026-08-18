import {useEffect, useRef} from 'react';
import {AppState} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * Resume-position helpers backed by AsyncStorage.
 * Key: `revayato:resume:v1:<movie|series>:<id>[:episodeId]`.
 */
const PREFIX = 'revayato:resume:v1';

interface ResumeEntry {
  positionSeconds: number;
  durationSeconds: number;
  updatedAt: number;
}

export function resumeKey(
  kind: 'movie' | 'episode',
  mediaId: number,
  episodeId?: number,
): string {
  const base = `${PREFIX}:${kind}:${mediaId}`;
  return episodeId ? `${base}:ep${episodeId}` : base;
}

export async function loadResume(key: string): Promise<ResumeEntry | null> {
  const raw = await AsyncStorage.getItem(key).catch(() => null);
  if (!raw) {return null;}
  try {
    const parsed = JSON.parse(raw) as ResumeEntry;
    if (!Number.isFinite(parsed.positionSeconds)) {return null;}
    return parsed;
  } catch {
    return null;
  }
}

/** Clamp to within the last `tailSeconds` of the video so resume is useful. */
export function clampResume(
  entry: ResumeEntry | null,
  durationSeconds: number,
  tailSeconds = 90,
): number {
  if (!entry || entry.positionSeconds <= 0) {return 0;}
  if (entry.positionSeconds > durationSeconds - tailSeconds) {return 0;}
  return Math.min(entry.positionSeconds, durationSeconds * 0.95);
}

export async function saveResume(
  key: string,
  positionSeconds: number,
  durationSeconds: number,
): Promise<void> {
  const entry: ResumeEntry = {
    positionSeconds,
    durationSeconds,
    updatedAt: Date.now(),
  };
  await AsyncStorage.setItem(key, JSON.stringify(entry)).catch(() => undefined);
}

export async function clearResume(key: string): Promise<void> {
  await AsyncStorage.removeItem(key).catch(() => undefined);
}

/**
 * Hook that throttles resume writes (~10s) and flushes on background/unmount.
 * Returns {record, flush} — record() stores without triggering re-renders.
 */
export function useResumeProgress(key: string) {
  const lastWrite = useRef(0);
  const posRef = useRef(0);
  const durRef = useRef(0);
  const keyRef = useRef(key);
  keyRef.current = key;

  const flush = () => {
    const position = posRef.current;
    const duration = durRef.current;
    if (position > 0 && duration > 0) {
      void saveResume(keyRef.current, position, duration);
    }
  };

  useEffect(() => {
    const sub = AppState.addEventListener('change', state => {
      if (state !== 'active') {flush();}
    });
    return () => {
      flush();
      sub.remove();
    };

  }, []);

  return {
    record(
      positionSeconds: number,
      durationSeconds: number,
      now = Date.now(),
    ): void {
      posRef.current = positionSeconds;
      durRef.current = durationSeconds;
      if (now - lastWrite.current >= 10_000) {
        lastWrite.current = now;
        flush();
      }
    },
    flush,
  };
}
