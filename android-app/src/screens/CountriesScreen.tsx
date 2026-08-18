import React from 'react';
import {StyleSheet, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useApiGet} from '../hooks/useApiGet';
import {listCountries} from '../api/endpoints';
import {colors, radius, spacing} from '../theme';
import {t} from '../data/translations';
import {AppText} from '../components/ui/AppText';
import {PressableFocus} from '../components/ui/PressableFocus';
import {LoadingState} from '../components/ui/LoadingState';
import {GridEmptyState} from '../components/list/MediaGrid';
import type {RootStackParamList} from '../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export function CountriesScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();
  const {data, isLoading, error, refetch} = useApiGet(
    'countries',
    () => listCountries(),
    {persistKey: 'countries', persistTtlMs: 24 * 60 * 60 * 1000},
  );

  const countries = data ?? [];

  return (
    <View style={[styles.root, {paddingTop: insets.top + spacing.md}]}>
      <AppText weight="bold" size="xl" color={colors.textPrimary} style={styles.header}>
        {t.countries}
      </AppText>

      {isLoading && !countries.length ? (
        <LoadingState label={t.loading} />
      ) : error && !countries.length ? (
        <GridEmptyState
          title={t.errorGeneral}
          subtitle={error}
          actionLabel={t.retry}
          onAction={() => refetch()}
        />
      ) : countries.length ? (
        <View style={styles.grid}>
          {countries.map((c, i) => (
            <PressableFocus
              key={c.code}
              tvPreferredFocus={i === 0}
              style={styles.card}
              onPress={() =>
                navigation.navigate('GenreBrowse', {
                  slug: c.code,
                  title: c.name,
                  kind: 'country',
                })
              }>
              <AppText size="md" color={colors.textPrimary} weight="medium">
                {c.name}
              </AppText>
              <AppText size="xs" color={colors.textMuted}>
                {c.movie_count} {t.movies} · {c.series_count} {t.series}
              </AppText>
            </PressableFocus>
          ))}
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
