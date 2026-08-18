import React, {useCallback, useState} from 'react';
import {ScrollView, StyleSheet, TextInput, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {useNavigation} from '@react-navigation/native';
import type {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {searchContent} from '../api/endpoints';
import {colors, radius, spacing} from '../theme';
import {t} from '../data/translations';
import type {AppMedia} from '../data/catalogAdapter';
import {adaptListMovie, adaptListSeries} from '../data/catalogAdapter';
import {MediaGrid, GridEmptyState} from '../components/list/MediaGrid';
import {AppText} from '../components/ui/AppText';
import {PressableFocus} from '../components/ui/PressableFocus';
import type {RootStackParamList} from '../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Tab = 'movie' | 'series';

export function SearchScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<Nav>();

  const [q, setQ] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [tab, setTab] = useState<Tab>('movie');
  const [results, setResults] = useState<{movies: AppMedia[]; series: AppMedia[]}>({
    movies: [],
    series: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (trimmed.length < 2) {
        setSubmitted(false);
        setResults({movies: [], series: []});
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const res = await searchContent(trimmed, 'all', 12);
        setSubmitted(true);
        setResults({
          movies: (res.movies ?? []).map(adaptListMovie),
          series: (res.series ?? []).map(adaptListSeries),
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : t.errorGeneral);
        setSubmitted(false);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const activeItems: AppMedia[] = tab === 'movie' ? results.movies : results.series;
  const activeCount = activeItems.length;

  return (
    <ScrollView
      style={styles.root}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={{paddingTop: insets.top + spacing.md, paddingBottom: spacing['3xl']}}>
      <AppText weight="bold" size="xl" color={colors.textPrimary} style={styles.header}>
        {t.search}
      </AppText>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          value={q}
          placeholder={t.searchPlaceholder}
          placeholderTextColor={colors.textMuted}
          autoCorrect={false}
          returnKeyType="search"
          onChangeText={v => {
            setQ(v);
            setResults({movies: [], series: []});
            setSubmitted(false);
          }}
          onSubmitEditing={() => run(q)}
        />
        <PressableFocus onPress={() => run(q)} style={styles.goBtn}>
          <AppText color={colors.bgMain} weight="bold">
            {t.search}
          </AppText>
        </PressableFocus>
      </View>

      {loading ? (
        <GridEmptyState title={t.loading} />
      ) : error ? (
        <GridEmptyState
          title={t.errorGeneral}
          subtitle={error}
          actionLabel={t.retry}
          onAction={() => run(q)}
        />
      ) : submitted && !activeItems.length ? (
        <GridEmptyState
          title={t.noResults}
          subtitle={activeCount === 0 && (results.movies.length || results.series.length) ? t.minSearch : undefined}
        />
      ) : activeItems.length ? (
        <>
          <View style={styles.tabs}>
            {(
              [
                {key: 'movie' as Tab, label: t.movies, count: results.movies.length},
                {key: 'series' as Tab, label: t.series, count: results.series.length},
              ]
            ).map(tabDef => (
              <PressableFocus
                key={tabDef.key}
                onPress={() => setTab(tabDef.key)}
                style={[styles.tab, tab === tabDef.key && styles.tabActive]}>
                <AppText size="sm" color={tab === tabDef.key ? colors.bgMain : colors.textSecondary}>
                  {tabDef.label} ({tabDef.count})
                </AppText>
              </PressableFocus>
            ))}
          </View>
          <MediaGrid
            items={activeItems}
            onPress={m => navigation.navigate('Detail', {type: m.type, slug: m.slug})}
          />
        </>
      ) : null}
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
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
  },
  input: {
    flex: 1,
    borderRadius: radius.md,
    backgroundColor: colors.bgSurface,
    color: colors.textPrimary,
    paddingHorizontal: spacing.lg,
    paddingVertical: 10,
  },
  goBtn: {
    backgroundColor: colors.brandBright,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 10,
  },
  tabs: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  tab: {
    borderRadius: radius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bgSurface,
  },
  tabActive: {
    backgroundColor: colors.brandBright,
  },
});
