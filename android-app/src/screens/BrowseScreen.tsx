import React, {useMemo, useState} from 'react';
import {ScrollView, StyleSheet, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation, useRoute} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {listMovies, listSeries} from '../api/endpoints';
import {colors, radius, spacing} from '../theme';
import {t} from '../data/translations';
import type {AppMedia, MediaType} from '../data/catalogAdapter';
import {adaptListMovie, adaptListSeries} from '../data/catalogAdapter';
import type {ApiMovieListItem, ApiPaginated, ApiSeriesListItem, CatalogFilters} from '../api/types';
import {MediaGrid, GridEmptyState} from '../components/list/MediaGrid';
import {LoadingState} from '../components/ui/LoadingState';
import {AppText} from '../components/ui/AppText';
import {PressableFocus} from '../components/ui/PressableFocus';
import type {RootStackParamList} from '../navigation/types';

const SORTS: {key: Exclude<CatalogFilters['sort'], undefined>; label: string}[] = [
  {key: 'newest', label: 'جدیدترین'},
  {key: 'rating', label: 'برترین‌ها'},
  {key: 'popular', label: 'محبوب‌ترین‌ها'},
  {key: 'trending', label: 'در حال ترند'},
];

type Nav = NativeStackNavigationProp<RootStackParamList>;

export function BrowseScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();
  const route = useRoute();
  const type = (route.params as {type?: MediaType} | undefined)?.type ?? 'movie';
  const [sort, setSort] = useState<CatalogFilters['sort']>('newest');

  const filters: CatalogFilters = useMemo(() => ({sort, limit: 30}), [sort]);
  const movies = useApiGet<ApiPaginated<ApiMovieListItem>, ApiMovieListItem[]>(
    `browse:movie:${sort}`,
    () => listMovies(filters),
    {refreshOnResume: true, select: p => p?.results ?? []},
  );
  const series = useApiGet<ApiPaginated<ApiSeriesListItem>, ApiSeriesListItem[]>(
    `browse:series:${sort}`,
    () => listSeries(filters),
    {refreshOnResume: true, select: p => p?.results ?? []},
  );

  const items: AppMedia[] = useMemo(() => {
    if (type === 'series') {return (series.data ?? []).map(adaptListSeries);}
    return (movies.data ?? []).map(adaptListMovie);
  }, [type, series.data, movies.data]);

  const active = type === 'series' ? series : movies;
  const isLoading = active.isLoading;
  const error = active.error;
  const refetch = active.refetch;

  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={{paddingTop: insets.top + spacing.md, paddingBottom: spacing['3xl']}}>
      <AppText weight="bold" size="xl" color={colors.textPrimary} style={styles.header}>
        {type === 'movie' ? t.movies : t.series}
      </AppText>

      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={styles.chips}>
          {SORTS.map(({key, label}) => (
            <PressableFocus
              key={key}
              onPress={() => setSort(key)}
              style={[
                styles.chip,
                sort === key && styles.chipActive,
              ]}>
              <AppText size="sm" color={sort === key ? colors.bgMain : colors.textSecondary}>
                {label}
              </AppText>
            </PressableFocus>
          ))}
        </View>
      </ScrollView>

      {isLoading && !items.length ? (
        <LoadingState label={t.loading} />
      ) : error && !items.length ? (
        <GridEmptyState
          title={t.errorGeneral}
          subtitle={error}
          actionLabel={t.retry}
          onAction={() => refetch()}
        />
      ) : items.length ? (
        <MediaGrid items={items} onPress={m => navigation.navigate('Detail', {type: m.type, slug: m.slug})} />
      ) : (
        <GridEmptyState title={t.noResults} />
      )}
    </ScrollView>
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
  chips: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  chip: {
    borderRadius: radius.full,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bgSurface,
  },
  chipActive: {
    backgroundColor: colors.brandBright,
  },
});
