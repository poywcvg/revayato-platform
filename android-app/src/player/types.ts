/**
 * Player contract — screens depend on these types, and only `VideoSurface`
 * touches react-native-video.
 */
import type {AppSubtitleTrack} from '../data/catalogAdapter';

export type PlaybackKind = 'movie' | 'episode';

export interface PlayableSource {
  uri: string; // absolute HLS or progressive mp4/mkv URL
  posterURL: string;
  title: string;
  kind: PlaybackKind;
  subtitleTracks: AppSubtitleTrack[];
  startAtSeconds?: number;
}

export interface PlayerSnapshot {
  isPlaying: boolean;
  positionSeconds: number;
  durationSeconds: number;
  playbackRate: number;
}

export interface VideoController {
  play(): void;
  pause(): void;
  seek(seconds: number): void;
  setRate(rate: number): void;
  getSnapshot(): PlayerSnapshot;
}
