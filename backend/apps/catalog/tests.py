from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.test import TestCase
from datetime import datetime, timezone as dt_timezone

from .models import Country, Director, Episode, Movie, Season, Series


def make_movie(**kwargs):
    defaults = {
        'title': 'Test Movie',
        'slug': 'test-movie',
        'is_published': False,
    }
    defaults.update(kwargs)
    return Movie.objects.create(**defaults)


class MovieVisibilityTests(TestCase):
    def test_draft_movie_excluded_from_public_list(self):
        make_movie(title='Draft Movie', slug='draft-movie', is_published=False)

        response = self.client.get('/api/movies/')

        self.assertEqual(response.status_code, 200)
        slugs = [item['slug'] for item in response.json()['results']]
        self.assertNotIn('draft-movie', slugs)

    def test_draft_movie_detail_not_found(self):
        make_movie(title='Draft Movie', slug='draft-movie', is_published=False)

        response = self.client.get('/api/movies/draft-movie/')

        self.assertEqual(response.status_code, 404)

    def test_published_movie_visible_in_list_and_detail(self):
        make_movie(title='Published Movie', slug='published-movie', is_published=True)

        list_response = self.client.get('/api/movies/')
        detail_response = self.client.get('/api/movies/published-movie/')

        self.assertEqual(list_response.status_code, 200)
        slugs = [item['slug'] for item in list_response.json()['results']]
        self.assertIn('published-movie', slugs)

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()['title'], 'Published Movie')

    def test_slug_lookup_returns_correct_movie(self):
        make_movie(title='Movie A', slug='movie-a', is_published=True)
        make_movie(title='Movie B', slug='movie-b', is_published=True)

        response = self.client.get('/api/movies/movie-b/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Movie B')

    def test_seo_fields_fall_back_when_not_set(self):
        movie = make_movie(
            title='Movie C', slug='movie-c', is_published=True,
            short_description='A short teaser.',
        )

        self.assertEqual(movie.seo_title, 'Movie C')
        self.assertEqual(movie.seo_description, 'A short teaser.')

    def test_seo_description_includes_cast_names(self):
        from .models import Actor, MovieActor

        movie = make_movie(
            title='Movie Cast', slug='movie-cast', is_published=True,
            short_description='داستان کوتاه.',
        )
        actor = Actor.objects.create(name='Ali Actor', slug='ali-actor')
        MovieActor.objects.create(movie=movie, actor=actor, role='Lead', order=0)

        self.assertIn('Ali Actor', movie.seo_description)
        self.assertIn('بازیگران', movie.seo_description)

    def test_seo_and_download_metadata_from_links(self):
        movie = make_movie(
            title='Movie DL', slug='movie-dl', is_published=True,
            short_description='داستان کوتاه.',
            download_links=[
                {'label': '1080p', 'quality': '1080p', 'url': 'https://cdn.example/a.mkv'},
                {'label': '720p', 'quality': '720p', 'url': 'https://cdn.example/b.mkv'},
            ],
        )

        self.assertTrue(movie.has_downloads)
        self.assertEqual(movie.download_qualities, ['1080p', '720p'])
        self.assertIn('دانلود: 1080p', movie.seo_description)
        self.assertIn('دانلود', movie.effective_seo_keywords)
        self.assertIn('1080p', movie.effective_seo_keywords)

        response = self.client.get('/api/movies/movie-dl/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['has_downloads'])
        self.assertEqual(payload['download_qualities'], ['1080p', '720p'])
        self.assertIn('دانلود', payload['seo_keywords'])
        self.assertIn('دانلود: 1080p', payload['seo_description'])


class MovieExternalIdTests(TestCase):
    def test_duplicate_tmdb_id_rejected(self):
        make_movie(title='Movie A', slug='movie-a', tmdb_id=101)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_movie(title='Movie B', slug='movie-b', tmdb_id=101)

    def test_duplicate_imdb_id_rejected(self):
        make_movie(title='Movie A', slug='movie-a', imdb_id='tt0000001')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_movie(title='Movie B', slug='movie-b', imdb_id='tt0000001')

    def test_multiple_movies_without_external_ids_allowed(self):
        make_movie(title='Movie A', slug='movie-a')
        make_movie(title='Movie B', slug='movie-b')

        self.assertEqual(Movie.objects.count(), 2)


class CatalogApiContractTests(TestCase):
    def test_movie_list_filters_and_exposes_card_metadata(self):
        director = Director.objects.create(name='Hana Noor', slug='hana-noor')
        country = Country.objects.create(name='Iran', code='IR')
        movie = make_movie(
            title='Visible Movie', slug='visible-movie', is_published=True,
            release_year=2025, language='Persian', age_rating='15+',
            imdb_rating='8.7', is_featured=True, trailer_url='movies/animated/trailer.m3u8',
            content_format='animation', is_dubbed=True, has_subtitle=True,
            is_uncensored=True, content_warnings=['violence'],
        )
        movie.directors.add(director)
        movie.countries.add(country)
        make_movie(title='Other Movie', slug='other-movie', is_published=True, release_year=2020)

        response = self.client.get('/api/movies/', {
            'q': 'Hana',
            'year': '2025',
            'country': 'IR',
            'language': 'Persian',
            'age': '15+',
            'min_rating': '8',
            'availability': 'dubbed',
            'content_format': 'animation',
        })

        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual([item['slug'] for item in results], ['visible-movie'])
        self.assertEqual(results[0]['directors'][0]['name'], 'Hana Noor')
        self.assertEqual(results[0]['countries'][0]['code'], 'IR')
        self.assertEqual(results[0]['countries'][0]['name'], 'ایران')
        self.assertTrue(results[0]['is_featured'])
        self.assertTrue(results[0]['is_dubbed'])
        self.assertTrue(results[0]['has_subtitle'])
        self.assertTrue(results[0]['is_uncensored'])
        self.assertEqual(results[0]['content_format'], 'animation')
        self.assertIn('has_downloads', results[0])
        self.assertFalse(results[0]['has_downloads'])
        self.assertEqual(results[0]['trailer_url'], '/media/movies/animated/trailer.m3u8')

        detail_response = self.client.get('/api/movies/visible-movie/')
        self.assertEqual(detail_response.json()['content_warnings'], ['violence'])

        persian_filter = self.client.get('/api/movies/', {'country': 'ایران'})
        self.assertEqual(
            [item['slug'] for item in persian_filter.json()['results']],
            ['visible-movie'],
        )

        countries_response = self.client.get('/api/countries/')
        self.assertEqual(countries_response.status_code, 200)
        iran = next(item for item in countries_response.json() if item['code'] == 'IR')
        self.assertEqual(iran['name'], 'ایران')
        self.assertEqual(iran['movie_count'], 1)
        self.assertEqual(iran['series_count'], 0)

    def test_movie_list_filters_by_tag_slug(self):
        from .models import Tag
        tagged = make_movie(title='Marvel Movie', slug='marvel-movie', is_published=True)
        make_movie(title='Other Movie', slug='plain-movie', is_published=True)
        tag = Tag.objects.create(name='مارول', slug='marvel', is_featured=True)
        tagged.tags.add(tag)

        response = self.client.get('/api/movies/', {'tag': 'marvel'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['slug'] for item in response.json()['results']], ['marvel-movie'])

    def test_recent_catalog_mixes_movies_and_series_by_created_at(self):
        older_movie = make_movie(title='Older Movie', slug='older-movie', is_published=True)
        series = Series.objects.create(
            title='Fresh Series', slug='fresh-series', is_published=True, start_year=2024,
        )
        newer_movie = make_movie(title='Newer Movie', slug='newer-movie', is_published=True)
        make_movie(title='Draft Movie', slug='draft-recent', is_published=False)

        # Ensure created_at ordering is deterministic regardless of insert timing.
        Movie.objects.filter(pk=older_movie.pk).update(
            created_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        )
        Series.objects.filter(pk=series.pk).update(
            created_at=datetime(2024, 6, 1, tzinfo=dt_timezone.utc),
        )
        Movie.objects.filter(pk=newer_movie.pk).update(
            created_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
        )

        response = self.client.get('/api/catalog/recent/', {'limit': 10})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 3)
        slugs = [item['slug'] for item in payload['results']]
        self.assertEqual(slugs, ['newer-movie', 'fresh-series', 'older-movie'])
        self.assertEqual(payload['results'][0]['content_type'], 'movie')
        self.assertEqual(payload['results'][1]['content_type'], 'series')

        page = self.client.get('/api/catalog/recent/', {'limit': 1, 'offset': 1})
        self.assertEqual(page.json()['results'][0]['slug'], 'fresh-series')
        self.assertTrue(page.json()['next'])
        self.assertTrue(page.json()['previous'])

    def test_rating_sort_and_invalid_numeric_filters_are_safe(self):
        make_movie(title='Lower', slug='lower', is_published=True, imdb_rating='6.5')
        make_movie(title='Higher', slug='higher', is_published=True, imdb_rating='9.1')

        sorted_response = self.client.get('/api/movies/', {'sort': 'rating'})
        invalid_response = self.client.get('/api/movies/', {'year': 'not-a-year', 'min_rating': 'invalid'})
        trending_response = self.client.get('/api/trending/', {'limit': 'invalid'})

        self.assertEqual(sorted_response.status_code, 200)
        self.assertEqual(sorted_response.json()['results'][0]['slug'], 'higher')
        self.assertEqual(invalid_response.status_code, 200)
        self.assertEqual(trending_response.status_code, 200)

    def test_offset_past_last_page_returns_empty_results(self):
        make_movie(title='Only Movie', slug='only-movie', is_published=True)

        response = self.client.get('/api/movies/', {'offset': 500})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

    def test_movie_list_omits_full_description_and_caches_responses(self):
        make_movie(
            title='Cached Movie',
            slug='cached-movie',
            is_published=True,
            description='Long synopsis that must not ship in list payloads.',
            short_description='Short teaser.',
        )

        first = self.client.get('/api/movies/', {'limit': 10, 'sort': 'newest'})
        second = self.client.get('/api/movies/', {'limit': 10, 'sort': 'newest'})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first['X-Catalog-Cache'], 'MISS')
        self.assertEqual(second['X-Catalog-Cache'], 'HIT')
        item = first.json()['results'][0]
        self.assertEqual(item['slug'], 'cached-movie')
        self.assertEqual(item['short_description'], 'Short teaser.')
        self.assertNotIn('description', item)
        self.assertIn('public', first['Cache-Control'])

    def test_catalog_cache_invalidates_after_publish_change(self):
        movie = make_movie(title='Draft Then Live', slug='draft-then-live', is_published=False)
        empty = self.client.get('/api/movies/', {'limit': 5})
        self.assertEqual(empty.json()['results'], [])

        movie.is_published = True
        movie.save(update_fields=['is_published', 'updated_at'])

        live = self.client.get('/api/movies/', {'limit': 5})
        self.assertEqual(live['X-Catalog-Cache'], 'MISS')
        self.assertEqual([item['slug'] for item in live.json()['results']], ['draft-then-live'])


