import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Orientation from 'react-native-orientation-locker';
import {colors, radius, spacing} from '../theme';
import {AppText} from '../components/ui/AppText';
import {formatClock} from '../utils/format';
import {IS_TV} from '../utils/platform';
import type {VideoController} from './types';

export function lockLandscape() {
  try {
    Orientation.lockToLandscape();
  } catch {
    /* orientation lib may be absent on TV */
  }
}

export function releaseOrientation() {
  try {
    Orientation.unlockAllOrientations();
  } catch {
    /* noop */
  }
}

interface PlayerShellProps {
  title: string;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  isBuffering: boolean;
  controller: VideoController;
  onBack?: () => void;
  children?: React.ReactNode;
}

/**
 * Overlay + controls shell around the video surface.
 * - Phone: tap toggles a fade overlay (play/pause, scrub bar, back). Fullscreen.
 * - TV: overlay sleeps; any DPAD wake (~4s); DPAD actions drive the controller.
 */
export function PlayerShell({
  title,
  isPlaying,
  currentTime,
  duration,
  isBuffering,
  controller,
  onBack,
  children,
}: PlayerShellProps) {
  const [overlayVisible, setOverlayVisible] = useState(!IS_TV);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showOverlay = useCallback(() => {
    setOverlayVisible(true);
    if (hideTimer.current) {clearTimeout(hideTimer.current);}
    hideTimer.current = setTimeout(() => setOverlayVisible(false), 4000);
  }, []);

  useEffect(() => {
    if (!IS_TV) {return;}
    showOverlay();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => {
    if (hideTimer.current) {clearTimeout(hideTimer.current);}
  }, []);

  const togglePlay = () => {
    if (isPlaying) {controller.pause();}
    else {controller.play();}
    showOverlay();
  };

  const seekBy = (delta: number) => controller.seek(Math.max(0, currentTime + delta));
  const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;

  return (
    <View style={styles.root} onTouchStart={IS_TV ? undefined : showOverlay}>
      {children}

      {isBuffering ? (
        <View style={styles.loadingAbs} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.brandBright} />
        </View>
      ) : null}

      {overlayVisible ? (
        <View style={styles.overlay}>
          <View style={styles.topBar}>
            <AppText size="sm" color={colors.textPrimary} numberOfLines={1} weight="medium">
              {title}
            </AppText>
            <Pressable
              onPress={onBack}
              style={[styles.iconBtn, {alignSelf: 'flex-start'}]}
              hitSlop={{top: 10, bottom: 10, left: 10, right: 10}}>
              <Text style={styles.iconText}>✕</Text>
            </Pressable>
          </View>

          <View style={styles.centerRow}>
            <Pressable onPress={seekBy.bind(null, -10)} style={styles.iconBtn}>
              <Text style={styles.iconText}>↺</Text>
            </Pressable>
            <Pressable onPress={togglePlay} style={styles.playBtn} hasTVPreferredFocus={IS_TV}>
              <Text style={styles.playIcon}>{isPlaying ? '❚❚' : '▶'}</Text>
            </Pressable>
            <Pressable onPress={seekBy.bind(null, 10)} style={styles.iconBtn}>
              <Text style={styles.iconText}>↻</Text>
            </Pressable>
          </View>

          <View style={styles.bottomBar}>
            <AppText size="xs" color={colors.textMuted}>
              {formatClock(currentTime)}
            </AppText>
            <View style={styles.scrubTrack}>
              <View style={[styles.scrubFill, {width: `${progress * 100}%`}]} />
            </View>
            <AppText size="xs" color={colors.textMuted}>
              {formatClock(Math.max(0, duration))}
            </AppText>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#000',
  },
  loadingAbs: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.overlay,
    justifyContent: 'space-between',
    padding: spacing.lg,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  centerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xl,
  },
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.full,
    backgroundColor: 'rgba(0,0,0,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconText: {
    color: colors.textPrimary,
    fontSize: 20,
  },
  playBtn: {
    width: 72,
    height: 72,
    borderRadius: radius.full,
    backgroundColor: colors.brandBright,
    alignItems: 'center',
    justifyContent: 'center',
  },
  playIcon: {
    color: colors.bgMain,
    fontSize: 28,
    fontWeight: '700',
  },
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  scrubTrack: {
    flex: 1,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.25)',
    overflow: 'hidden',
  },
  scrubFill: {
    height: '100%',
    backgroundColor: colors.brandBright,
  },
});
