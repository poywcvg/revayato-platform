"""Regression tests for the automatic support / content-report fixing loop.

Each test pins a failure that was observed in production:

* the playback remediation read the wrong result key, so a fix never resolved;
* an episode report was judged at *series* level (one HLS episode made the whole
  show "playable" while the reported episode was still a bare ``.mkv``);
* an episode ticket's ``related_title`` ("Çukur — قسمت 27") never resolved to a
  catalog row, so a fixed ticket stayed ``in_progress`` forever;
* a flat 12-attempt cap abandoned tickets after ~6 hours;
* the report drain was never scheduled and its rows were never re-tried.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog import content_remediation as remediation
from apps.catalog.content_reports import record_content_issue_report
from apps.catalog.models import ContentIssueReport, Episode, Movie, Season, Series
from apps.engagement import services, support_automation as automation
from apps.engagement.models import SupportTicket

User = get_user_model()

MKV = [{'url': 'https://cdn.example/film.1080p.mkv', 'quality': '1080p'}]
MP4 = [{'url': 'https://cdn.example/film.1080p.mp4', 'quality': '1080p'}]


def _age(obj, **delta):
    """Backdate ``updated_at`` (auto_now, so it needs a queryset update)."""
    type(obj).objects.filter(pk=obj.pk).update(updated_at=timezone.now() - timedelta(**delta))
    obj.refresh_from_db()


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='viewer', email='v@example.com', password='x12345678')

    def movie(self, links=MKV):
        return Movie.objects.create(title='فیلم', slug='film', is_published=True, download_links=links)

    def series_with_episodes(self, ep2_url='https://cdn.example/s1e2.mkv'):
        series = Series.objects.create(title='سریال', slug='serial', is_published=True)
        season = Season.objects.create(series=series, season_number=1, title='S1', is_published=True)
        good = Episode.objects.create(
            season=season, episode_number=1, title='E1', is_published=True,
            video_url='https://cdn.example/s1e1.mp4',
        )
        bad = Episode.objects.create(
            season=season, episode_number=2, title='E2', is_published=True, video_url=ep2_url,
        )
        return series, good, bad

    def report(self, obj, *, episode=None, **kw):
        defaults = dict(
            content_type='movie' if isinstance(obj, Movie) else 'series',
            object_id=obj.pk, episode_id=episode.pk if episode else 0,
            problem_type='playback', slug=obj.slug, title=obj.title, reporter=self.user,
        )
        defaults.update(kw)
        return ContentIssueReport.objects.create(**defaults)


class PlaybackRemediationTests(_Base):
    def test_refreshed_outcome_resolves_report(self):
        """``remediate`` answers under ``outcome``; reading ``status`` left every
        fixed report ``queued`` forever."""
        movie = self.movie(MKV)
        report = self.report(movie)

        def fake_remediate(obj):
            obj.download_links = MP4
            obj.save(update_fields=['download_links'])
            return {'outcome': 'refreshed', 'codes': {}, 'diag_after': {'reason': ''}}

        with patch('apps.catalog.playback_sources.remediate', side_effect=fake_remediate):
            out = remediation.remediate_report(report)

        self.assertEqual(out['status'], 'resolved')
        report.refresh_from_db()
        self.assertEqual(report.status, 'resolved')
        self.assertIsNotNone(report.remediated_at)

    def test_no_network_when_already_playable(self):
        movie = self.movie(MP4)
        report = self.report(movie)
        with patch('apps.catalog.playback_sources.remediate') as crawl:
            out = remediation.remediate_report(report)
        crawl.assert_not_called()
        self.assertEqual(out['status'], 'resolved')

    def test_unavailable_when_only_unsafe_upstream(self):
        movie = self.movie(MKV)
        report = self.report(movie)
        with patch('apps.catalog.playback_sources.remediate', return_value={
            'outcome': 'unavailable', 'codes': {}, 'diag_after': {'reason': 'mkv_only'},
        }):
            out = remediation.remediate_report(report)
        self.assertEqual(out['status'], 'unavailable')
        self.assertIn('mkv_only', out['result'])

    def test_provider_error_is_queued_for_retry(self):
        report = self.report(self.movie(MKV))
        with patch('apps.catalog.playback_sources.remediate', return_value={
            'outcome': 'provider_error', 'codes': {}, 'diag_after': {},
        }):
            out = remediation.remediate_report(report)
        self.assertEqual(out['status'], 'queued')

    def test_episode_report_judged_on_the_episode_not_the_series(self):
        """Series looks playable (episode 1 has HLS) but the reported episode 2 is
        still an .mkv — it must NOT be closed as fixed."""
        series, _good, bad = self.series_with_episodes()
        report = self.report(series, episode=bad)

        self.assertFalse(remediation.recheck_report(report))
        report.refresh_from_db()
        self.assertEqual(report.status, 'open')

        Episode.objects.filter(pk=bad.pk).update(video_url='https://cdn.example/s1e2.mp4')
        self.assertTrue(remediation.recheck_report(report))
        report.refresh_from_db()
        self.assertEqual(report.status, 'resolved')

    def test_episode_remediation_reevaluates_after_crawl(self):
        """A series-level ``refreshed`` verdict must not resolve an episode whose
        own source is still unsafe."""
        series, _good, bad = self.series_with_episodes()
        report = self.report(series, episode=bad)
        with patch('apps.catalog.playback_sources.remediate', return_value={
            'outcome': 'refreshed', 'codes': {}, 'diag_after': {'reason': ''},
        }):
            out = remediation.remediate_report(report)
        self.assertEqual(out['status'], 'unavailable')


class ReportDrainTests(_Base):
    def test_sync_resolves_reports_whose_target_now_plays(self):
        stale = self.report(self.movie(MP4), status='queued')
        broken = self.report(Movie.objects.create(title='B', slug='b', is_published=True, download_links=MKV),
                             status='queued')
        stats = remediation.sync_reports_with_reality()
        self.assertEqual(stats['resolved_report_ids'], [stale.pk])
        broken.refresh_from_db()
        self.assertEqual(broken.status, 'queued')

    def test_sync_also_revives_unavailable_and_needs_review(self):
        movie = self.movie(MP4)
        unavailable = self.report(movie, status='unavailable')
        stats = remediation.sync_reports_with_reality()
        self.assertIn(unavailable.pk, stats['resolved_report_ids'])

    def test_backoff_holds_a_recent_attempt_back(self):
        report = self.report(self.movie(MKV), status='queued', attempts=1)
        with patch.object(remediation, 'remediate_report') as run:
            stats = remediation.remediate_open_reports()
        run.assert_not_called()
        self.assertEqual(stats['processed'], 0)

        _age(report, minutes=11)  # past the 10-minute step
        with patch.object(remediation, 'remediate_report', return_value={
            'report_id': report.pk, 'status': 'queued',
        }) as run:
            stats = remediation.remediate_open_reports()
        run.assert_called_once()
        self.assertEqual(stats['processed'], 1)

    def test_exhausted_report_is_handed_to_a_human(self):
        report = self.report(self.movie(MKV), status='queued', attempts=remediation.MAX_AUTO_ATTEMPTS)
        stats = remediation.remediate_open_reports()
        self.assertEqual(stats['exhausted'], 1)
        report.refresh_from_db()
        self.assertEqual((report.status, report.remediation_action), ('needs_review', 'auto_exhausted'))
        # …and stays out of the auto queue afterwards.
        self.assertEqual(remediation.remediate_open_reports()['processed'], 0)

    def test_crashed_report_is_retried_not_stranded(self):
        """12 production reports sat in needs_review forever after a since-fixed crash."""
        report = self.report(
            self.movie(MKV), status='needs_review', remediation_action='error',
            last_result='FieldDoesNotExist: Episode has no field named download_links', attempts=1,
        )
        _age(report, minutes=11)
        with patch.object(remediation, 'remediate_report', return_value={
            'report_id': report.pk, 'status': 'queued',
        }) as run:
            remediation.remediate_open_reports()
        run.assert_called_once()

    def test_dead_worker_row_in_remediating_is_recovered(self):
        report = self.report(self.movie(MKV), status='remediating', attempts=0)
        _age(report, minutes=20)
        with patch.object(remediation, 'remediate_report', return_value={
            'report_id': report.pk, 'status': 'queued',
        }) as run:
            remediation.remediate_open_reports()
        run.assert_called_once()

    def test_recent_remediation_is_reused_not_recrawled(self):
        report = self.report(self.movie(MKV), status='queued', attempts=1)
        with patch('apps.catalog.playback_sources.remediate') as crawl:
            out = remediation.remediate_report(report, min_interval_seconds=300)
        crawl.assert_not_called()
        self.assertEqual(out['status'], 'queued')


class TicketFromReportTests(_Base):
    def _ticket_for(self, report, title):
        ticket = services.create_support_ticket(
            user=self.user, category=SupportTicket.Category.BUG, subject='گزارش پلیر',
            body='x', related_title=title, auto_process=False,
        )
        report.support_ticket = ticket
        report.save(update_fields=['support_ticket'])
        services.set_support_ticket_status(
            ticket=ticket, status=SupportTicket.Status.IN_PROGRESS, staff_note='[auto:report_remediation] queued',
        )
        return ticket

    def test_episode_ticket_closes_when_that_episode_is_fixed(self):
        """related_title carries «— قسمت N», which never matches a catalog row."""
        series, _good, bad = self.series_with_episodes()
        report = self.report(series, episode=bad, status='queued')
        ticket = self._ticket_for(report, 'سریال — قسمت 2')

        outcome, resolved = automation.retry_ticket(ticket)
        self.assertFalse(resolved)  # still an .mkv: must stay open, honestly

        Episode.objects.filter(pk=bad.pk).update(video_url='https://cdn.example/s1e2.mp4')
        outcome, resolved = automation.retry_ticket(ticket)
        self.assertTrue(resolved)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.Status.RESOLVED)
        self.assertTrue(ticket.messages.filter(is_staff_reply=True).exists())

    def test_sweep_notifies_owner_of_resolved_reports_immediately(self):
        movie = self.movie(MKV)
        report = self.report(movie, status='queued')
        ticket = self._ticket_for(report, 'فیلم')
        Movie.objects.filter(pk=movie.pk).update(download_links=MP4)
        stats = remediation.sync_reports_with_reality()
        closed = automation.close_tickets_for_reports(stats['resolved_report_ids'])
        self.assertEqual(closed, 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.Status.RESOLVED)

    def test_dead_end_is_announced_once_not_silently_parked(self):
        """A viewer whose report cannot be auto-fixed used to sit on «در صف قرار
        گرفت» forever; they now get one honest update, and only one."""
        series, _good, bad = self.series_with_episodes()
        report = self.report(series, episode=bad, status='unavailable',
                             last_result='no_browser_safe_source:episode_source_not_browser_safe')
        ticket = self._ticket_for(report, 'سریال — قسمت 2')

        outcome, resolved = automation.retry_ticket(ticket)
        self.assertFalse(resolved)
        self.assertEqual(outcome.action, 'report_unavailable')
        replies = ticket.messages.filter(is_staff_reply=True)
        self.assertEqual(replies.count(), 1)
        self.assertIn('کروم', replies.first().body)

        ticket.refresh_from_db()
        automation.retry_ticket(ticket)  # next tick: nothing new to say
        self.assertEqual(ticket.messages.filter(is_staff_reply=True).count(), 1)

    def test_exhausted_report_also_announces_once(self):
        report = self.report(self.movie(MKV), status='needs_review', remediation_action='auto_exhausted')
        ticket = self._ticket_for(report, 'فیلم')
        automation.retry_ticket(ticket)
        self.assertEqual(ticket.messages.filter(is_staff_reply=True).count(), 1)

    def test_announced_dead_end_still_resolves_when_a_mirror_lands(self):
        movie = self.movie(MKV)
        report = self.report(movie, status='unavailable')
        ticket = self._ticket_for(report, 'فیلم')
        automation.retry_ticket(ticket)

        Movie.objects.filter(pk=movie.pk).update(download_links=MP4)
        ticket.refresh_from_db()
        _outcome, resolved = automation.retry_ticket(ticket)
        self.assertTrue(resolved)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.Status.RESOLVED)

    def test_unavailable_reply_is_honest_and_gives_a_workaround(self):
        report = self.report(self.movie(MKV))
        with patch('apps.catalog.playback_sources.remediate', return_value={
            'outcome': 'unavailable', 'codes': {}, 'diag_after': {'reason': 'mkv_only'},
        }):
            outcome = automation._handle_from_report(report)
        self.assertEqual(outcome.status, SupportTicket.Status.IN_PROGRESS)
        self.assertIn('کروم', outcome.reply)
        self.assertNotIn('برطرف شد', outcome.reply)


class RetryPolicyTests(_Base):
    def _parked(self, retries, *, age):
        ticket = services.create_support_ticket(
            user=self.user, category=SupportTicket.Category.BUG, subject='s', body='b', auto_process=False,
        )
        services.set_support_ticket_status(
            ticket=ticket, status=SupportTicket.Status.IN_PROGRESS,
            staff_note=f'[auto:recheck] still_pending · retries={retries}',
        )
        _age(ticket, **age)
        return ticket

    def test_ticket_is_never_abandoned_after_twelve_tries(self):
        ticket = self._parked(12, age={'hours': 7})
        self.assertIn(ticket, automation._retry_tickets(10, None))

    def test_backoff_widens_with_each_attempt(self):
        early = self._parked(0, age={'minutes': 31})
        late = self._parked(7, age={'hours': 2})  # needs 6h at this depth
        due = automation._retry_tickets(10, None)
        self.assertIn(early, due)
        self.assertNotIn(late, due)

    def test_ticket_older_than_window_is_left_to_humans(self):
        ticket = self._parked(3, age={'days': 1})
        SupportTicket.objects.filter(pk=ticket.pk).update(
            created_at=timezone.now() - timedelta(days=automation.RETRY_MAX_AGE_DAYS + 1),
        )
        self.assertNotIn(ticket, automation._retry_tickets(10, None))


class EventDrivenTests(_Base):
    def test_ticket_is_processed_right_after_it_is_filed(self):
        with patch('apps.engagement.tasks.process_support_ticket_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                ticket = services.create_support_ticket(
                    user=self.user, category=SupportTicket.Category.SUPPORT, subject='s', body='b',
                )
        delay.assert_called_once_with(ticket.pk)

    def test_user_reply_wakes_the_engine_but_staff_reply_does_not(self):
        ticket = services.create_support_ticket(
            user=self.user, category=SupportTicket.Category.SUPPORT, subject='s', body='b', auto_process=False,
        )
        with patch('apps.engagement.tasks.process_support_ticket_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                services.reply_support_ticket(ticket=ticket, author=self.user, body='again', is_staff_reply=False)
                services.reply_support_ticket(
                    ticket=ticket, author=automation.get_bot_user(), body='hi', is_staff_reply=True,
                )
        delay.assert_called_once_with(ticket.pk)

    def test_broker_outage_never_breaks_the_users_request(self):
        with patch('apps.engagement.tasks.process_support_ticket_task.delay', side_effect=OSError('broker down')):
            with self.captureOnCommitCallbacks(execute=True):
                ticket = services.create_support_ticket(
                    user=self.user, category=SupportTicket.Category.SUPPORT, subject='s', body='b',
                )
        self.assertTrue(SupportTicket.objects.filter(pk=ticket.pk).exists())

    def test_process_ticket_answers_once_even_if_called_twice(self):
        ticket = services.create_support_ticket(
            user=self.user, category=SupportTicket.Category.SUPPORT, subject='s', body='b', auto_process=False,
        )
        self.assertIsNotNone(automation.process_ticket(ticket.pk))
        self.assertIsNone(automation.process_ticket(ticket.pk))  # sweep/duplicate task: no 2nd reply
        self.assertEqual(ticket.messages.filter(is_staff_reply=True).count(), 1)

    def _request(self):
        return SimpleNamespace(user=self.user, META={}, session=None)

    def test_report_intake_never_crawls_inside_the_http_request(self):
        movie = self.movie(MKV)
        with patch('apps.catalog.playback_sources.remediate') as crawl, \
                patch('apps.catalog.tasks.handle_content_report_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                result = record_content_issue_report(
                    self._request(), content_type='movie', problem_type='playback', object_id=movie.pk,
                )
        crawl.assert_not_called()
        delay.assert_called_once_with(result['report_id'])
        self.assertTrue(result['ok'])
        # The mirrored ticket is driven by the report task, not queued a second time.
        report = ContentIssueReport.objects.get(pk=result['report_id'])
        self.assertIsNotNone(report.support_ticket_id)

    def test_report_for_an_already_fixed_title_resolves_instantly(self):
        movie = self.movie(MP4)
        with patch('apps.catalog.tasks.handle_content_report_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                result = record_content_issue_report(
                    self._request(), content_type='movie', problem_type='playback', object_id=movie.pk,
                )
        delay.assert_not_called()
        self.assertEqual(result['status'], 'resolved')

    def test_repeat_report_reopens_a_resolved_ticket(self):
        movie = self.movie(MKV)
        with patch('apps.catalog.tasks.handle_content_report_task.delay'):
            with self.captureOnCommitCallbacks(execute=True):
                first = record_content_issue_report(
                    self._request(), content_type='movie', problem_type='playback', object_id=movie.pk,
                )
        report = ContentIssueReport.objects.get(pk=first['report_id'])
        services.set_support_ticket_status(ticket=report.support_ticket, status=SupportTicket.Status.RESOLVED)
        ContentIssueReport.objects.filter(pk=report.pk).update(status='resolved')

        with patch('apps.catalog.tasks.handle_content_report_task.delay'):
            with self.captureOnCommitCallbacks(execute=True):
                record_content_issue_report(
                    self._request(), content_type='movie', problem_type='playback', object_id=movie.pk,
                )
        report.support_ticket.refresh_from_db()
        self.assertEqual(report.support_ticket.status, SupportTicket.Status.OPEN)
