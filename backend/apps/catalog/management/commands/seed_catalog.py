from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import Country, Episode, Genre, Movie, Season, Series
from apps.catalog.genres import GENRES


def clean_data(model, data):
    fields = {field.name for field in model._meta.fields}
    return {key: value for key, value in data.items() if key in fields}


class Command(BaseCommand):
    help = 'Seed initial catalog data'

    def handle(self, *args, **options):
        # Persist only an object key.  The configured media CDN is applied by
        # serializers and playback payloads at response time.
        stream_url = 'movies/demo/hls/master.m3u8'
        genres = {
            slug: Genre.objects.update_or_create(
                slug=slug,
                defaults={
                    'title': title,
                    'description': description,
                    'is_featured': is_featured,
                },
            )[0]
            for slug, title, description, is_featured in GENRES
        }
        action = genres['action']
        drama = genres['drama']
        sci_fi = genres['sci-fi']
        crime = genres['crime']
        thriller = genres['thriller']
        countries = {
            code: Country.objects.get_or_create(code=code, defaults={'name': name})[0]
            for code, name in {
                'US': 'United States',
                'GB': 'United Kingdom',
                'DE': 'Germany',
                'CA': 'Canada',
            }.items()
        }

        movies_data = [
            {
                'title': 'Shadow Protocol',
                'description': 'A former intelligence analyst discovers a hidden surveillance network and must expose it before he disappears.',
                'release_year': 2024,
                'country_code': 'US',
                'language': 'English',
                'age_rating': '18+',
                'imdb_rating': 7.8,
                'video_url': stream_url,
                'trailer_url': stream_url,
                'has_subtitle': True,
                'is_uncensored': True,
                'content_warnings': ['Strong violence', 'Intense situations'],
                'is_published': True,
                'is_featured': True,
                'genres': [action, thriller],
            },
            {
                'title': 'Silent Orbit',
                'description': 'A space engineer wakes up alone on a damaged orbital station with no memory of the last 48 hours.',
                'release_year': 2023,
                'country_code': 'GB',
                'language': 'English',
                'age_rating': '15+',
                'imdb_rating': 8.1,
                'video_url': stream_url,
                'trailer_url': stream_url,
                'is_dubbed': True,
                'has_subtitle': True,
                'content_warnings': ['Flashing lights'],
                'is_published': True,
                'is_featured': True,
                'genres': [sci_fi, drama],
            },
            {
                'title': 'Concrete Nights',
                'description': 'A detective follows a money trail through the city and uncovers a criminal system protected by powerful people.',
                'release_year': 2022,
                'country_code': 'DE',
                'language': 'German',
                'age_rating': '18+',
                'imdb_rating': 7.5,
                'video_url': stream_url,
                'trailer_url': stream_url,
                'has_subtitle': True,
                'is_uncensored': True,
                'content_warnings': ['Strong violence', 'Substance use'],
                'is_published': True,
                'genres': [crime, drama, thriller],
            },
        ]

        for data in movies_data:
            genres = data.pop('genres')
            country = countries[data.pop('country_code')]
            slug = slugify(data['title'])
            movie, _ = Movie.objects.update_or_create(
                slug=slug,
                defaults=clean_data(Movie, {**data, 'slug': slug})
            )
            movie.genres.set(genres)
            movie.countries.set([country])

        series_data = [
            {
                'title': 'Red Signal',
                'description': 'A cybercrime unit tracks a mysterious signal used to coordinate high-level digital attacks.',
                'start_year': 2024,
                'end_year': None,
                'country_code': 'US',
                'language': 'English',
                'age_rating': '18+',
                'imdb_rating': 8.4,
                'trailer_url': stream_url,
                'has_subtitle': True,
                'is_uncensored': True,
                'content_warnings': ['Strong violence', 'Cybercrime themes'],
                'is_published': True,
                'is_featured': True,
                'genres': [crime, thriller],
                'episodes': [
                    {'title': 'The First Trace', 'episode_number': 1, 'duration_minutes': 48},
                    {'title': 'Dead Node', 'episode_number': 2, 'duration_minutes': 51},
                    {'title': 'Root Access', 'episode_number': 3, 'duration_minutes': 46},
                ],
            },
            {
                'title': 'After Earthfall',
                'description': 'Years after a global disaster, isolated communities fight for control of the last stable regions.',
                'start_year': 2023,
                'end_year': None,
                'country_code': 'CA',
                'language': 'English',
                'age_rating': '18+',
                'imdb_rating': 7.9,
                'trailer_url': stream_url,
                'is_dubbed': True,
                'has_subtitle': True,
                'content_warnings': ['Strong violence', 'Post-disaster themes'],
                'is_published': True,
                'genres': [sci_fi, drama, action],
                'episodes': [
                    {'title': 'Ash Line', 'episode_number': 1, 'duration_minutes': 55},
                    {'title': 'The Northern Gate', 'episode_number': 2, 'duration_minutes': 52},
                ],
            },
        ]

        for data in series_data:
            genres = data.pop('genres')
            episodes = data.pop('episodes')
            country = countries[data.pop('country_code')]
            slug = slugify(data['title'])

            series, _ = Series.objects.update_or_create(
                slug=slug,
                defaults=clean_data(Series, {**data, 'slug': slug})
            )
            series.genres.set(genres)
            series.countries.set([country])

            season, _ = Season.objects.update_or_create(
                series=series,
                season_number=1,
                defaults=clean_data(Season, {
                    'series': series,
                    'season_number': 1,
                    'title': 'Season 1',
                    'release_year': data.get('start_year'),
                    'episode_count': len(episodes),
                    'is_published': True,
                })
            )

            for episode_data in episodes:
                Episode.objects.update_or_create(
                    season=season,
                    episode_number=episode_data['episode_number'],
                    defaults=clean_data(Episode, {
                        **episode_data,
                        'season': season,
                        'video_url': stream_url,
                        'is_published': True,
                    })
                )

        self.stdout.write(self.style.SUCCESS('Catalog seed data created successfully.'))
