from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from apps.catalog.trending import featured_score, popular_score, trending_score


class _FakeTitle:
    def __init__(self, **kwargs):
        self.pk = kwargs.get('pk', kwargs.get('id', 1))
        self.id = self.pk
        self.view_count = kwargs.get('view_count', 0)
        self.like_count = kwargs.get('like_count', 0)
        self.popularity = kwargs.get('popularity', 0)
        self.is_featured = kwargs.get('is_featured', False)
        self.is_recommended = kwargs.get('is_recommended', False)
        self.is_dubbed = kwargs.get('is_dubbed', False)
        self.has_subtitle = kwargs.get('has_subtitle', False)
        self.download_links = kwargs.get('download_links', [])
        self.subtitle_tracks = kwargs.get('subtitle_tracks', [])
        self.imdb_rating = kwargs.get('imdb_rating', None)
        self.tmdb_rating = kwargs.get('tmdb_rating', None)
        self.imdb_rank = kwargs.get('imdb_rank', None)
        self.poster_path = kwargs.get('poster_path', '/x.jpg')
        self.poster = kwargs.get('poster', None)
        self.poster_external_url = kwargs.get('poster_external_url', '')
        self.backdrop = kwargs.get('backdrop', None)
        self.backdrop_path = kwargs.get('backdrop_path', '')
        self.backdrop_external_url = kwargs.get('backdrop_external_url', '')
        self.download_key = kwargs.get('download_key', '')
        self.updated_at = kwargs.get('updated_at', timezone.now())
        self.created_at = kwargs.get('created_at', timezone.now())


class TrendingScoreTests(SimpleTestCase):
    def test_playable_dub_softsub_beats_bare_popularity(self):
        now = timezone.now()
        bare = _FakeTitle(pk=1, popularity=200, view_count=10, updated_at=now, created_at=now - timedelta(days=20))
        playable = _FakeTitle(
            pk=2,
            popularity=40,
            view_count=12,
            is_dubbed=True,
            has_subtitle=True,
            download_links=[{'url': 'https://cdn.example/a.mp4'}],
            subtitle_tracks=[{'key': 'x.vtt'}],
            updated_at=now,
            created_at=now - timedelta(days=2),
        )
        self.assertGreater(trending_score(playable, now=now), trending_score(bare, now=now))

    def test_fresh_rising_title_beats_stale_featured_flag(self):
        now = timezone.now()
        rising = _FakeTitle(
            pk=3,
            view_count=80,
            like_count=12,
            popularity=25,
            is_dubbed=True,
            has_subtitle=True,
            created_at=now - timedelta(days=2),
            updated_at=now,
        )
        stale_featured = _FakeTitle(
            pk=4,
            is_featured=True,
            popularity=90,
            view_count=40,
            created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=40),
        )
        self.assertGreater(
            trending_score(rising, now=now, recent_hits=6),
            trending_score(stale_featured, now=now, recent_hits=0),
        )

    def test_recent_hits_boost_trending(self):
        now = timezone.now()
        quiet = _FakeTitle(pk=5, view_count=50, popularity=40, created_at=now - timedelta(days=5))
        hot = _FakeTitle(pk=6, view_count=50, popularity=40, created_at=now - timedelta(days=5))
        self.assertGreater(
            trending_score(hot, now=now, recent_hits=18),
            trending_score(quiet, now=now, recent_hits=0),
        )

    def test_featured_score_prefers_editorial_picks(self):
        now = timezone.now()
        curated = _FakeTitle(
            pk=7,
            is_recommended=True,
            imdb_rating=7.8,
            imdb_rank=40,
            popularity=20,
            created_at=now,
            is_dubbed=True,
        )
        plain = _FakeTitle(pk=8, popularity=90, view_count=40, created_at=now)
        self.assertGreater(featured_score(curated, now=now), featured_score(plain, now=now))

    def test_featured_score_rewards_top_imdb_rank(self):
        now = timezone.now()
        classic = _FakeTitle(pk=9, imdb_rating=8.6, imdb_rank=12, popularity=30, created_at=now - timedelta(days=400))
        mid = _FakeTitle(pk=10, imdb_rating=7.0, popularity=80, view_count=200, created_at=now - timedelta(days=30))
        self.assertGreater(featured_score(classic, now=now), featured_score(mid, now=now))

    def test_popular_score_weights_engagement(self):
        now = timezone.now()
        loved = _FakeTitle(pk=11, view_count=900, like_count=120, popularity=30, updated_at=now)
        quiet = _FakeTitle(pk=12, view_count=5, like_count=0, popularity=120, updated_at=now)
        self.assertGreater(popular_score(loved, now=now), popular_score(quiet, now=now))

    def test_dubbed_score_prefers_dubbed_playable(self):
        from apps.catalog.trending import dubbed_score

        now = timezone.now()
        dubbed = _FakeTitle(
            pk=21,
            is_dubbed=True,
            has_subtitle=True,
            download_links=[{'url': 'https://cdn.example/a.mp4'}],
            view_count=40,
            popularity=20,
            created_at=now - timedelta(days=3),
        )
        subtitled = _FakeTitle(
            pk=22,
            is_dubbed=False,
            has_subtitle=True,
            view_count=200,
            popularity=90,
            created_at=now - timedelta(days=3),
        )
        self.assertGreater(dubbed_score(dubbed, now=now), dubbed_score(subtitled, now=now))
        self.assertLess(dubbed_score(subtitled, now=now), -1e6)

    def test_diversify_ranked_caps_genre_dominance(self):
        from apps.catalog.trending import diversify_ranked

        class G:
            def __init__(self, slug):
                self.slug = slug

        class Item:
            def __init__(self, pk, slug):
                self.pk = pk
                self._genres = [G(slug)]

            @property
            def genres(self):
                class Manager:
                    def __init__(self, rows):
                        self._rows = rows

                    def all(self):
                        return self._rows

                return Manager(self._genres)

        ranked = [Item(i, 'action' if i < 5 else 'drama') for i in range(8)]
        picked = diversify_ranked(ranked, limit=4, max_per_genre=2)
        action_count = sum(1 for item in picked if item._genres[0].slug == 'action')
        drama_count = sum(1 for item in picked if item._genres[0].slug == 'drama')
        self.assertLessEqual(action_count, 2)
        self.assertLessEqual(drama_count, 2)
        self.assertEqual(len(picked), 4)

    def test_rail_rotation_meta_is_stable_in_slot(self):
        from apps.catalog.trending import rail_rotation_meta

        now = timezone.now().replace(hour=3, minute=10, second=0, microsecond=0)
        a = rail_rotation_meta(now)
        b = rail_rotation_meta(now.replace(minute=50))
        self.assertEqual(a['bucket'], b['bucket'])
        self.assertEqual(a['focus_genre'], b['focus_genre'])
        later = rail_rotation_meta(now.replace(hour=10))
        self.assertNotEqual(a['bucket'], later['bucket'])
