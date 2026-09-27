"""English page addresses for movies/series, with old addresses kept alive."""

import copy
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .ingestion import upsert_tmdb_movie
from .models import CatalogSlugAlias, Movie, Series
from .slugs import canonical_slug, english_slug_base, english_slug_for, is_english_slug
from .tests_ingestion import MOVIE_DETAILS


class EnglishSlugHelperTests(TestCase):
    def test_base_is_ascii_title_plus_year(self):
        self.assertEqual(english_slug_base('Inception', year=2010), 'inception-2010')
        self.assertEqual(english_slug_base('Amélie', year=2001), 'amelie-2001')

    def test_non_latin_title_falls_through_to_next_candidate(self):
        self.assertEqual(english_slug_base('ذهن زیبا', 'A Beautiful Mind', year=2001), 'a-beautiful-mind-2001')
        self.assertEqual(english_slug_base('千と千尋', 'فیلم', fallback='movie-129'), 'movie-129')

    def test_collision_takes_tmdb_suffix(self):
        Movie.objects.create(title='الف', slug='dune-2021')
        self.assertEqual(
            english_slug_for(Movie, title='تلماسه', original_title='Dune', year=2021, tmdb_id=438631),
            'dune-2021-438631',
        )

    def test_existing_english_slug_is_kept(self):
        self.assertEqual(
            english_slug_for(Movie, original_title='Dune', year=2021, current_slug='dune'), 'dune',
        )

    def test_is_english_slug(self):
        self.assertTrue(is_english_slug('inception-2010'))
        self.assertFalse(is_english_slug('ذهن-زیبا'))
        self.assertFalse(is_english_slug(''))


class SlugAliasTests(TestCase):
    def test_renaming_keeps_old_slug_resolvable(self):
        movie = Movie.objects.create(title='ذهن زیبا', slug='ذهن-زیبا')
        movie.slug = 'a-beautiful-mind-2001'
        movie.save()
        alias = CatalogSlugAlias.objects.get(kind='movie', old_slug='ذهن-زیبا')
        self.assertEqual(alias.object_id, movie.pk)
        self.assertEqual(canonical_slug(Movie, 'ذهن-زیبا'), 'a-beautiful-mind-2001')
        self.assertEqual(canonical_slug(Movie, 'a-beautiful-mind-2001'), 'a-beautiful-mind-2001')
        self.assertEqual(canonical_slug(Movie, 'nope'), 'nope')

    def test_update_fields_without_slug_skips_tracking(self):
        movie = Movie.objects.create(title='الف', slug='alef')
        movie.title = 'ب'
        with CaptureQueriesContext(connection) as ctx:
            movie.save(update_fields=['title'])
        self.assertFalse([q for q in ctx.captured_queries if q['sql'].startswith('SELECT "catalog_movie"."slug"')])

    def test_live_slug_wins_over_alias(self):
        movie = Movie.objects.create(title='الف', slug='old-one')
        movie.slug = 'new-one'
        movie.save()
        other = Movie.objects.create(title='ب', slug='old-one')
        self.assertEqual(canonical_slug(Movie, 'old-one'), 'old-one')
        # Renaming back to a former slug drops that alias so it cannot loop.
        movie.slug = 'old-two'
        movie.save()
        self.assertFalse(CatalogSlugAlias.objects.filter(old_slug='old-two').exists())
        self.assertTrue(other.pk)

    def test_series_aliases_are_separate(self):
        series = Series.objects.create(title='دوستان', slug='دوستان')
        series.slug = 'friends-1994'
        series.save()
        self.assertEqual(canonical_slug(Series, 'دوستان'), 'friends-1994')
        self.assertEqual(canonical_slug(Movie, 'دوستان'), 'دوستان')


@override_settings(CATALOG_AUTO_PUBLISH=False)
class IngestionEnglishSlugTests(TestCase):
    def test_new_import_gets_english_slug(self):
        movie, *_ = upsert_tmdb_movie(copy.deepcopy(MOVIE_DETAILS))
        self.assertEqual(movie.slug, 'automated-release-2026')

    def test_reimport_converts_persian_slug_and_keeps_alias(self):
        Movie.objects.create(title='انتشار خودکار', slug='انتشار-خودکار', tmdb_id=MOVIE_DETAILS['id'])
        movie, *_ = upsert_tmdb_movie(copy.deepcopy(MOVIE_DETAILS))
        self.assertEqual(movie.slug, 'automated-release-2026')
        self.assertEqual(canonical_slug(Movie, 'انتشار-خودکار'), 'automated-release-2026')

    def test_reimport_keeps_existing_english_slug(self):
        Movie.objects.create(title='انتشار خودکار', slug='automated-release', tmdb_id=MOVIE_DETAILS['id'])
        movie, *_ = upsert_tmdb_movie(copy.deepcopy(MOVIE_DETAILS))
        self.assertEqual(movie.slug, 'automated-release')
        self.assertFalse(CatalogSlugAlias.objects.exists())


class ApiAliasTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_old_persian_address_serves_current_movie(self):
        movie = Movie.objects.create(title='ذهن زیبا', slug='ذهن-زیبا', is_published=True)
        movie.slug = 'a-beautiful-mind-2001'
        movie.save()
        response = self.client.get('/api/movies/ذهن-زیبا/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slug'], 'a-beautiful-mind-2001')
        self.assertEqual(self.client.get('/api/movies/ذهن-زیبا/similar/').status_code, 200)

    def test_old_persian_address_serves_current_series(self):
        series = Series.objects.create(title='دوستان', slug='دوستان', is_published=True)
        series.slug = 'friends-1994'
        series.save()
        response = self.client.get('/api/series/دوستان/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slug'], 'friends-1994')

    def test_unknown_address_still_404s(self):
        self.assertEqual(self.client.get('/api/movies/no-such-film/').status_code, 404)


class EnglishifyCommandTests(TestCase):
    def test_dry_run_writes_nothing_and_apply_renames(self):
        movie = Movie.objects.create(
            title='ذهن زیبا', original_title='A Beautiful Mind', slug='ذهن-زیبا', release_year=2001, tmdb_id=453,
        )
        english = Movie.objects.create(title='الف', slug='already-english')
        series = Series.objects.create(title='دوستان', original_title='Friends', slug='دوستان', start_year=1994)
        out = StringIO()
        call_command('englishify_slugs', stdout=out)
        movie.refresh_from_db()
        self.assertEqual(movie.slug, 'ذهن-زیبا')
        self.assertIn('a-beautiful-mind-2001', out.getvalue())

        call_command('englishify_slugs', '--apply', stdout=StringIO())
        movie.refresh_from_db()
        series.refresh_from_db()
        english.refresh_from_db()
        self.assertEqual(movie.slug, 'a-beautiful-mind-2001')
        self.assertEqual(series.slug, 'friends-1994')
        self.assertEqual(english.slug, 'already-english')
        self.assertEqual(canonical_slug(Movie, 'ذهن-زیبا'), movie.slug)
        self.assertEqual(canonical_slug(Series, 'دوستان'), series.slug)
