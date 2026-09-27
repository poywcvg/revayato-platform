from django.test import SimpleTestCase, TestCase

from . import search_suggest
from .models import Actor, Movie, Series


def movie(title, slug, **kwargs):
    kwargs.setdefault('is_published', True)
    return Movie.objects.create(title=title, slug=slug, **kwargs)


class SearchSuggestTests(TestCase):
    url = '/api/search/suggest/'

    def get(self, q, **params):
        response = self.client.get(self.url, {'q': q, **params})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def slugs(self, payload, key='movies'):
        return [item['slug'] for item in payload[key]]

    def test_every_keystroke_narrows_to_the_title(self):
        movie('Interstellar', 'interstellar-2014', original_title='Interstellar', release_year=2014)
        movie('Inception', 'inception-2010', release_year=2010)

        self.assertEqual(set(self.slugs(self.get('I'))), {'inception-2010', 'interstellar-2014'})
        self.assertEqual(self.slugs(self.get('Int')), ['interstellar-2014'])
        payload = self.get('Interst')
        self.assertEqual(payload['match_type'], 'direct')
        self.assertEqual(payload['movies'][0]['title'], 'Interstellar')

    def test_one_letter_only_matches_word_starts(self):
        movie('Big Fish', 'big-fish')
        movie('Fargo', 'fargo')

        # A title starting with the letter outranks one where a later word does.
        self.assertEqual(self.slugs(self.get('f')), ['fargo', 'big-fish'])
        # "i" appears inside "Big Fish" but starts no word: no suggestion.
        self.assertEqual(self.slugs(self.get('i')), [])

    def test_exact_title_beats_a_more_popular_prefix_match(self):
        movie('Upgrade', 'upgrade', view_count=900, popularity=90)
        movie('Up', 'up', view_count=5, popularity=1)

        self.assertEqual(self.slugs(self.get('up')), ['up', 'upgrade'])

    def test_popularity_breaks_ties_within_a_tier(self):
        movie('Dark Water', 'dark-water', view_count=1)
        movie('Dark', 'dark-series-film', view_count=0)
        movie('Darkest Hour', 'darkest-hour', view_count=500)

        # "Dark" is exact; the two prefix matches follow by views.
        self.assertEqual(self.slugs(self.get('dark')), ['dark-series-film', 'darkest-hour', 'dark-water'])

    def test_persian_keyboard_variants_and_zwnj(self):
        movie('کیان', 'kian')
        movie('می‌خواهم زنده بمانم', 'i-want-to-live')

        self.assertEqual(self.slugs(self.get('كي')), ['kian'])
        self.assertEqual(self.slugs(self.get('میخواهم')), ['i-want-to-live'])
        self.assertEqual(self.slugs(self.get('می خو')), ['i-want-to-live'])

    def test_english_name_and_spacing_variants_find_persian_titles(self):
        movie('مرد عنکبوتی', 'spider-man-2002', original_title='Spider-Man', release_year=2002)

        self.assertEqual(self.slugs(self.get('spiderman')), ['spider-man-2002'])
        self.assertEqual(self.slugs(self.get('spider m')), ['spider-man-2002'])
        self.assertEqual(self.slugs(self.get('عنکب')), ['spider-man-2002'])

    def test_drafts_are_never_suggested(self):
        movie('Hidden Draft', 'hidden-draft', is_published=False)

        self.assertEqual(self.slugs(self.get('hidden')), [])

    def test_year_in_the_box_filters_titles(self):
        movie('تلماسه', 'dune-2021', original_title='Dune', release_year=2021)
        movie('تلماسه', 'dune-1984', original_title='Dune', release_year=1984)

        payload = self.get('تلماسه ۲۰۲۱')
        self.assertEqual(payload['year'], 2021)
        self.assertEqual(self.slugs(payload), ['dune-2021'])
        self.assertEqual(set(self.slugs(self.get('dune'))), {'dune-2021', 'dune-1984'})

    def test_series_and_actors_are_suggested(self):
        Series.objects.create(title='بریکینگ بد', original_title='Breaking Bad', slug='breaking-bad', is_published=True)
        Actor.objects.create(name='تیموتی شالامه', original_name='Timothee Chalamet', slug='timothee-chalamet')

        self.assertEqual(self.slugs(self.get('break'), 'series'), ['breaking-bad'])
        self.assertEqual(self.slugs(self.get('chal'), 'actors'), ['timothee-chalamet'])
        self.assertEqual(self.slugs(self.get('break', type='movie'), 'series'), [])

    def test_typo_falls_back_to_similar_titles(self):
        movie('Interstellar', 'interstellar', original_title='Interstellar', popularity=90)
        movie('Unrelated title', 'unrelated-title', popularity=100)

        payload = self.get('Interstelar', type='movie')
        self.assertEqual(payload['match_type'], 'similar')
        self.assertEqual(self.slugs(payload), ['interstellar'])

    def test_empty_query_is_a_cheap_empty_answer(self):
        payload = self.get('   ')
        self.assertEqual(payload['match_type'], 'none')
        self.assertEqual(payload['movies'], [])

    def test_payload_cards_match_the_full_search_shape(self):
        movie('Interstellar', 'interstellar', release_year=2014)

        suggest = self.get('Interstellar')['movies'][0]
        full = self.client.get('/api/search/', {'q': 'Interstellar'}).json()['movies'][0]
        self.assertEqual(set(suggest), set(full))


class SuggestRankTests(SimpleTestCase):
    def test_rank_orders_by_tier_then_views(self):
        docs = [
            search_suggest._make_doc(1, ('Heat', '', 'heat'), 1995, (10, 0.0)),
            search_suggest._make_doc(2, ('Heatwave', '', 'heatwave'), 2020, (99, 0.0)),
            search_suggest._make_doc(3, ('The Heat', '', 'the-heat'), 2013, (500, 0.0)),
            search_suggest._make_doc(4, ('Cheaters', '', 'cheaters'), 2000, (999, 0.0)),
        ]
        ids, exact = search_suggest.rank(docs, 'heat', year=None, limit=10)
        # exact > prefix > word-prefix > contains
        self.assertEqual(ids, [1, 2, 3, 4])
        self.assertTrue(exact)

        ids, exact = search_suggest.rank(docs, 'heat', year=2013, limit=10)
        self.assertEqual(ids, [3])
        self.assertFalse(exact)
