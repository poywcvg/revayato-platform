import React from 'react';
import {Image, Linking, ScrollView, StyleSheet, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation, useRoute} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {getMovie, getMovieSimilar, getSeries, getSeriesSimilar} from '../api/endpoints';
import {colors, radius, spacing} from '../theme';
import {t} from '../data/translations';
import {
  adaptDetail,
  adaptListMovie,
  adaptListSeries,
  adaptSeriesDetail,
  AppMedia,
  MediaType,
} from '../data/catalogAdapter';
import {AppText} from '../components/ui/AppText';
import {PressableFocus} from '../components/ui/PressableFocus';
import {PosterCard} from '../components/ui/PosterCard';
import {RatingBadge, AgeBadge, FeatureBadge} from '../components/ui/Badges';
import {LoadingState} from '../components/ui/LoadingState';
import {GridEmptyState} from '../components/list/MediaGrid';
import {toFa, formatDuration} from '../utils/format';
import type {RootStackParamList} from '../navigation/types';
import type {
  ApiMovieListItem,
  ApiPaginated,
  ApiSeriesListItem,
} from '../api/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;
interface RouteParams {
  type?: MediaType;
  slug?: string;
}

export function DetailScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();
  const route = useRoute();
  const {type = 'movie', slug = ''} = (route.params ?? {}) as RouteParams;

  const isSeries = type === 'series';
  const {data, isLoading, error, refetch} = useApiGet(
    `${type}:detail:${slug}`,
    isSeries
      ? () => getSeries(slug).then(adaptSeriesDetail)
      : () => getMovie(slug).then(adaptDetail),
    {ttlMs: 10 * 60 * 1000},
  );

  const media: AppMedia | null = data ?? null;

  const openPlayer = () => {
    if (!media) {return;}
    if (media.type === 'series') {
      navigation.navigate('SeriesPlayer', {slug: media.slug});
    } else {
      navigation.navigate('MoviePlayer', {slug: media.slug});
    }
  };

  const openEpisode = (episodeId: number) => {
    if (media) {navigation.navigate('SeriesPlayer', {slug: media.slug, episodeId});}
  };

  if (isLoading && !media) {
    return (
      <View style={[styles.root, {paddingTop: insets.top}]}>
        <LoadingState label={t.loading} />
      </View>
    );
  }

  if (error && !media) {
    return (
      <View style={[styles.root, {paddingTop: insets.top}]}>
        <GridEmptyState
          title={t.errorGeneral}
          subtitle={error}
          actionLabel={t.retry}
          onAction={() => refetch()}
        />
      </View>
    );
  }

  if (!media) {return null;}

  const hasPlayer = media.type === 'movie'
    ? !!(media.hls_url || media.download_links.length)
    : !!(media.seasons.length);

  const hasBackdrop = !!media.backdrop_url;

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.root}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{paddingBottom: spacing['3xl']}}>
        {/* hero */}
        <View style={styles.hero}>
          {hasBackdrop ? (
            <Image source={{uri: media.backdrop_url}} style={styles.backdrop} resizeMode="cover" />
          ) : null}
          <View style={styles.heroOverlay}>
            <AppText weight="bold" size="2xl" color={colors.textPrimary}>
              {media.title}
            </AppText>
            {media.secondary_title ? (
              <AppText size="sm" color={colors.textSecondary}>
                {media.secondary_title}
              </AppText>
            ) : null}
            <View style={styles.metaRow}>
              {media.year ? <AppText size="sm" color={colors.textMuted}>{toFa(media.year)}</AppText> : null}
              {media.duration_minutes ? (
                <AppText size="sm" color={colors.textMuted}>
                  {formatDuration(media.duration_minutes)}
                </AppText>
              ) : null}
              <AgeBadge ageRating={media.age_rating} />
              {media.is_dubbed ? <FeatureBadge label={t.dubbed} /> : null}
              {media.has_subtitle ? <FeatureBadge label={t.subtitles} /> : null}
            </View>
            <View style={styles.heroBadges}>
              <RatingBadge source="imdb" value={media.imdb_rating} />
              <RatingBadge source="site" value={media.rating_average} />
            </View>
          </View>
        </View>

        {/* genre chips */}
        {media.genres.length ? (
          <View style={styles.chipRow}>
            {media.genres.map(g => (
              <PressableFocus
                key={g.slug}
                style={styles.chip}
                onPress={() =>
                  navigation.navigate('GenreBrowse', {slug: g.slug, title: g.title, kind: 'genre'})
                }>
                <AppText size="xs" color={colors.textSecondary}>{g.title}</AppText>
              </PressableFocus>
            ))}
          </View>
        ) : null}

        {/* action buttons */}
        <View style={styles.actions}>
          {hasPlayer ? (
            <PressableFocus onPress={openPlayer} style={styles.playBtn} tvPreferredFocus>
              <AppText color={colors.bgMain} weight="bold" size="lg">
                {media.type === 'series' ? t.watch : t.play}
              </AppText>
            </PressableFocus>
          ) : null}
          {media.trailer_url ? (
            <PressableFocus
              onPress={() => Linking.openURL(media.trailer_url)}
              style={styles.trailerBtn}>
              <AppText color={colors.textPrimary} size="md">
                🎬 {t.watchNow}
              </AppText>
            </PressableFocus>
          ) : null}
        </View>

        {/* description */}
        {media.description ? (
          <View style={styles.section}>
            <AppText size="md" color={colors.textSecondary} align="right">
              {media.description}
            </AppText>
          </View>
        ) : null}

        {/* cast */}
        {media.cast.length ? (
          <View style={styles.section}>
            <AppText weight="bold" size="lg" color={colors.textPrimary}>
              {t.cast}
            </AppText>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={styles.castRow}>
                {media.cast.map(a => (
                  <View key={a.id} style={styles.castItem}>
                    {a.photo_url ? (
                      <Image source={{uri: a.photo_url}} style={styles.castPhoto} />
                    ) : (
                      <View style={[styles.castPhoto, styles.castPhotoFallback]} />
                    )}
                    <AppText size="xs" color={colors.textSecondary} numberOfLines={1}>
                      {a.name}
                    </AppText>
                    {a.role ? (
                      <AppText size="xs" color={colors.textMuted} numberOfLines={1}>
                        {a.role}
                      </AppText>
                    ) : null}
                  </View>
                ))}
              </View>
            </ScrollView>
          </View>
        ) : null}

        {/* series episodes */}
        {media.type === 'series' && media.seasons.length ? (
          <View style={styles.section}>
            <AppText weight="bold" size="lg" color={colors.textPrimary}>
              {t.episodes}
            </AppText>
            {media.seasons.map(season => (
              <View key={season.id} style={styles.season}>
                <AppText weight="bold" size="md" color={colors.textSecondary}>
                  فصل {toFa(season.season_number)}
                </AppText>
                {season.episodes.map(ep => (
                  <PressableFocus
                    key={ep.id}
                    style={styles.episodeRow}
                    onPress={() => openEpisode(ep.id)}>
                    <AppText size="md" color={colors.textPrimary} weight="medium">
                      {toFa(ep.episode_number)}
                    </AppText>
                    <View style={styles.episodeMeta}>
                      <AppText size="sm" color={colors.textPrimary} numberOfLines={2}>
                        {ep.title}
                      </AppText>
                      <AppText size="xs" color={colors.textMuted}>
                        {ep.duration_minutes ? formatDuration(ep.duration_minutes) : ''}
                      </AppText>
                    </View>
                  </PressableFocus>
                ))}
              </View>
            ))}
          </View>
        ) : null}

        {/* download links */}
        {media.download_links.length ? (
          <View style={styles.section}>
            <AppText weight="bold" size="lg" color={colors.textPrimary}>
              {t.downloads}
            </AppText>
            {media.download_links.map((l, i) => (
              <View key={i} style={styles.dlRow}>
                <AppText size="sm" color={colors.textSecondary} numberOfLines={1}>
                  {l.label}
                </AppText>
              </View>
            ))}
          </View>
        ) : null}

        {/* similar */}
        <SimilarRow type={media.type} slug={media.slug} onPress={m => navigation.navigate('Detail', {type: m.type, slug: m.slug})} />
      </ScrollView>
    </View>
  );
}

