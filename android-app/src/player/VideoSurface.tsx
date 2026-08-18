import React, {forwardRef, useImperativeHandle, useRef, useState} from 'react';
import Video, {
  OnBufferData,
  OnLoadData,
  OnProgressData,
  OnVideoErrorData,
  VideoRef,
} from 'react-native-video';
import type {PlayableSource, PlayerSnapshot} from './types';
import {defaultTextTrackDescriptor, toVideoTextTracks} from './textTracks';

export interface VideoSurfaceHandle {
  play(): void;
  pause(): void;
  seek(seconds: number): void;
  setRate(rate: number): void;
  getSnapshot(): PlayerSnapshot;
}

export interface VideoSurfaceProps {
  source: PlayableSource;
  paused?: boolean;
  rate?: number;
  onLoad?: (data: {duration: number}) => void;
  onProgress?: (data: {positionSeconds: number; durationSeconds: number}) => void;
  onEnd?: () => void;
  onError?: (error: OnVideoErrorData) => void;
  onBuffer?: (status: OnBufferData) => void;
  onPlaybackStateChange?: (isPlaying: boolean) => void;
  onReadyForDisplay?: () => void;
  style?: object;
}

/**
 * The ONLY module that imports react-native-video. Everything above the player
 * talks to this surface through the `VideoSurfaceHandle` (imperative) API.
 *
 * react-native-video v6 expects textTracks on the `source` object, and audio
 * rate changes flow through a `rate` bound via React (not a ref method).
 */
export const VideoSurface = forwardRef<VideoSurfaceHandle, VideoSurfaceProps>(
  function VideoSurface(
    {
      source,
      paused = false,
      rate = 1,
      onLoad,
      onProgress,
      onEnd,
      onError,
      onBuffer,
      onPlaybackStateChange,
      onReadyForDisplay,
      style,
    },
    ref,
  ) {
    const videoRef = useRef<VideoRef | null>(null);
    // rnv v6 drives `rate` through the React prop, so the imperative handle
    // stores into state; the prop binds to native.
    const [effectiveRate, setEffectiveRate] = useState(rate);
    const snapshot = useRef<PlayerSnapshot>({
      isPlaying: !paused,
      positionSeconds: 0,
      durationSeconds: 0,
      playbackRate: rate,
    });

    useImperativeHandle(ref, () => {
      const video = () => videoRef.current;
      return {
        play() {
          video()?.resume();
          snapshot.current.isPlaying = true;
          onPlaybackStateChange?.(true);
        },
        pause() {
          video()?.pause();
          snapshot.current.isPlaying = false;
          onPlaybackStateChange?.(false);
        },
        seek(seconds: number) {
          video()?.seek(seconds);
          snapshot.current.positionSeconds = seconds;
        },
        setRate(r: number) {
          setEffectiveRate(r);
          snapshot.current.playbackRate = r;
        },
        getSnapshot(): PlayerSnapshot {
          return {...snapshot.current};
        },
      };
    });

    // rnv v6: textTracks + selectedTextTrack belong to the source object.
    const textTracks = toVideoTextTracks(source.subtitleTracks);

    return (
      <Video
        ref={videoRef}
        source={{
          uri: source.uri,
          ...(textTracks.length ? {textTracks} : {}),
          ...(textTracks.length
            ? {selectedTextTrack: defaultTextTrackDescriptor(source.subtitleTracks)}
            : {}),
        }}
        poster={source.posterURL || undefined}
        posterResizeMode="cover"
        resizeMode="contain"
        paused={paused}
        rate={effectiveRate}
        repeat={false}
        playInBackground={false}
        playWhenInactive={false}
        progressUpdateInterval={500}
        onLoad={(data: OnLoadData) => {
          snapshot.current.durationSeconds = data.duration;
          onLoad?.({duration: data.duration});
        }}
        onProgress={(data: OnProgressData) => {
          snapshot.current.positionSeconds = data.currentTime;
          onProgress?.({
            positionSeconds: data.currentTime,
            durationSeconds: snapshot.current.durationSeconds,
          });
        }}
        onEnd={() => {
          snapshot.current.positionSeconds = snapshot.current.durationSeconds;
          onEnd?.();
        }}
        onError={(error: OnVideoErrorData) => onError?.(error)}
        onBuffer={(info: OnBufferData) => onBuffer?.(info)}
        onPlaybackRateChange={({playbackRate}) => {
          snapshot.current.isPlaying = playbackRate > 0;
          onPlaybackStateChange?.(playbackRate > 0);
        }}
        onReadyForDisplay={onReadyForDisplay}
        onAudioBecomingNoisy={() => {
          snapshot.current.isPlaying = false;
          onPlaybackStateChange?.(false);
        }}
        style={[{width: '100%', height: '100%'}, style]}
      />
    );
  },
);

