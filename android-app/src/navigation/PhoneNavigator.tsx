import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {StyleSheet, View} from 'react-native';
import {colors} from '../theme';
import {AppText} from '../components/ui/AppText';
import type {RootStackParamList} from './types';
import {HomeScreen} from '../screens/HomeScreen';
import {BrowseScreen} from '../screens/BrowseScreen';
import {SearchScreen} from '../screens/SearchScreen';
import {DetailScreen} from '../screens/DetailScreen';
import {GenresScreen} from '../screens/GenresScreen';
import {GenreBrowseScreen} from '../screens/GenreBrowseScreen';
import {CountriesScreen} from '../screens/CountriesScreen';
import {PlayerScreen} from '../player/PlayerScreen';
import {EpisodePlayer} from '../player/EpisodePlayer';
import {t} from '../data/translations';

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<Pick<RootStackParamList, 'Home' | 'Browse' | 'Search'>>();

// ----------------------------------------------------------- phone bottom tabs

function TabIcon({label, focused}: {label: string; focused: boolean}) {
  return (
    <View style={styles.tabItem}>
      <View style={[styles.dot, focused && styles.dotActive]} />
      <AppText size="xs" color={focused ? colors.brandBright : colors.textMuted}>
        {label}
      </AppText>
    </View>
  );
}

const TAB_LABELS: Record<string, string> = {
  Home: t.home,
  Browse: t.browse,
  Search: t.search,
};

function phoneTabIcon(routeName: string) {
  return ({focused}: {focused: boolean}) => (
    <TabIcon label={TAB_LABELS[routeName] ?? routeName} focused={focused} />
  );
}

function PhoneTabs() {
  return (
    <Tab.Navigator
      screenOptions={({route}) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.brandBright,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: {
          backgroundColor: colors.bgMain,
          borderTopColor: colors.line,
          height: 62,
          paddingBottom: 8,
          paddingTop: 6,
        },
        sceneStyle: {backgroundColor: colors.bgMain},
        tabBarIcon: phoneTabIcon(route.name),
        tabBarLabel: () => null,
      })}>
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="Browse" component={BrowseScreen} />
      <Tab.Screen name="Search" component={SearchScreen} />
    </Tab.Navigator>
  );
}

// --------------------------------------------------------------- phone stack

export function PhoneNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: {backgroundColor: colors.bgMain},
        animation: 'slide_from_right',
      }}>
      <Stack.Screen name="Home" component={PhoneTabs} />
      <Stack.Screen name="Detail" component={DetailScreen} />
      <Stack.Screen name="GenreBrowse" component={GenreBrowseScreen} />
      <Stack.Screen name="Genres" component={GenresScreen} />
      <Stack.Screen name="Countries" component={CountriesScreen} />
      <Stack.Screen
        name="MoviePlayer"
        component={PlayerScreen}
        options={{presentation: 'fullScreenModal'}}
      />
      <Stack.Screen
        name="SeriesPlayer"
        component={EpisodePlayer}
        options={{presentation: 'fullScreenModal'}}
      />
    </Stack.Navigator>
  );
}

const styles = StyleSheet.create({
  tabItem: {
    alignItems: 'center',
    gap: 2,
    width: 72,
  },
  dot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: 'transparent',
  },
  dotActive: {
    backgroundColor: colors.brandBright,
  },
});