function SimilarRow({
  type,
  slug,
  onPress,
}: {
  type: MediaType;
  slug: string;
  onPress: (m: AppMedia) => void;
}) {
  const {data} = useApiGet<
    ApiPaginated<ApiMovieListItem> | ApiPaginated<ApiSeriesListItem>,
    AppMedia[]
  >(
    `${type}:similar:${slug}`,
    () => (type === 'series' ? getSeriesSimilar(slug, 12) : getMovieSimilar(slug, 12)),
    {
      select: page =>
        (page?.results ?? []).map(item =>
          type === 'series'
            ? adaptListSeries(item as ApiSeriesListItem)
            : adaptListMovie(item as ApiMovieListItem),
        ),
    },
  );
  const matches = data ?? [];
  if (!matches.length) {return null;}

  return (
    <View style={styles.section}>
      <AppText weight="bold" size="lg" color={colors.textPrimary}>
        {t.similar}
      </AppText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.similarRow}>
        {matches.map(media => (
          <PosterCard key={`${media.type}-${media.slug}`} media={media} width={120} onPress={() => onPress(media)} />
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgMain,
  },
  hero: {
    position: 'relative',
    minHeight: 220,
  },
  backdrop: {
    width: '100%',
    height: 280,
  },
  heroOverlay: {
    padding: spacing.lg,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.sm,
    flexWrap: 'wrap',
  },
  heroBadges: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md,
  },
  chip: {
    borderRadius: radius.full,
    backgroundColor: colors.bgSurface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.lg,
  },
  playBtn: {
    flex: 1,
    alignItems: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.brandBright,
    paddingVertical: spacing.md,
  },
  trailerBtn: {
    alignItems: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.bgElevated,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  section: {
    marginTop: spacing.xl,
    paddingHorizontal: spacing.lg,
  },
  castRow: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  similarRow: {
    gap: spacing.md,
    paddingTop: spacing.md,
  },
  castItem: {
    width: 96,
    alignItems: 'center',
  },
  castPhoto: {
    width: 72,
    height: 72,
    borderRadius: radius.full,
    backgroundColor: colors.bgSurface,
    marginBottom: spacing.xs,
  },
  castPhotoFallback: {
    backgroundColor: colors.bgElevated,
  },
  season: {
    marginTop: spacing.md,
  },
  episodeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.bgSurface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  episodeMeta: {
    flex: 1,
  },
  dlRow: {
    marginTop: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.bgSurface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
});
