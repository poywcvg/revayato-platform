from rest_framework.throttling import UserRateThrottle


class WatchPartyCreateThrottle(UserRateThrottle):
    scope = 'watch_party_create'


class WatchPartyJoinThrottle(UserRateThrottle):
    scope = 'watch_party_join'
