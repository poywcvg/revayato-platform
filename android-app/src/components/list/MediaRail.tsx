import React, {useRef} from 'react';
import {FlatList, StyleSheet, View} from 'react-native';
import {colors, spacing} from '../../theme';
import type {AppMedia} from '../../data/catalogAdapter';
import {useTVLayout} from '../../hooks/useTVLayout';
import {AppText} from '../ui/AppText';
import {PosterCard} from '../ui/PosterCard';

interface MediaRailProps {
  title?: string;
  items: AppMedia[];
  onPress?: (media: AppMedia) => void;
  /** Margin-start used to align the header with content on phones. */
  horizontalPadding?: number;
}

/**
 * Horizontal media rail. On TV the first tile requests DPAD focus once; onFocus
 * auto-scrolls the tile into view. FlatList flips automatically under RTL.
 */
export function MediaRail({title, items, onPress, horizontalPadding = spacing.lg}: MediaRailProps) {
  const listRef = useRef<FlatList<AppMedia>>(null);
  const {isTV, tileWidth} = useTVLayout();

  return (
    <View style={styles.rail}>
      {title ? (
        <AppText weight="bold" size="lg" style={styles.header} color={colors.textPrimary}>
          {title}
        </AppText>
      ) : null}
      <FlatList
        ref={listRef}
        data={items}
        keyExtractor={item => `${item.type}-${item.slug}`}
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{paddingStart: horizontalPadding, paddingEnd: horizontalPadding}}
        onScrollToIndexFailed={() => undefined}
        renderItem={({item, index}) => (
          <PosterCard
            media={item}
            width={tileWidth}
            tvPreferredFocus={isTV && index === 0}
            onPress={onPress ? () => onPress(item) : undefined}
          />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  rail: {
    marginVertical: spacing.sm,
  },
  header: {
    marginStart: spacing.lg,
    marginBottom: spacing.sm,
  },
});
