from rest_framework.views import exception_handler


ERROR_COPY = {
    401: (
        'نشست شما معتبر نیست یا زمان آن تمام شده است.',
        'دوباره وارد حساب شو.',
    ),
    403: (
        'حساب شما اجازه انجام این کار را ندارد.',
        'اگر فکر می‌کنی اشتباهی رخ داده، با پشتیبانی تماس بگیر.',
    ),
    404: (
        'اطلاعاتی که خواستی پیدا نشد.',
        'آدرس یا انتخابت را بررسی کن.',
    ),
    405: (
        'این روش برای این بخش قابل استفاده نیست.',
        'صفحه را تازه کن و دوباره تلاش کن.',
    ),
    429: (
        'درخواست‌های زیادی در زمان کوتاه فرستاده شد.',
        'کمی صبر کن و دوباره تلاش کن.',
    ),
}


def _has_persian(value):
    return isinstance(value, str) and any('\u0600' <= character <= '\u06ff' for character in value)


def user_friendly_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None or not isinstance(response.data, dict):
        return response

    copy = ERROR_COPY.get(response.status_code)
    detail = response.data.get('detail')
    if copy and not _has_persian(str(detail)):
        response.data['detail'] = copy[0]
        response.data.setdefault('hint', copy[1])
        response.data.setdefault('code', getattr(exc, 'default_code', 'request_failed'))
    return response
