from django.test import SimpleTestCase
from django.urls import resolve, reverse
from urllib.parse import unquote

from config.converters import UnicodeSlugConverter


class UnicodeSlugConverterTests(SimpleTestCase):
    def test_regex_accepts_persian_slug(self):
        converter = UnicodeSlugConverter()
        self.assertRegex('ذهن-زیبا', f'^{converter.regex}$')
        self.assertRegex('a-beautiful-mind', f'^{converter.regex}$')

    def test_movie_detail_route_resolves_persian_slug(self):
        match = resolve('/api/movies/ذهن-زیبا/')
        self.assertEqual(match.url_name, 'movie_detail')
        self.assertEqual(match.kwargs['slug'], 'ذهن-زیبا')

    def test_reverse_keeps_unicode_slug(self):
        url = reverse('movie_detail', kwargs={'slug': 'ذهن-زیبا'})
        self.assertEqual(unquote(url), '/api/movies/ذهن-زیبا/')
