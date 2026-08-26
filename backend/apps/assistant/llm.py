"""Thin client for the Anthropic-shaped AI gateway used for behavior analysis.

The gateway speaks the Anthropic Messages API (NOT OpenAI):
    POST {AI_BASE_URL}/v1/messages
    headers: x-api-key, anthropic-version: 2023-06-01
    body:    { model, max_tokens, system, messages, stream }

Credentials come from the environment only (never hardcoded, never committed):
    AI_API_KEY   - the gateway bearer key
    AI_BASE_URL  - gateway host (defaults to the local gateway the project uses)
    AI_MODEL     - model id (defaults to claude-opus-5)

This module is strictly read-only with respect to the catalog: it receives an
already-built taste profile + a short list of existing catalog titles and returns
natural-language Persian analysis. It never touches Movie/Series.
"""

import json
import os

import requests

DEFAULT_BASE_URL = 'http://178.105.20.69:20128'
DEFAULT_MODEL = 'claude-opus-5'

SYSTEM_PROMPT = (
    'شما «دستیار هوشمند رِوایتو» هستید: یک منتقد و پیشنهاددهنده‌ی فیلم و سریال '
    'که به فارسی صحبت می‌کند. شما فقط تحلیل رفتار تماشای کاربر را به زبان ساده و '
    'دوستانه توضیح می‌دهید و بر اساس سلیقه‌ی او، از بین فیلم‌ها و سریال‌هایی که '
    'هم‌اکنون در سایت موجودند به او پیشنهاد می‌دهید. قواعد: (۱) فقط به فارسی، '
    'صمیمی و کوتاه بنویسید (حداکثر چهار پاراگراف). (۲) نام فیلم‌ها و سریال‌های '
    'پیشنهادی را دقیقاً همان‌طور که در لیست «عناوین موجود» آمده تکرار کنید؛ '
    'هیچ اثری خارج از آن لیست پیشنهاد ندهید. (۳) ژانرهای مورد علاقه، نحوه تماشا '
    '(دوبله/زیرنویس) و تعداد آثار تمام‌شده را برجسته کنید. (۴) از اطلاعات شخصی '
    'استفاده نکنید و فقط بر تحلیل سلیقه تمرکز کنید.'
)


def _config():
    return {
        'api_key': os.environ.get('AI_API_KEY', ''),
        'base_url': os.environ.get('AI_BASE_URL', DEFAULT_BASE_URL).rstrip('/'),
        'model': os.environ.get('AI_MODEL', DEFAULT_MODEL),
    }


def _build_user_prompt(profile, taste_summary, recent_events, picks):
    top_genres = [g.get('title') for g in (taste_summary or {}).get('top_genres', [])]
    playback = (taste_summary or {}).get('inferred_playback', 'any')
    completed = (taste_summary or {}).get('completed_count', 0)

    lines = []
    lines.append('خلاصه‌ی سلیقه‌ی کاربر (از رفتارهای ثبت‌شده):')
    lines.append(f'- ژانرهای برتر: {", ".join(top_genres) if top_genres else "هنوز مشخص نشده"}')
    lines.append(f'- نحوه تماشا: {playback} (دوبله / زیرنویس / هر دو)')
    lines.append(f'- تعداد آثار تمام‌شده: {completed}')

    if recent_events:
        lines.append('')
        lines.append('آخرین فعالیت‌های کاربر:')
        for ev in recent_events[:12]:
            lines.append(f'- {ev}')

    if picks:
        lines.append('')
        lines.append('عناوین موجود در سایت برای پیشنهاد (فقط از این لیست استفاده کنید):')
        for pick in picks:
            title = pick.get('title') or pick.get('name') or '?'
            ctype = 'سریال' if pick.get('content_type') == 'series' else 'فیلم'
            reason = pick.get('reason', '')
            lines.append(f'- [{ctype}] {title} — {reason}')

    lines.append('')
    lines.append('لطفاً تحلیل سلیقه را بنویسید و ۳ تا ۵ مورد از عناوین بالا را '
                 'با ذکر دلیل پیشنهاد دهید.')
    return '\n'.join(lines)


def _extract_text(response):
    """Pull assistant text out of either a JSON body or an SSE stream."""
    ctype = response.headers.get('content-type', '')
    if 'text/event-stream' in ctype or not response.text.lstrip().startswith('{'):
        text = []
        for raw in response.text.splitlines():
            if not raw.startswith('data:'):
                continue
            payload = raw[len('data:'):].strip()
            if not payload or payload == '[DONE]':
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get('type') == 'content_block_delta':
                delta = chunk.get('delta', {})
                if delta.get('type') == 'text_delta':
                    text.append(delta.get('text', ''))
        if text:
            return ''.join(text).strip()
    try:
        data = response.json()
    except json.JSONDecodeError:
        data = {}
    blocks = data.get('content')
    if isinstance(blocks, list):
        return ''.join(
            b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text'
        ).strip()
    if isinstance(data.get('text'), str):
        return data['text'].strip()
    return ''


def analyze_behavior(profile, taste_summary, recent_events, picks, *, max_tokens=700, timeout=30):
    """Return Persian analysis text for the user's behavior.

    Raises RuntimeError on missing key / gateway error / empty reply so the
    caller can fall back to a deterministic summary.
    """
    cfg = _config()
    if not cfg['api_key']:
        raise RuntimeError('AI_API_KEY is not configured')

    user_text = _build_user_prompt(profile, taste_summary, recent_events, picks)
    payload = {
        'model': cfg['model'],
        'max_tokens': max_tokens,
        'system': SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': user_text}],
        'stream': False,
    }

    try:
        resp = requests.post(
            f"{cfg['base_url']}/v1/messages",
            headers={
                'x-api-key': cfg['api_key'],
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f'AI gateway unreachable: {exc}') from exc

    if resp.status_code != 200:
        raise RuntimeError(f'AI gateway error {resp.status_code}: {resp.text[:200]}')

    text = _extract_text(resp)
    if not text:
        raise RuntimeError('AI gateway returned empty analysis')
    return text