class SeriesPublicationApiTests(TestCase):
    def test_detail_exposes_only_published_seasons_and_episodes(self):
        series = Series.objects.create(title='Test Series', slug='test-series', is_published=True)
        published_season = Season.objects.create(
            series=series, season_number=1, title='Published Season', is_published=True,
        )
        draft_season = Season.objects.create(
            series=series, season_number=2, title='Draft Season', is_published=False,
        )
        empty_season = Season.objects.create(
            series=series, season_number=3, title='Empty Season', is_published=True,
        )
        Episode.objects.create(
            season=published_season,
            episode_number=1,
            title='Published Episode',
            is_published=True,
            video_url='https://cdn.example/s1e1.mp4',
        )
        Episode.objects.create(
            season=published_season, episode_number=2, title='Draft Episode', is_published=False,
        )
        Episode.objects.create(
            season=draft_season,
            episode_number=1,
            title='Hidden Season Episode',
            is_published=True,
            video_url='https://cdn.example/s2e1.mp4',
        )
        Episode.objects.create(
            season=empty_season,
            episode_number=1,
            title='No stream',
            is_published=True,
            video_url='',
        )

        response = self.client.get('/api/series/test-series/')

        self.assertEqual(response.status_code, 200)
        seasons = response.json()['seasons']
        self.assertEqual([season['season_number'] for season in seasons], [1])
        self.assertEqual([episode['episode_number'] for episode in seasons[0]['episodes']], [1])


