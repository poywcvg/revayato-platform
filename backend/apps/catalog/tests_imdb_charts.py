"""Smoke tests for IMDb Top-250 chart ranking helpers."""

from django.test import SimpleTestCase

from apps.catalog.imdb_charts import ImdbChartTitle, _rank_chart, _weighted_rating


class ImdbChartsTests(SimpleTestCase):
    def test_weighted_rating_pulls_low_votes_toward_mean(self):
        high_votes = _weighted_rating(9.0, 1_000_000, mean=7.0, min_votes=25_000)
        low_votes = _weighted_rating(9.0, 1_000, mean=7.0, min_votes=25_000)
        self.assertGreater(high_votes, low_votes)
        self.assertAlmostEqual(low_votes, 7.0769, places=3)

    def test_rank_chart_orders_by_weighted_score(self):
        ranked = _rank_chart(
            [
                {
                    'imdb_id': 'tt1',
                    'title_type': 'movie',
                    'primary_title': 'A',
                    'original_title': 'A',
                    'start_year': 2000,
                    'average_rating': 9.2,
                    'num_votes': 2_000_000,
                },
                {
                    'imdb_id': 'tt2',
                    'title_type': 'movie',
                    'primary_title': 'B',
                    'original_title': 'B',
                    'start_year': 2001,
                    'average_rating': 9.5,
                    'num_votes': 30_000,
                },
            ],
            limit=2,
            min_votes=25_000,
        )
        self.assertEqual(len(ranked), 2)
        self.assertIsInstance(ranked[0], ImdbChartTitle)
        self.assertEqual(ranked[0].imdb_id, 'tt1')
        self.assertEqual(ranked[0].rank, 1)
        self.assertEqual(ranked[1].imdb_id, 'tt2')
