"""Read-only report: which of the three link providers each published title draws on.

A link names its provider in ``source`` when the path that stored it stamped one;
older rows only carry the CDN host, so the host decides for those.
"""

from collections import Counter
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand

from apps.catalog.provider_import.source_fill import PROVIDERS, link_provider


class Command(BaseCommand):
    help = 'Per provider: how many published titles carry its links, and how many carry none.'

    def add_arguments(self, parser):
        parser.add_argument('--hosts', type=int, default=0, help='Also list the top N untagged link hosts.')

    def handle(self, *args, **opts):
        from apps.catalog.models import Movie, Series

        for label, model in (('movies', Movie), ('series', Series)):
            per = Counter()
            combos = Counter()
            untagged_hosts = Counter()
            total = 0
            for links in model.objects.filter(is_published=True).values_list('download_links', flat=True).iterator(chunk_size=500):
                total += 1
                found = set()
                for item in links or []:
                    if not isinstance(item, dict) or not item.get('url'):
                        continue
                    provider = link_provider(item)
                    if provider:
                        found.add(provider)
                    if not str(item.get('source') or '').strip():
                        untagged_hosts[(urlsplit(str(item['url'])).hostname or '?').lower()] += 1
                for provider in found:
                    per[provider] += 1
                combos['+'.join(sorted(found)) or 'none'] += 1
            self.stdout.write(f'== {label}: {total} published')
            for provider in PROVIDERS:
                self.stdout.write(f'  {provider:9} {per[provider]:7}  ({per[provider] * 100 / max(total, 1):.1f}%)')
            for combo, count in combos.most_common():
                self.stdout.write(f'  combo {combo:26} {count:7}')
            for host, count in untagged_hosts.most_common(opts['hosts']):
                self.stdout.write(f'  untagged host {host:40} {count:7}')
