import {useCallback, useEffect, useRef, useState} from 'react';
import type {VideoSurfaceHandle} from './VideoSurface';
import type {PlayerSnapshot} from './types';

/**
 * Bridges the imperative VideoSurfaceHandle into state + a stable method set.
 * Screens consume `controller` (play/pause/seek/setRate/getSnapshot) and the
 * `state` (isPlaying / currentTime / duration / isBuffering / error).
 */
export function useVideoController() {
  const surfaceRef = useRef<VideoSurfaceHandle | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isBuffering, setIsBuffering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const controller = useRef({
    play() {
      surfaceRef.current?.play();
    },
    pause() {
      surfaceRef.current?.pause();
    },
    seek(seconds: number) {
      surfaceRef.current?.seek(seconds);
      setCurrentTime(seconds);
    },
    setRate(rate: number) {
      surfaceRef.current?.setRate(rate);
    },
    getSnapshot(): PlayerSnapshot {
      return (
        surfaceRef.current?.getSnapshot() ?? {
          isPlaying: false,
          positionSeconds: 0,
          durationSeconds: 0,
          playbackRate: 1,
        }
      );
    },
  }).current;

  const onLoad = useCallback(({duration: d}: {duration: number}) => {
    setDuration(d);
    setError(null);
  }, []);

  const onProgress = useCallback(
    ({positionSeconds, durationSeconds}: {positionSeconds: number; durationSeconds: number}) => {
      setCurrentTime(positionSeconds);
      if (durationSeconds > 0) {setDuration(durationSeconds);}
    },
    [],
  );

  const onBuffer = useCallback(({isBuffering: buffering}: {isBuffering: boolean}) => {
    setIsBuffering(buffering);
  }, []);

  const onError = useCallback(() => {
    setError('پخش ناموفق بود');
    setIsPlaying(false);
  }, []);

  const onPlaybackStateChange = useCallback((playing: boolean) => setIsPlaying(playing), []);

  useEffect(() => {
    const surface = surfaceRef.current;
    return () => surface?.pause();
  }, []);

  return {
    surfaceRef,
    controller,
    state: {isPlaying, currentTime, duration, isBuffering, error},
    onLoad,
    onProgress,
    onBuffer,
    onError,
    onPlaybackStateChange,
  };
}
