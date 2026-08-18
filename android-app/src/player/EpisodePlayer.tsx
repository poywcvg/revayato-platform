import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {StyleSheet, View} from 'react-native';
import type {RouteProp} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {getSeries} from '../api/endpoints';
import {adaptSeriesDetail, AppMedia, AppEpisode} from '../data/catalogAdapter';
import {VideoSurface} from './VideoSurface';
import {useVideoController} from './useVideoController';
import {
  useResumeProgress,
  clampResume,
  resumeKey,
  loadResume,
  clearResume,
} from './useResumeProgress';
import {PlayerShell, lockLandscape, releaseOrientation} from './PlayerShell';
import type {PlayableSource} from './types';
import {AppText} from '../components/ui/AppText';
import {PressableFocus} from '../components/ui/PressableFocus';
import {colors, spacing} from '../theme';
import {t} from '../data/translations';
import {firstPlayable, isPlayableUrl} from '../utils/url';
import type {RootStackParamList} from '../navigation/types';

interface EpisodePlayerProps {
  route: RouteProp<RootStackParamList, 'SeriesPlayer'>;
  navigation: NativeStackNavigationProp<RootStackParamList>;
}

/**
 * Series episode playback. The backend detail payload lists only playable
 * episodes; switching episodes never refetches (detail stays cached). Moving
 * to the next episode happens automatically on end. Resume is per-episode.
 */
export function EpisodePlayer({route, navigation}: EpisodePlayerProps) {
  const {slug, episodeId} = route.params;
  const {data} = useApiGet(
    `series:${slug}`,
    () => getSeries(slug).then(adaptSeriesDetail),
    {ttlMs: 10 * 60 * 1000},
  );

  const series: AppMedia | null = data ?? null;
  const allEpisodes = useMemo<AppEpisode[]>(
    () => (series?.seasons ?? []).flatMap(s => s.episodes),
    [series],
  );

  const [episodeIndex, setEpisodeIndex] = useState(() => {
    if (!episodeId || !allEpisodes.length) {return 0;}
    const idx = allEpisodes.findIndex(e => e.id === episodeId);
    return idx === -1 ? 0 : idx;
  });

  const [fallbackUri, setFallbackUri] = useState<string | null>(null);
  const resumeLoaded = useRef(false);

  const vc = useVideoController();
  const {controller, surfaceRef} = vc;

  useEffect(() => {
    lockLandscape();
    return () => releaseOrientation();
  }, []);

  const episode: AppEpisode | null = allEpisodes[episodeIndex] ?? null;

  const playableUri =
    fallbackUri ?? firstPlayable(episode?.hls_url, series?.download_links?.[0]?.url);

  // Resume key is per-episode; the hook tracks the live key in a ref.
  const resumeKeyFor = series
    ? resumeKey('episode', series.id, episode?.id)
    : '';
  const resumeHook = useResumeProgress(resumeKeyFor);
  const resumeHookRef = useRef(resumeHook);
  resumeHookRef.current = resumeHook;

  const onSurfaceLoad = useCallback(
    ({duration}: {duration: number}) => {
      vc.onLoad({duration});
      if (episode && duration > 0 && !resumeLoaded.current) {
        resumeLoaded.current = true;
        void loadResume(resumeKeyFor).then(entry => {
          const at = clampResume(entry, duration);
          if (at > 0) {vc.controller.seek(at);}
        });
      }
    },
    [vc, episode, resumeKeyFor],
  );

  const onSurfaceProgress = useCallback(
    ({positionSeconds, durationSeconds}: {positionSeconds: number; durationSeconds: number}) => {
      vc.onProgress({positionSeconds, durationSeconds});
      if (durationSeconds > 0) {
        resumeHookRef.current.record(positionSeconds, durationSeconds);
      }
    },
    [vc],
  );

  const goNext = useCallback(() => {
    if (episodeIndex + 1 < allEpisodes.length) {
      resumeLoaded.current = false;
      setFallbackUri(null);
      setEpisodeIndex(episodeIndex + 1);
    } else {
      vc.controller.pause();
    }
  }, [episodeIndex, allEpisodes.length, vc]);

  const onSurfaceEnd = useCallback(() => {
    if (resumeKeyFor) {void clearResume(resumeKeyFor);}
    goNext();
  }, [resumeKeyFor, goNext]);

  const onSurfaceError = useCallback(() => {
    vc.onError();
    if (fallbackUri || !series) {return;}
    const mp4 = series.download_links.find(
      l => isPlayableUrl(l.url) && /\.mp4/i.test(l.url),
    );
    if (mp4) {setFallbackUri(mp4.url);}
  }, [vc, fallbackUri, series]);

  const playable: PlayableSource | null =
    playableUri && episode
      ? {
          uri: playableUri,
          posterURL: episode.poster_url || series?.poster_url || '',
          title: `${series?.title ?? ''} — ${episode.title}`,
          kind: 'episode',
          subtitleTracks: episode.subtitle_tracks,
        }
      : null;

  if (!series) {
    return (
      <View style={styles.center}>
        <AppText color={colors.textMuted}>{t.loading}</AppText>
      </View>
    );
  }

  if (!episode || !playable) {
    return (
      <View style={styles.center}>
        <AppText color={colors.textSecondary}>{t.notAvailable}</AppText>
        {series.download_links.length ? (
          <View style={{marginTop: spacing.lg}}>
            <AppText color={colors.brand} weight="bold">
              {t.downloads}
            </AppText>
            {series.download_links.map((l, i) => (
              <AppText key={i} color={colors.textSecondary} size="sm">
                {l.label}
              </AppText>
            ))}
          </View>
        ) : null}
        <PressableFocus
          onPress={() => navigation.goBack()}
          style={styles.backBtn}
          tvPreferredFocus>
          <AppText color={colors.bgMain}>{t.retry}</AppText>
        </PressableFocus>
      </View>
    );
  }

  return (
    <PlayerShell
      title={playable.title}
      isPlaying={vc.state.isPlaying}
      currentTime={vc.state.currentTime}
      duration={vc.state.duration}
      isBuffering={vc.state.isBuffering}
      controller={controller}
      onBack={() => navigation.goBack()}>
      <VideoSurface
        ref={surfaceRef}
        source={playable}
        paused={false}
        onLoad={onSurfaceLoad}
        onProgress={onSurfaceProgress}
        onEnd={onSurfaceEnd}
        onError={onSurfaceError}
        onBuffer={vc.onBuffer}
        onPlaybackStateChange={vc.onPlaybackStateChange}
      />
    </PlayerShell>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.bgMain,
    padding: spacing.xl,
  },
  backBtn: {
    marginTop: spacing.lg,
    backgroundColor: colors.brandBright,
    borderRadius: 999,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
  },
});
