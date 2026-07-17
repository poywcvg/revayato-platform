from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('engagement', '0002_like_rating_watchlistitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='useractivityevent',
            name='action',
            field=models.CharField(
                choices=[
                    ('view_movie', 'View Movie'),
                    ('view_series', 'View Series'),
                    ('view_episode', 'View Episode'),
                    ('play', 'Play'),
                    ('pause', 'Pause'),
                    ('watch_progress', 'Watch Progress'),
                    ('complete_watch', 'Complete Watch'),
                    ('like', 'Like'),
                    ('remove_like', 'Remove Like'),
                    ('dislike', 'Dislike'),
                    ('rate', 'Rate'),
                    ('add_to_watchlist', 'Add to Watchlist'),
                    ('remove_from_watchlist', 'Remove from Watchlist'),
                    ('search', 'Search'),
                    ('click_search_result', 'Click Search Result'),
                    ('filter_genre', 'Filter Genre'),
                    ('filter_year', 'Filter Year'),
                    ('filter_country', 'Filter Country'),
                    ('open_actor_page', 'Open Actor Page'),
                    ('open_director_page', 'Open Director Page'),
                    ('share', 'Share'),
                    ('comment', 'Comment'),
                    ('download_click', 'Download Click'),
                    ('trailer_watch', 'Trailer Watch'),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
    ]
