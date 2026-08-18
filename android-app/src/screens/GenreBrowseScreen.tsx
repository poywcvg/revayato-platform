import React, {useMemo} from 'react';
import {StyleSheet, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation, useRoute} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {listMovies} from '../api/endpoints';
import type {CatalogFilters} from '../api/types';
import {colors, spacing} from '../theme';
import {t} from '../data/translations';
import type {AppMedia} from '../data/catalogAdapter';
import {adaptListMovie} from '../data/catalogAdapter';
import {MediaGrid, GridEmptyState} from '../components/list/MediaGrid';
import {LoadingState} from '../components/ui/LoadingState';
import {AppText} from '../components/ui/AppText';
import type {RootStackParamList} from '../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;
interface RouteParams {
  slug: string;
  title: string;
  kind?: 'genre' | 'country';
}

/**
 * Browsing list scoped by a Genre slug or a Country code. The filter map grabs
 * the right param (`genre` vs `country`) from the route, so one screen serves
 * both GenreBrowse and Countries without dead routes.
 */
export function GenreBrowseScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();
  const route = useRoute();
  const {slug, title, kind = 'genre'} = (route.params ?? {}) as RouteParams;

  const filters: CatalogFilters = useMemo(
    () => (kind === 'country' ? {country: slug} : {genre: slug}),
    [kind, slug],
  );

  const {data, isLoading, error, refetch} = useApiGet(
    `browse:${kind}:${slug}`,
    () => listMovies({...filters, limit: 40}),
    {refreshOnResume: true},
  );

  const items: AppMedia[] = useMemo(
    () => (data?.results ?? []).map(adaptListMovie),
    [data],
  );

  return (
    <View style={[styles.root, {paddingTop: insets.top + spacing.md}]}>
      <AppText weight="bold" size="xl" color={colors.textPrimary} style={styles.header}>
        {title}
      </AppText>

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
        <MediaGrid
          items={items}
          onPress={m => navigation.navigate('Detail', {type: m.type, slug: m.slug})}
        />
      ) : (
        <GridEmptyState title={t.noResults} />
      )}
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
});
