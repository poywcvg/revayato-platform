import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import type {RootStackParamList} from './types';
import {colors} from '../theme';
import {HomeScreen} from '../screens/HomeScreen';
import {BrowseScreen} from '../screens/BrowseScreen';
import {SearchScreen} from '../screens/SearchScreen';
import {DetailScreen} from '../screens/DetailScreen';
import {GenresScreen} from '../screens/GenresScreen';
import {GenreBrowseScreen} from '../screens/GenreBrowseScreen';
import {CountriesScreen} from '../screens/CountriesScreen';
import {PlayerScreen} from '../player/PlayerScreen';
import {EpisodePlayer} from '../player/EpisodePlayer';

const Stack = createNativeStackNavigator<RootStackParamList>();

/**
 * TV lands on a single stack (no tab bar — DPAD focus lives on rails/cards).
 * Home is the launching point; everything else pushes.
 */
export function TvNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: {backgroundColor: colors.bgMain},
        animation: 'none',
      }}>
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="Browse" component={BrowseScreen} />
      <Stack.Screen name="Search" component={SearchScreen} />
      <Stack.Screen name="Detail" component={DetailScreen} />
      <Stack.Screen name="Genres" component={GenresScreen} />
      <Stack.Screen name="GenreBrowse" component={GenreBrowseScreen} />
      <Stack.Screen name="Countries" component={CountriesScreen} />
      <Stack.Screen name="MoviePlayer" component={PlayerScreen} />
      <Stack.Screen name="SeriesPlayer" component={EpisodePlayer} />
    </Stack.Navigator>
  );
}
