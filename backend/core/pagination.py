from rest_framework.pagination import CursorPagination as DRFCursorPagination
from rest_framework.response import Response
from django.utils import timezone


class CursorPagination(DRFCursorPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-created_at'
    cursor_query_param = 'cursor'

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'pagination': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'has_next': self.has_next(),
                'has_previous': self.has_previous(),
                'page_size': self.page_size,
            }
        })


class OffsetPagination:
    default_limit = 20
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'

    def paginate_queryset(self, queryset, request, view=None):
        try:
            limit = int(request.query_params.get(self.limit_query_param, self.default_limit))
            offset = int(request.query_params.get(self.offset_query_param, 0))
        except (ValueError, TypeError):
            limit = self.default_limit
            offset = 0

        limit = min(limit, self.max_limit)
        offset = max(offset, 0)

        self.limit = limit
        self.offset = offset
        self.count = queryset.count()

        return queryset[offset:offset + limit]

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'pagination': {
                'count': self.count,
                'limit': self.limit,
                'offset': self.offset,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            }
        })

    def get_next_link(self):
        if self.offset + self.limit >= self.count:
            return None
        return f'?{self.limit_query_param}={self.limit}&{self.offset_query_param}={self.offset + self.limit}'

    def get_previous_link(self):
        if self.offset <= 0:
            return None
        prev_offset = max(0, self.offset - self.limit)
        return f'?{self.limit_query_param}={self.limit}&{self.offset_query_param}={prev_offset}'


class PageNumberPagination:
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def paginate_queryset(self, queryset, request, view=None):
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

        try:
            page_size = int(request.query_params.get(self.page_size_query_param, self.page_size))
        except (ValueError, TypeError):
            page_size = self.page_size

        page_size = min(page_size, self.max_page_size)

        try:
            page_number = int(request.query_params.get(self.page_query_param, 1))
        except (ValueError, TypeError):
            page_number = 1

        paginator = Paginator(queryset, page_size)

        try:
            page = paginator.page(page_number)
        except PageNotAnInteger:
            page = paginator.page(1)
        except EmptyPage:
            page = paginator.page(paginator.num_pages)

        self.page = page
        return page.object_list

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'pagination': {
                'count': self.page.paginator.count,
                'num_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.page.paginator.per_page,
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous(),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            }
        })

    def get_next_link(self):
        if not self.page.has_next():
            return None
        return f'?{self.page_query_param}={self.page.next_page_number()}&{self.page_size_query_param}={self.page.paginator.per_page}'

    def get_previous_link(self):
        if not self.page.has_previous():
            return None
        return f'?{self.page_query_param}={self.page.previous_page_number()}&{self.page_size_query_param}={self.page.paginator.per_page}'