import React from 'react';
import {StyleSheet, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {listGenres} from '../api/endpoints';
import {colors, radius, spacing} from '../theme';
import {t} from '../data/translations';
import {AppText} from '../components/ui/AppText';
import {PressableFocus} from '../components/ui/PressableFocus';
import {LoadingState} from '../components/ui/LoadingState';
import {GridEmptyState} from '../components/list/MediaGrid';
import type {RootStackParamList} from '../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export function GenresScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();
  const {data, isLoading, error, refetch} = useApiGet(
    'genres',
    () => listGenres(),
    {persistKey: 'genres', persistTtlMs: 24 * 60 * 60 * 1000},
  );

  const genres = data ?? [];

  return (
    <View style={[styles.root, {paddingTop: insets.top + spacing.md}]}>
      <AppText weight="bold" size="xl" color={colors.textPrimary} style={styles.header}>
        {t.genres}
      </AppText>

      {isLoading && !genres.length ? (
        <LoadingState label={t.loading} />
      ) : error && !genres.length ? (
        <GridEmptyState
          title={t.errorGeneral}
          subtitle={error}
          actionLabel={t.retry}
          onAction={() => refetch()}
        />
      ) : genres.length ? (
        <View style={styles.grid}>
          {genres.map((g, i) => {
            const count = (g.movie_count ?? 0) + (g.series_count ?? 0);
            return (
              <PressableFocus
                key={g.slug}
                tvPreferredFocus={i === 0}
                style={styles.card}
                onPress={() => navigation.navigate('GenreBrowse', {slug: g.slug, title: g.title, kind: 'genre'})}>
                <AppText size="md" color={colors.textPrimary} weight="medium">
                  {g.title}
                </AppText>
                {count > 0 ? (
                  <AppText size="xs" color={colors.textMuted}>
                    {t.movies} + {t.series} · {count}
                  </AppText>
                ) : null}
              </PressableFocus>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgMain,
  },
  header: {
    marginStart: spacing.lg,
    marginBottom: spacing.md,
  },
  grid: {
    paddingHorizontal: spacing.lg,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  card: {
    backgroundColor: colors.bgSurface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.lg,
    minWidth: '30%',
  },
});
