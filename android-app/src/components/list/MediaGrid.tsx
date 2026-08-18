import React from 'react';
import {FlatList, StyleSheet, View} from 'react-native';
import {colors, radius, spacing} from '../../theme';
import type {AppMedia} from '../../data/catalogAdapter';
import {useTVLayout} from '../../hooks/useTVLayout';
import {AppText} from '../ui/AppText';
import {PosterCard} from '../ui/PosterCard';
import {PressableFocus} from '../ui/PressableFocus';

interface MediaGridProps {
  items: AppMedia[];
  onPress?: (media: AppMedia) => void;
  columnCount?: number;
  /** Optional footer row rendered after the grid (typ. LoadMore). */
  ListFooterComponent?: React.ReactElement;
}

/** Vertical poster grid used by Browse / GenreBrowse / Countries. */
export function MediaGrid({items, onPress, columnCount, ListFooterComponent}: MediaGridProps) {
  const layout = useTVLayout();
  const cols = columnCount ?? layout.columnCount;
  const tileWidth = Math.floor(items.length ? (layout.width - (cols + 1) * spacing.md) / cols : 100);

  return (
    <FlatList
      data={items}
      keyExtractor={item => `${item.type}-${item.slug}`}
      numColumns={cols}
      columnWrapperStyle={cols > 1 ? styles.row : undefined}
      contentContainerStyle={styles.content}
      ListFooterComponent={ListFooterComponent}
      renderItem={({item, index}) => (
        <View style={{flex: cols === 1 ? 1 : undefined}}>
          <PosterCard media={item} width={tileWidth} tvPreferredFocus={index === 0} onPress={onPress ? () => onPress(item) : undefined} />
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  row: {
    justifyContent: 'flex-start',
    marginBottom: spacing.lg,
  },
  content: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing['2xl'],
    paddingHorizontal: spacing.xl,
  },
  retryBtn: {
    marginTop: spacing.lg,
    backgroundColor: colors.brandBright,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.full,
  },
});

/** Shared grid/list empty or error state. */
export function GridEmptyState({
  title,
  subtitle,
  actionLabel,
  onAction,
}: {
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.empty}>
      <AppText size="lg" color={colors.textPrimary}>
        {title}
      </AppText>
      {subtitle ? (
        <AppText size="sm" color={colors.textMuted} style={{marginTop: spacing.xs}}>
          {subtitle}
        </AppText>
      ) : null}
      {actionLabel && onAction ? (
        <PressableFocus onPress={onAction} style={[styles.retryBtn]} tvPreferredFocus>
          <AppText color={colors.bgMain} weight="bold">
            {actionLabel}
          </AppText>
        </PressableFocus>
      ) : null}
    </View>
  );
}

