"""Tests for the admin catalog import job: provider selection + year window.

The heavy phases are faked; what matters here is that the job runs the providers
the admin asked for, threads the year window into every phase, and reports both
per-provider and flat totals.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.catalog.models import ProviderImportJob, ProviderSource
from apps.catalog.provider_import.tasks import run_catalog_year_import_task

PHASES = 'scripts.import_2026_full'


def _row(**kwargs):
    row = {'movies_created': 0, 'series_created': 0, 'skipped_existing': 0, 'rounds': 1}
    row.update(kwargs)
    return row


class CatalogYearImportTaskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.provider = ProviderSource.objects.create(
            name='Dornatv', slug='dornatv',
            provider_type=ProviderSource.ProviderType.API,
            base_url='https://dornatv.com',
        )

    def _job(self, **params):
        payload = {
            'content_type': 'both', 'discover': True, 'enrich': False, 'softsub': False,
            'episode_metadata': False, 'providers': ['dornatv', 'myf2m'],
            'year_start': None, 'year_end': None, 'delay': 0.1,
            'dornatv_rounds': 1, 'myf2m_rounds': 1, 'myf2m_pages_per_round': 5,
        }
        payload.update(params)
        return ProviderImportJob.objects.create(
            provider=self.provider, content_type='both',
            mode=ProviderImportJob.Mode.IMPORT_MISSING, params=payload,
        )

    def _run(self, job, *, dornatv=None, myf2m=None):
        with patch(f'{PHASES}.report', return_value={'movies_total': 0}), \
                patch(f'{PHASES}.phase_dornatv_missing', return_value=dornatv or _row()) as dorna, \
                patch(f'{PHASES}.phase_myf2m_missing', return_value=myf2m or _row()) as f2m, \
                patch(f'{PHASES}.phase_enrich', return_value={}), \
                patch(f'{PHASES}.phase_softsub_queue', return_value={}):
            summary = run_catalog_year_import_task(str(job.id))
        return summary, dorna, f2m
