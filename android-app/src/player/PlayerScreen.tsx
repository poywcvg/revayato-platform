import React, {useCallback, useEffect, useRef, useState} from 'react';
import {StyleSheet, View} from 'react-native';
import type {RouteProp} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {getMovie} from '../api/endpoints';
import {adaptDetail, type AppMedia} from '../data/catalogAdapter';
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

interface PlayerScreenProps {
  route: RouteProp<RootStackParamList, 'MoviePlayer'>;
  navigation: NativeStackNavigationProp<RootStackParamList>;
}

/**
 * Movie playback screen. Owns the landscape lock, resumes from the saved
 * position, and falls back to poster + download mirrors when the HLS stream
 * errors. Back pops the fullscreen modal.
 */
export function PlayerScreen({route, navigation}: PlayerScreenProps) {
  const {slug} = route.params;

  const {data} = useApiGet(
    `movie:${slug}`,
    () => getMovie(slug).then(adaptDetail),
    {ttlMs: 10 * 60 * 1000},
  );
  const media: AppMedia | null = data ?? null;

  const [fallbackUri, setFallbackUri] = useState<string | null>(null);
  const resumeLoaded = useRef(false);

  const key = media ? resumeKey('movie', media.id) : '';

  // The key '' before media loads is harmless: the hook tracks the current
  // `key` prop in a ref, so writes go to the real key once media resolves.
  const resumeHook = useResumeProgress(key);
  const resumeHookRef = useRef(resumeHook);
  resumeHookRef.current = resumeHook;

  const vc = useVideoController();
  const {controller, surfaceRef} = vc;

  // Orientation lock for phones; released on unmount.
  useEffect(() => {
    lockLandscape();
    return () => releaseOrientation();
  }, []);

  const playableUri =
    fallbackUri ?? firstPlayable(media?.hls_url, media?.download_links?.[0]?.url);

  const onSurfaceLoad = useCallback(
    ({duration}: {duration: number}) => {
      vc.onLoad({duration});
      if (media && key && !resumeLoaded.current && duration > 0) {
        resumeLoaded.current = true;
        void loadResume(key).then(entry => {
          const at = clampResume(entry, duration);
          if (at > 0) {vc.controller.seek(at);}
        });
      }
    },
    [vc, key, media],
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

  const onSurfaceEnd = useCallback(() => {
    vc.controller.pause();
    if (key) {void clearResume(key);}
  }, [vc, key]);

  const onSurfaceError = useCallback(() => {
    vc.onError();
    if (fallbackUri || !media) {return;}
    // HLS failure → offer the best direct download mirror.
    const mp4 = media.download_links.find(l => isPlayableUrl(l.url) && /\.mp4/i.test(l.url));
    if (mp4) {setFallbackUri(mp4.url);}
  }, [vc, fallbackUri, media]);

  const playable: PlayableSource | null = playableUri
    ? {
        uri: playableUri,
        posterURL: media?.poster_url ?? '',
        title: media?.title ?? '',
        kind: 'movie',
        subtitleTracks: media?.subtitle_tracks ?? [],
      }
    : null;

  if (!media) {
    return (
      <View style={styles.center}>
        <AppText color={colors.textMuted}>{t.loading}</AppText>
      </View>
    );
  }

  if (!playable) {
    return (
      <View style={styles.center}>
        <AppText color={colors.textSecondary}>{t.notAvailable}</AppText>
        {media.download_links.length ? (
          <View style={{marginTop: spacing.lg}}>
            <AppText color={colors.brand} weight="bold">
              {t.downloads}
            </AppText>
            {media.download_links.map((l, i) => (
              <AppText key={i} color={colors.textSecondary} size="sm">
                {l.label}
              </AppText>
            ))}
          </View>
        ) : null}
        <PressableFocus onPress={() => navigation.goBack()} style={styles.backBtn} tvPreferredFocus>
          <AppText color={colors.bgMain}>{t.retry}</AppText>
        </PressableFocus>
      </View>
    );
  }

  return (
    <PlayerShell
      title={media.title}
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
