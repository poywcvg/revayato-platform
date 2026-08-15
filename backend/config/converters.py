"""URL path converters for catalog detail routes."""


class UnicodeSlugConverter:
    """Match ASCII and Unicode slugs (Persian titles use allow_unicode=True)."""

    # Word chars + hyphen; Python 3 \w includes letters like ی/ک.
    regex = r'[-\w]+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
