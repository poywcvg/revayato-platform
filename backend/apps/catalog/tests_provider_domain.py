"""The provider's domain is configuration — nothing may pin it in a pattern.

Film2Media moved from ``myf2m.info`` to ``myf2ms.top``. Every listing page kept
answering HTTP 200, so the importer reported success on every round while the
hard-coded domain in its link regexes matched **zero** items: measured on
production, ``movie listing page=1 items=0`` on every page, no new title created
in 24 hours, and 7,007 unpublished titles with no source. A failure that loud
should never have looked like success, so these tests fail the moment a host is
pinned again.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from apps.catalog.provider_import.catalog_lookup import _crawl_with_healed_path
from apps.catalog.provider_import.exceptions import ProviderImportError
from apps.catalog.provider_import.providers.myf2m_parser import SEARCH_CARD_RE_ALT


def _load_import_batch():
    """Load the crawler script by path; ``scripts/`` is not an importable package."""
    path = settings.BASE_DIR / 'scripts' / 'import_missing_myf2m_batch.py'
    spec = importlib.util.spec_from_file_location('import_missing_myf2m_batch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Whatever the provider calls itself this year.
HOSTS = ('https://www.myf2m.info', 'https://www.myf2ms.top', 'https://film2media.example')


#: Any host a provider has answered on. Substrings, matched case-insensitively.
PROVIDER_DOMAINS = ('myf2m.info', 'myf2ms.top', 'film2media.', 'dornatv.com', 'dlyar.top')

#: Every tree that is allowed to talk to a provider.
SCANNED_ROOTS = ('apps/catalog/provider_import', 'scripts')


def _compiled_pattern_literals():
    """Yield ``(file, lineno, pattern)`` for every regex literal in the scanned trees.

    Parsed with ``ast`` rather than grepped, so prose in comments and docstrings —
    including the ones explaining this very bug — cannot trip it, and only strings
    that actually reach ``re.compile`` are judged.
    """
    base = Path(settings.BASE_DIR)
    for root in SCANNED_ROOTS:
        for path in sorted((base / root).rglob('*.py')):
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except (OSError, SyntaxError):  # pragma: no cover - unreadable file
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == 'compile'):
                    continue
                if not (isinstance(func.value, ast.Name) and func.value.id == 're'):
                    continue
                for arg in node.args[:1]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        yield path.relative_to(base), arg.lineno, arg.value


class NoPatternPinsAProviderHostTests(SimpleTestCase):
    """Exhaustive by construction — this is the part that was missing.

    The tests below this one check named patterns in named modules. That guard
    passed for weeks while an identical copy of the bug sat in
    ``provider_import/myf2m_discover.py``: its item regexes still pinned
    ``myf2m.info``, matched nothing on the new domain, and the walk read that as
    "past the final page" and reported ``status: ok`` with zero items. Discovery
    from that provider was dead and every signal said it was fine.

    A guard that only covers the patterns someone remembered to list cannot catch
    the next copy. This one scans every regex literal in the provider trees, so a
    new module is covered the moment it is written.
    """

    def test_no_regex_literal_contains_a_provider_domain(self):
        offenders = [
            f'{path}:{lineno} pins a provider host in {pattern!r}'
            for path, lineno, pattern in _compiled_pattern_literals()
            if any(domain in pattern.lower() for domain in PROVIDER_DOMAINS)
        ]
        self.assertEqual(
            offenders, [],
            'The provider host is configuration (MYF2M_BASE_URL / DORNATV_BASE_URL). '
            'Match the *shape* of a link instead, e.g. '
            r'href="(?:https?://[^"/]+)?/(?P<id>\d+)/(?P<slug>[^"/]+)/". '
            'Offenders:\n' + '\n'.join(offenders),
        )

    def test_the_scan_actually_reaches_the_module_that_regressed(self):
        """Guard the guard: an empty scan would pass the test above vacuously."""
        scanned = {str(path) for path, _, _ in _compiled_pattern_literals()}
        self.assertIn('apps/catalog/provider_import/myf2m_discover.py', scanned)
        self.assertIn('scripts/import_missing_myf2m_batch.py', scanned)
        self.assertGreater(len(scanned), 5)


class ListingPatternTests(SimpleTestCase):
    def setUp(self):
        self.batch = _load_import_batch()

    def test_movie_links_match_on_any_host(self):
        for host in HOSTS:
            html = f'<a href="{host}/86902/korean-kanakaraju-2026/">…</a>'
            with self.subTest(host=host):
                match = self.batch.LISTING_MOVIE_RE.search(html)
                self.assertIsNotNone(match, f'movie listing regex missed {host}')
                self.assertEqual(match.group('id'), '86902')
                self.assertEqual(match.group('slug'), 'korean-kanakaraju-2026')

    def test_series_links_match_on_any_host(self):
        for host in HOSTS:
            html = f'<a href="{host}/series/clevatess/">…</a>'
            with self.subTest(host=host):
                match = self.batch.SERIES_SLUG_RE.search(html)
                self.assertIsNotNone(match, f'series listing regex missed {host}')
                self.assertEqual(match.group('slug'), 'clevatess')

    def test_relative_links_still_match(self):
        self.assertIsNotNone(self.batch.LISTING_MOVIE_RE.search('<a href="/81191/masters-2026/">'))
        self.assertIsNotNone(self.batch.SERIES_SLUG_RE.search('<a href="/series/neagley/">'))

    def test_search_card_fallback_matches_on_any_host(self):
        for host in HOSTS:
            with self.subTest(host=host):
                match = SEARCH_CARD_RE_ALT.search(f'<a href="{host}/81191/masters-2026/" class="x">')
                self.assertIsNotNone(match)
                self.assertTrue(match.group('href').endswith('/81191/masters-2026/'))


class HealedPathTests(SimpleTestCase):
    """A stored permalink that 301s to ``/profile/`` must not be a dead end."""

    def _connector(self, *, failures):
        connector = mock.Mock()
        seen = []

        def crawl(target, *, content_type):
            seen.append(target)
            if target in failures:
                raise ProviderImportError('redirected to profile', code='myf2m_page_required')
            return {'page_path': target}

        connector.crawl_download_links.side_effect = crawl
        connector.seen = seen
        return connector

    def test_re_resolves_a_dead_permalink(self):
        connector = self._connector(failures={'/old-persian-slug/'})
        result = _crawl_with_healed_path(
            connector,
            target='/old-persian-slug/',
            content_type='movie',
            resolve=lambda: '/81191/masters-2026/',
            explicit=True,
        )
        self.assertEqual(result['page_path'], '/81191/masters-2026/')
        self.assertEqual(connector.seen, ['/old-persian-slug/', '/81191/masters-2026/'])

    def test_gives_up_when_the_search_returns_the_same_dead_path(self):
        connector = self._connector(failures={'/old-persian-slug/'})
        with self.assertRaises(ProviderImportError):
            _crawl_with_healed_path(
                connector,
                target='/old-persian-slug/',
                content_type='movie',
                resolve=lambda: '/old-persian-slug/',
                explicit=True,
            )
        self.assertEqual(connector.seen, ['/old-persian-slug/'])

    def test_does_not_retry_a_target_the_search_itself_produced(self):
        """It already is the best guess; re-running the search would repeat it."""
        resolve = mock.Mock(return_value='/whatever/')
        connector = self._connector(failures={'/searched/'})
        with self.assertRaises(ProviderImportError):
            _crawl_with_healed_path(
                connector,
                target='/searched/',
                content_type='movie',
                resolve=resolve,
                explicit=False,
            )
        resolve.assert_not_called()

    def test_other_failures_are_not_healed(self):
        connector = mock.Mock()
        connector.crawl_download_links.side_effect = ProviderImportError(
            'no links', code='myf2m_links_empty',
        )
        resolve = mock.Mock(return_value='/other/')
        with self.assertRaises(ProviderImportError):
            _crawl_with_healed_path(
                connector,
                target='/x/',
                content_type='movie',
                resolve=resolve,
                explicit=True,
            )
        resolve.assert_not_called()


class IdentityCheckTests(SimpleTestCase):
    """A page found by title + year must actually be the title we hold.

    Two films sharing a name (a remake and its original) are exactly what a
    title + year search swaps, and a wrong page means every link on the card is
    someone else's film.
    """

    def _connector(self, pages):
        connector = mock.Mock()
        connector.seen = []

        def crawl(target, *, content_type):
            connector.seen.append(target)
            return {'page_path': target, **pages[target]}

        connector.crawl_download_links.side_effect = crawl
        return connector

    def _crawl(self, connector, target, **kwargs):
        return _crawl_with_healed_path(
            connector, target=target, content_type='movie', resolve=lambda: '', explicit=False, **kwargs,
        )

    def test_a_page_for_another_imdb_title_falls_through_to_the_next_search_hit(self):
        connector = self._connector({
            '/1/dune-1984/': {'imdb_ids': ['tt0087182']},
            '/2/dune-2021/': {'imdb_ids': ['tt1160419']},
        })
        result = self._crawl(
            connector, '/1/dune-1984/', expected_imdb='tt1160419',
            alternatives=lambda: ['/1/dune-1984/', '/2/dune-2021/'],
        )
        self.assertEqual(result['page_path'], '/2/dune-2021/')
        self.assertEqual(connector.seen, ['/1/dune-1984/', '/2/dune-2021/'])

    def test_a_movie_heading_a_decade_off_is_refused(self):
        connector = self._connector({'/1/dune/': {'imdb_ids': [], 'page_heading': 'Dune 1984'}})
        with self.assertRaises(ProviderImportError) as caught:
            self._crawl(connector, '/1/dune/', expected_imdb='tt1160419', expected_year=2021)
        self.assertEqual(caught.exception.code, 'myf2m_identity_mismatch')

    def test_a_title_containing_a_number_is_judged_by_its_release_year(self):
        connector = self._connector({'/1/br/': {'imdb_ids': [], 'page_heading': 'Blade Runner 2049 2017'}})
        result = self._crawl(connector, '/1/br/', expected_imdb='tt1856101', expected_year=2017)
        self.assertEqual(result['page_path'], '/1/br/')

    def test_a_one_year_difference_is_tolerated(self):
        """Festival premiere vs. general release is routinely a year apart."""
        connector = self._connector({'/1/x/': {'imdb_ids': [], 'page_heading': 'Film 2020'}})
        self.assertEqual(self._crawl(connector, '/1/x/', expected_year=2021)['page_path'], '/1/x/')

    def test_a_page_without_any_signal_is_let_through(self):
        connector = self._connector({'/1/x/': {}})
        result = self._crawl(connector, '/1/x/', expected_imdb='tt1160419', expected_year=2021)
        self.assertEqual(result['page_path'], '/1/x/')

    def test_a_matching_imdb_link_wins_over_the_heading(self):
        connector = self._connector({'/1/x/': {'imdb_ids': ['tt1160419'], 'page_heading': 'Dune 1984'}})
        result = self._crawl(connector, '/1/x/', expected_imdb='tt1160419', expected_year=2021)
        self.assertEqual(result['page_path'], '/1/x/')
