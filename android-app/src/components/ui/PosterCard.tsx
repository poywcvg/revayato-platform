import React from 'react';
import {Image, StyleSheet, View} from 'react-native';
import {colors, radius, spacing} from '../../theme';
import type {AppMedia} from '../../data/catalogAdapter';
import {AppText} from './AppText';
import {PressableFocus} from './PressableFocus';

interface PosterCardProps {
  media: AppMedia;
  width?: number;
  title?: boolean;
  tvPreferredFocus?: boolean;
  onPress?: () => void;
}

/** Poster + optional title for rails and grids. RTL-aware (start-aligned). */
export function PosterCard({
  media,
  width = 120,
  title = true,
  tvPreferredFocus = false,
  onPress,
}: PosterCardProps) {
  const aspect = 2 / 3; // poster portrait
  const height = Math.round(width / aspect);
  const hasPoster = !!media.poster_url;

  return (
    <PressableFocus
      tvPreferredFocus={tvPreferredFocus}
      onPress={onPress}
      style={[styles.card, {width}]}
      disabled={!onPress}>
      <View
        style={[
          styles.posterBox,
          {width, height, backgroundColor: hasPoster ? colors.bgSurface : colors.bgSoft},
        ]}>
        {hasPoster ? (
          <Image
            source={{uri: media.poster_url}}
            style={styles.poster}
            resizeMode="cover"
          />
        ) : (
          <View style={styles.posterPlaceholder}>
            <AppText size="sm" color={colors.textMuted}>
              {media.title}
            </AppText>
          </View>
        )}
      </View>
      {title ? (
        <AppText
          numberOfLines={1}
          size="sm"
          color={colors.textSecondary}
          style={styles.title}>
          {media.title}
        </AppText>
      ) : null}
    </PressableFocus>
  );
}

const styles = StyleSheet.create({
  card: {
    marginEnd: spacing.sm,
  },
  posterBox: {
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  poster: {
    width: '100%',
    height: '100%',
  },
  posterPlaceholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.sm,
  },
  title: {
    marginTop: spacing.xs,
  },
});
