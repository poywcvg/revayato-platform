import type {LinkingOptions} from '@react-navigation/native';
import type {RootStackParamList} from './types';

/**
 * Deep links (e.g. `revayato://movie/<slug>`). Keep in sync with navigation/types.
 */
export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['revayato://', 'https://revayato.app'],
  config: {
    screens: {
      Home: '',
      Browse: 'browse/:type?',
      Detail: ':type/:slug',
      Search: 'search',
      Genres: 'genres',
      GenreBrowse: 'genres/:slug',
      Countries: 'countries',
      MoviePlayer: 'movie/:slug/play',
      SeriesPlayer: 'series/:slug/play/:episodeId?',
    },
  },
};
