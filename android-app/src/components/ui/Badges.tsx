import React from 'react';
import {StyleSheet, View} from 'react-native';
import {colors, radius, spacing} from '../../theme';
import {AppText} from './AppText';
import {toFa} from '../../utils/format';

/** Compact badge for an IMDb or site rating. */
export function RatingBadge({
  source,
  value,
}: {
  source: 'imdb' | 'site';
  value: number | null;
}) {
  if (value === null || value === undefined) {return null;}
  const primary = source === 'imdb' ? colors.accentCrimson : colors.brandBright;
  return (
    <View style={[styles.badge, {borderColor: primary}]}>
      <AppText size="xs" color={primary}>
        {source === 'imdb' ? 'IMDb' : 'روایتو'}
      </AppText>
      <AppText size="xs" color={colors.textPrimary} weight="bold">
        {toFa(value)}
      </AppText>
    </View>
  );
}

/** Age rating chip e.g. «۱۸+». Returns null when unknown. */
export function AgeBadge({ageRating}: {ageRating?: string}) {
  const digits = ageRating?.match(/\d+/)?.[0];
  if (!digits) {return null;}
  return (
    <View style={styles.age}>
      <AppText size="xs" color={colors.textSecondary}>
        {toFa(Number(digits))}+
      </AppText>
    </View>
  );
}

/** Small "دوبله فارسی" / "زیرنویس" markers. */
export function FeatureBadge({label}: {label: string}) {
  return (
    <View style={styles.feature}>
      <AppText size="xs" color={colors.brand}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
  },
  age: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
  },
  feature: {
    borderRadius: radius.sm,
    backgroundColor: 'rgba(64,138,113,0.16)',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
  },
});
