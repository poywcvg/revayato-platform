"""The «گزارش خطا» button catalogue — one definition, every client.

A viewer who taps "something is wrong" is the cheapest, most accurate sensor we
have: they are looking at the broken thing right now. What they were never asked
is *which* wrong thing, precisely enough to act on. ``subtitle`` used to mean
"missing", "out of sync" and "mojibake" at once — three different repairs behind
one word — so the engine could only guess, and ``audio`` had no repair at all.

Every button here is defined by the fix behind it. A symptom only earns its own
button when :mod:`apps.catalog.content_remediation` does something *different*
with it; otherwise it is false precision that makes the viewer choose between
two words for the same outcome.

The catalogue is served to clients (``GET /api/catalog/report-issue/options/``)
so the web player, the Android app and the admin all render the same buttons
from the same source. Clients keep a bundled copy for offline/first paint, but
the server's list wins — adding a repair ships a new button without an app
release.

``legacy`` maps the coarse types older clients still send onto the precise ones,
so an app from before this change keeps working and its reports still route to
a real fix.
"""

from __future__ import annotations

from typing import Any

#: Groups, in the order the picker shows them.
GROUPS = (
    ('playback', 'پخش'),
    ('audio', 'صدا'),
    ('subtitle', 'زیرنویس'),
    ('content', 'محتوا'),
    ('download', 'دانلود'),
    ('other', 'موارد دیگر'),
)

#: The buttons. ``scope`` restricts a button to one content type; ``auto`` marks
#: the ones the engine repairs without a human. ``icon`` names an icon both the
#: web player and the Android app already ship.
BUTTONS: tuple[dict[str, Any], ...] = (
    {
        'value': 'playback',
        'group': 'playback',
        'label': 'اصلاً پخش نمی‌شود',
        'hint': 'ویدیو باز نمی‌شود یا خطا می‌دهد',
        'icon': 'alert-triangle',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'buffering',
        'group': 'playback',
        'label': 'مدام قطع و وصل می‌شود',
        'hint': 'پخش شروع می‌شود ولی مدام می‌ایستد',
        'icon': 'loader',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'audio_silent',
        'group': 'audio',
        'label': 'تصویر هست، صدا نیست',
        'hint': 'فیلم پخش می‌شود ولی هیچ صدایی ندارد',
        'icon': 'volume-off',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'audio_desync',
        'group': 'audio',
        'label': 'صدا با تصویر هماهنگ نیست',
        'hint': 'صدا از تصویر جلو یا عقب است',
        'icon': 'audio',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'subtitle_missing',
        'group': 'subtitle',
        'label': 'زیرنویس ندارد',
        'hint': 'هیچ زیرنویس فارسی‌ای در دسترس نیست',
        'icon': 'captions-off',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'subtitle_sync',
        'group': 'subtitle',
        'label': 'زیرنویس عقب یا جلو است',
        'hint': 'متن با گفت‌وگو هم‌زمان نیست',
        'icon': 'captions',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'subtitle_garbled',
        'group': 'subtitle',
        'label': 'زیرنویس خراب یا نامفهوم است',
        'hint': 'حروف به‌هم‌ریخته‌اند یا متن بی‌ربط است',
        'icon': 'file-warning',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'wrong_title',
        'group': 'content',
        'label': 'فیلم با عنوان صفحه فرق دارد',
        'hint': 'چیزی که پخش می‌شود این فیلم نیست',
        'icon': 'film',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'wrong_episode',
        'group': 'content',
        'label': 'قسمت اشتباه است',
        'hint': 'این ویدیو مربوط به قسمت دیگری است',
        'icon': 'list-video',
        'scope': 'series',
        'requires_episode': True,
        'auto': True,
    },
    {
        'value': 'quality',
        'group': 'content',
        'label': 'کیفیت تصویر خیلی پایین است',
        'hint': 'تصویر تار است یا با کیفیت انتخابی نمی‌خواند',
        'icon': 'gauge',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'download_dead',
        'group': 'download',
        'label': 'لینک دانلود کار نمی‌کند',
        'hint': 'دانلود شروع نمی‌شود یا نیمه‌کاره می‌ماند',
        'icon': 'download',
        'scope': 'both',
        'auto': True,
    },
    {
        'value': 'other',
        'group': 'other',
        'label': 'مورد دیگر',
        'hint': 'مشکلی که در این فهرست نیست',
        'icon': 'info',
        'scope': 'both',
        'auto': False,
    },
)

#: Coarse types older clients still send → the precise button they meant.
#: ``subtitle`` and ``audio`` were the two ambiguous ones; a viewer tapping the
#: old «مشکل زیرنویس» most often meant "there is none", which is also the repair
#: that safely subsumes the others (the subtitle pipeline re-verifies sync and
#: encoding on whatever it lands).
LEGACY_ALIASES = {
    'subtitle': 'subtitle_missing',
    'audio': 'audio_silent',
}

BY_VALUE = {button['value']: button for button in BUTTONS}

#: Everything a client may post, including the retired spellings.
VALID_PROBLEMS = frozenset(BY_VALUE) | frozenset(LEGACY_ALIASES)

#: Types the remediation engine repairs on its own.
AUTO_PROBLEMS = frozenset(value for value, b in BY_VALUE.items() if b['auto'])

#: Persian labels, keyed by every accepted value so tickets and admin read alike.
PROBLEM_LABELS = {value: button['label'] for value, button in BY_VALUE.items()}
PROBLEM_LABELS.update({old: PROBLEM_LABELS[new] for old, new in LEGACY_ALIASES.items()})


def normalize(problem_type: str) -> str:
    """Map whatever a client sent onto a current button value.

    Unknown input falls back to ``other`` rather than being rejected: a report we
    cannot classify is still a viewer telling us something is broken, and the
    staff inbox is a better home for it than a dropped request.
    """
    value = (problem_type or '').strip().lower()
    value = LEGACY_ALIASES.get(value, value)
    return value if value in BY_VALUE else 'other'


def buttons_for(content_type: str = '', *, has_episode: bool = False) -> list[dict[str, Any]]:
    """The buttons a given player should show.

    «قسمت اشتباه» cannot be true for a film, and cannot be acted on for a series
    the player has not told us the episode of — offering it there would collect
    reports the engine must immediately reject.
    """
    kind = (content_type or '').strip().lower()
    out = []
    for button in BUTTONS:
        scope = button.get('scope', 'both')
        if kind and scope != 'both' and scope != kind:
            continue
        if button.get('requires_episode') and not has_episode:
            continue
        out.append(dict(button))
    return out


def grouped_for(content_type: str = '', *, has_episode: bool = False) -> list[dict[str, Any]]:
    """:func:`buttons_for`, bucketed into the display groups (empties dropped)."""
    available = buttons_for(content_type, has_episode=has_episode)
    groups = []
    for key, label in GROUPS:
        members = [b for b in available if b['group'] == key]
        if members:
            groups.append({'key': key, 'label': label, 'options': members})
    return groups
