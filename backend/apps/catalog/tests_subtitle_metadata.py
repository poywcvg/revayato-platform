"""Tests for metadata-aware subtitle page verification (subtitle_metadata)."""

from django.test import TestCase

from .models import Actor, Director, Genre, Movie, MovieActor
from .subtitle_metadata import build_title_identity, evaluate_subtitle_page


def _movie(**kwargs):
    defaults = {'title': 'Dune', 'slug': 'dune', 'release_year': 2021, 'imdb_id': 'tt1160419'}
    defaults.update(kwargs)
    return Movie.objects.create(**defaults)


class BuildTitleIdentityTests(TestCase):
    def test_pulls_cast_director_genre_from_orm(self):
        movie = _movie()
        villeneuve = Director.objects.create(
            name='دنی ویلنوو', original_name='Denis Villeneuve', slug='denis-villeneuve',
        )
        movie.directors.add(villeneuve)
        chalamet = Actor.objects.create(
            name='تیموتی شالامی', original_name='Timothée Chalamet', slug='timothee-chalamet',
        )
        MovieActor.objects.create(movie=movie, actor=chalamet, order=0)
        genre, _ = Genre.objects.get_or_create(title='ژانر تستی الف', defaults={'slug': 'test-genre-a'})
        movie.genres.add(genre)

        identity = build_title_identity(
            movie, title='Dune', year=2021, imdb_id='tt1160419',
        )

        self.assertEqual(identity.year, 2021)
        self.assertIn('chalamet', identity.cast_terms)
        self.assertIn('تیموتی شالامی', identity.cast_fa)
        self.assertIn('villeneuve', identity.director_terms)
        self.assertIn('ژانر تستی الف', identity.genre_terms)

    def test_missing_metadata_degrades_to_title_year_imdb(self):
        movie = _movie(imdb_id='')
        identity = build_title_identity(movie, title='Dune', year=2021, imdb_id='')
        self.assertEqual(identity.cast_terms, ())
        self.assertFalse(identity.has_people)


class EvaluatePageTests(TestCase):
    def setUp(self):
        movie = _movie()
        chalamet = Actor.objects.create(
            name='تیموتی شالامی', original_name='Timothée Chalamet', slug='timothee-chalamet',
        )
        MovieActor.objects.create(movie=movie, actor=chalamet, order=0)
        genre, _ = Genre.objects.get_or_create(title='ژانر تستی ب', defaults={'slug': 'test-genre-b'})
        movie.genres.add(genre)
        self.identity = build_title_identity(movie, title='Dune', year=2021, imdb_id='tt1160419')

    def test_imdb_conflict_rejects(self):
        verdict = evaluate_subtitle_page(self.identity, 'Some page', page_imdb='tt0087182')
        self.assertTrue(verdict.reject)
        self.assertIn('imdb-conflict', verdict.reasons)

    def test_year_conflict_without_imdb_rejects(self):
        # The 1984 Lynch adaptation must not win for the 2021 title.
        verdict = evaluate_subtitle_page(self.identity, 'Dune 1984 David Lynch', page_year=1984)
        self.assertTrue(verdict.reject)
        self.assertIn('year-conflict', verdict.reasons)

    def test_cast_and_year_confirm(self):
        html = 'زیرنویس فارسی Dune 2021 با بازی Timothee Chalamet'
        verdict = evaluate_subtitle_page(self.identity, html, page_year=2021)
        self.assertFalse(verdict.reject)
        self.assertTrue(verdict.confirmed)
        self.assertTrue(any(r.startswith('cast:') for r in verdict.reasons))

    def test_bare_title_page_is_unconfirmed_fallback(self):
        verdict = evaluate_subtitle_page(self.identity, 'دانلود زیرنویس فارسی', page_year=None)
        self.assertFalse(verdict.reject)
        self.assertFalse(verdict.confirmed)

    def test_imdb_match_confirms_even_with_offbyone_year(self):
        html = "<a href='https://imdb.com/title/tt1160419/'>Dune</a> 2020"
        verdict = evaluate_subtitle_page(self.identity, html, page_imdb='tt1160419', page_year=2020)
        self.assertFalse(verdict.reject)
        self.assertTrue(verdict.confirmed)
        self.assertIn('imdb', verdict.reasons)