class SeedCatalogTests(TestCase):
    def test_seed_creates_public_playable_metadata_and_is_repeatable(self):
        call_command('seed_catalog', verbosity=0)
        call_command('seed_catalog', verbosity=0)

        movie = Movie.objects.get(slug='silent-orbit')
        series = Series.objects.get(slug='red-signal')
        season = series.seasons.get(season_number=1)

        self.assertTrue(movie.has_subtitle)
        self.assertTrue(movie.is_dubbed)
        self.assertTrue(movie.video_url.endswith('.m3u8'))
        self.assertEqual(movie.countries.get().code, 'GB')
        self.assertTrue(season.is_published)
        self.assertEqual(season.episode_count, 3)
        self.assertTrue(season.episodes.filter(is_published=True).exists())


class ActorApiTests(TestCase):
    def test_actor_list_only_includes_published_titles(self):
        from .models import Actor, MovieActor

        published = make_movie(title='Published Cast', slug='published-cast', is_published=True)
        draft = make_movie(title='Draft Cast', slug='draft-cast', is_published=False)
        visible = Actor.objects.create(name='Visible Actor', slug='visible-actor', popularity=10)
        hidden = Actor.objects.create(name='Hidden Actor', slug='hidden-actor', popularity=20)
        MovieActor.objects.create(movie=published, actor=visible, order=0)
        MovieActor.objects.create(movie=draft, actor=hidden, order=0)

        response = self.client.get('/api/actors/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        results = payload['results'] if isinstance(payload, dict) and 'results' in payload else payload
        slugs = [item['slug'] for item in results]
        self.assertIn('visible-actor', slugs)
        self.assertNotIn('hidden-actor', slugs)

    def test_actor_detail_includes_filmography(self):
        from .models import Actor, MovieActor

        movie = make_movie(title='Filmography Movie', slug='filmography-movie', is_published=True)
        actor = Actor.objects.create(name='Lead Star', slug='lead-star')
        MovieActor.objects.create(movie=movie, actor=actor, role='Hero', order=0)

        response = self.client.get('/api/actors/lead-star/')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['slug'], 'lead-star')
        self.assertEqual(body['movies'][0]['slug'], 'filmography-movie')

    def test_search_finds_actor_by_original_name(self):
        from .models import Actor, MovieActor

        movie = make_movie(title='Cast Search Movie', slug='cast-search-movie', is_published=True)
        actor = Actor.objects.create(
            name='تیموتی شالامه',
            original_name='Timothee Chalamet',
            slug='timothee-chalamet',
        )
        MovieActor.objects.create(movie=movie, actor=actor, order=0)

        response = self.client.get('/api/search/', {'q': 'Chalamet', 'type': 'actor'})

        self.assertEqual(response.status_code, 200)
        slugs = [item['slug'] for item in response.json().get('actors', [])]
        self.assertIn('timothee-chalamet', slugs)

    def test_search_returns_close_title_when_direct_match_is_missing(self):
        make_movie(
            title='Interstellar',
            original_title='Interstellar',
            slug='interstellar',
            is_published=True,
            popularity=90,
        )
        make_movie(
            title='Unrelated title',
            slug='unrelated-title',
            is_published=True,
            popularity=100,
        )

        response = self.client.get('/api/search/', {
            'q': 'Interstelar',
            'type': 'movie',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['match_type'], 'similar')
        self.assertEqual(payload['movies'][0]['slug'], 'interstellar')
        self.assertNotIn(
            'unrelated-title',
            [item['slug'] for item in payload['movies']],
        )

    def test_search_normalizes_persian_keyboard_variants(self):
        make_movie(
            title='کیان',
            slug='kian',
            is_published=True,
        )

        response = self.client.get('/api/search/', {
            'q': 'كيان',
            'type': 'movie',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['match_type'], 'direct')
        self.assertEqual(payload['movies'][0]['slug'], 'kian')

    def test_search_finds_related_titles_by_genre(self):
        from .models import Genre

        genre = Genre.objects.create(title='علمی تخیلی', slug='science-fiction')
        movie = make_movie(
            title='Space Story',
            slug='space-story',
            is_published=True,
        )
        movie.genres.add(genre)

        response = self.client.get('/api/search/', {
            'q': 'علمی تخیلی',
            'type': 'movie',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['match_type'], 'direct')
        self.assertEqual(payload['movies'][0]['slug'], 'space-story')

    def test_search_prefers_title_tokens_over_synopsis_noise(self):
        make_movie(
            title='Unrelated City Lights',
            slug='unrelated-city-lights',
            is_published=True,
            popularity=100,
            short_description='A documentary about dead city architecture.',
        )
        Series.objects.create(
            title='The Walking Dead: Dead City',
            original_title='The Walking Dead: Dead City',
            slug='the-walking-dead-dead-city',
            is_published=True,
            popularity=40,
        )

        response = self.client.get('/api/search/', {
            'q': 'dead city',
            'type': 'all',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['match_type'], 'direct')
        series_slugs = [item['slug'] for item in payload.get('series', [])]
        self.assertIn('the-walking-dead-dead-city', series_slugs)
        self.assertEqual(series_slugs[0], 'the-walking-dead-dead-city')

    def test_search_by_year_returns_movies_and_series_from_database(self):
        make_movie(
            title='Movie From Requested Year',
            slug='movie-from-requested-year',
            release_year=2024,
            is_published=True,
        )
        make_movie(
            title='Movie From Another Year',
            slug='movie-from-another-year',
            release_year=2023,
            is_published=True,
        )
        Series.objects.create(
            title='Series From Requested Year',
            slug='series-from-requested-year',
            start_year=2024,
            is_published=True,
        )

        response = self.client.get('/api/search/', {'q': '2024', 'type': 'all'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['year'], 2024)
        self.assertEqual(payload['search_text'], '')
        self.assertEqual(payload['match_type'], 'direct')
        self.assertEqual(
            [item['slug'] for item in payload['movies']],
            ['movie-from-requested-year'],
        )
        self.assertEqual(
            [item['slug'] for item in payload['series']],
            ['series-from-requested-year'],
        )

    def test_search_understands_persian_year_digits(self):
        make_movie(
            title='Persian Digit Year',
            slug='persian-digit-year',
            release_year=2025,
            is_published=True,
        )

        response = self.client.get('/api/search/', {'q': 'سال ۲۰۲۵', 'type': 'movie'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['year'], 2025)
        self.assertEqual(payload['search_text'], '')
        self.assertEqual([item['slug'] for item in payload['movies']], ['persian-digit-year'])

    def test_title_and_year_query_narrows_duplicate_titles(self):
        make_movie(
            title='Dune',
            original_title='Dune',
            slug='dune-1984',
            release_year=1984,
            is_published=True,
        )
        make_movie(
            title='Dune',
            original_title='Dune',
            slug='dune-2021',
            release_year=2021,
            is_published=True,
        )

        response = self.client.get('/api/search/', {'q': 'Dune (2021)', 'type': 'movie'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['year'], 2021)
        self.assertEqual(payload['search_text'], 'Dune')
        self.assertEqual([item['slug'] for item in payload['movies']], ['dune-2021'])

    def test_explicit_year_parameter_narrows_header_search(self):
        make_movie(
            title='Legend',
            original_title='Legend',
            slug='legend-1985',
            release_year=1985,
            is_published=True,
        )
        make_movie(
            title='Legend',
            original_title='Legend',
            slug='legend-2015',
            release_year=2015,
            is_published=True,
        )

        response = self.client.get('/api/search/', {
            'q': 'Legend',
            'year': '2015',
            'type': 'movie',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['year'], 2015)
        self.assertEqual([item['slug'] for item in payload['movies']], ['legend-2015'])

    def test_search_miss_returns_empty_response(self):
        make_movie(
            title='Known Film',
            slug='known-film',
            is_published=True,
        )

        response = self.client.get('/api/search/', {
            'q': 'zzzzunlikelytitlezzzz',
            'type': 'movie',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['match_type'], 'none')
        self.assertEqual(payload['movies'], [])

    def test_movie_list_treats_year_in_single_search_field_as_filter(self):
        make_movie(
            title='List Search Year',
            slug='list-search-year',
            release_year=2022,
            is_published=True,
        )
        make_movie(
            title='Different List Search Year',
            slug='different-list-search-year',
            release_year=2021,
            is_published=True,
        )

        response = self.client.get('/api/movies/', {'q': '۲۰۲۲'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['slug'] for item in response.json()['results']],
            ['list-search-year'],
        )
