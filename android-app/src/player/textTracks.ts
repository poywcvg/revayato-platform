/**
 * Subtitle mapping: rnv v6 wants textTracks on the source object with an
 * ISO 639-1 `language` + `TextTrackType`. Default track is chosen via
 * `selectedTextTrack` (declared default, else first Persian).
 */
import {TextTrackType} from 'react-native-video';
import type {ISO639_1} from 'react-native-video';
import type {AppSubtitleTrack} from '../data/catalogAdapter';

export interface VideoTextTrack {
  title: string;
  language: ISO639_1;
  type: TextTrackType;
  uri: string;
}

export function toVideoTextTracks(tracks: AppSubtitleTrack[]): VideoTextTrack[] {
  return tracks
    .filter(track => track.src)
    .map(track => ({
      title: track.label || track.language,
      language: langCode(track.language),
      type: TextTrackType.VTT,
      uri: track.src,
    }));
}

/**
 * react-native-video selectedTextTrack descriptor — index of the declared
 * default (or first Persian) track, else 0 when none.
 */
export function defaultTextTrackDescriptor(tracks: AppSubtitleTrack[]): {
  type: 'index';
  value: number;
} {
  if (!tracks.length) {return {type: 'index', value: 0};}
  const declared = tracks.findIndex(t => t.default);
  if (declared !== -1) {return {type: 'index', value: declared};}
  const persian = tracks.findIndex(t => /fa|per|فارسی/i.test(t.language));
  return {type: 'index', value: persian === -1 ? 0 : persian};
}

/** Map backend language labels to ISO 639-1; default `fa` for RTL-first UIs. */
function langCode(language: string): ISO639_1 {
  const input = language.toLowerCase().trim();
  if (/^fa$/i.test(input) || /persian|farsi|فارسی/i.test(input)) {return 'fa';}
  if (/^en$/i.test(input) || /english/i.test(input)) {return 'en';}
  if (/^[a-z]{2}$/.test(input)) {return input as ISO639_1;}
  return 'fa';
}
