import type {MediaType} from '../data/catalogAdapter';

/**
 * Root stack param map — shared by phone and TV navigators. Player routes are
 * presented fullscreen (they own the orientation lock) so they cover the tab bar.
 */
export type RootStackParamList = {
  Home: undefined;
  Browse: {type: MediaType} | undefined;
  Detail: {type: MediaType; slug: string};
  Search: undefined;
  Genres: undefined;
  GenreBrowse: {slug: string; title: string; kind?: 'genre' | 'country'};
  Countries: undefined;
  MoviePlayer: {slug: string};
  SeriesPlayer: {slug: string; episodeId?: number};
};
