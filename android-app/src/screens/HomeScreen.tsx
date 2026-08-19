import React from 'react';
import {ScrollView, StyleSheet} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {getHomeRails, getTrending} from '../api/endpoints';
import {colors, spacing} from '../theme';
import {t} from '../data/translations';
import type {AppMedia} from '../data/catalogAdapter';
import {adaptListMovie, adaptListSeries} from '../data/catalogAdapter';
import {MediaRail} from '../components/list/MediaRail';
import {LoadingState} from '../components/ui/LoadingState';
import {GridEmptyState} from '../components/list/MediaGrid';
import {AppText} from '../components/ui/AppText';
import type {RootStackParamList} from '../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export function HomeScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();
  const openDetail = (media: AppMedia) =>
    navigation.navigate('Detail', {type: media.type, slug: media.slug});

  const rails = useApiGet(
    'home-rails',
    () => getHomeRails(7),
    {persistKey: 'home-rails', persistTtlMs: 6 * 60 * 60 * 1000, refreshOnResume: true},
  );
  const trending = useApiGet('home-trending', () => getTrending('all', 12));

  const featured: AppMedia[] = (rails.data?.featured ?? []).map(adaptListMovie);
  const dubbed: AppMedia[] = (rails.data?.dubbed ?? []).map(adaptListMovie);
  const popularSeries: AppMedia[] = (rails.data?.popular_series ?? []).map(adaptListSeries);
  const trendingMovies: AppMedia[] = (trending.data?.movies ?? []).map(adaptListMovie);

  const hasAny = featured.length || dubbed.length || popularSeries.length || trendingMovies.length;

  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={{paddingTop: insets.top + spacing.md, paddingBottom: spacing['3xl']}}
      showsVerticalScrollIndicator={false}>
      <AppText style={styles.brand} weight="bold" size="xl" color={colors.brandBright}>
        {t.appName}
      </AppText>
      <AppText style={styles.tagline} size="sm" color={colors.textMuted}>
        {t.tagline}
      </AppText>

      {rails.isLoading && !featured.length ? (
        <LoadingState label={t.loading} />
      ) : rails.error && !featured.length ? (
        <GridEmptyState
          title={t.errorGeneral}
          subtitle={rails.error}
          actionLabel={t.retry}
          onAction={() => rails.refetch()}
        />
      ) : null}

      {featured.length ? (
        <MediaRail title={t.featured} items={featured} onPress={openDetail} />
      ) : null}
      {dubbed.length ? (
        <MediaRail title={t.dubbed} items={dubbed} onPress={openDetail} />
      ) : null}
      {popularSeries.length ? (
        <MediaRail title={t.popularSeries} items={popularSeries} onPress={openDetail} />
      ) : null}
      {trendingMovies.length ? (
        <MediaRail title={t.trending} items={trendingMovies} onPress={openDetail} />
      ) : null}

      {!rails.isLoading && !hasAny && !rails.error ? (
        <GridEmptyState title={t.noResults} />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgMain,
  },
  brand: {
    marginStart: spacing.lg,
    marginBottom: spacing.xxs,
  },
  tagline: {
    marginStart: spacing.lg,
    marginBottom: spacing.md,
  },
});
