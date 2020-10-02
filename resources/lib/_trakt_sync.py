import resources.lib.cache as cache


class _TraktSyncMixin():
    def _get_activity_timestamp(self, activities, activity_type=None, activity_key=None):
        if not activities:
            return
        if not activity_type:
            return activities.get('all', '')
        if not activity_key:
            return activities.get('{}s'.format(activity_type), {})
        return activities.get('{}s'.format(activity_type), {}).get(activity_key)

    def _set_activity_timestamp(self, timestamp, activity_type=None, activity_key=None):
        if not timestamp:
            return
        activities = cache.get_cache('sync_activity') or {}
        activities['all'] = timestamp
        if activity_type and activity_key:
            activities['{}s'.format(activity_type)] = activities.get('{}s'.format(activity_type)) or {}
            activities['{}s'.format(activity_type)][activity_key] = timestamp
        if not activities:
            return
        return cache.set_cache(activities, cache_name='sync_activity', cache_days=30)

    def _get_last_activity(self, activity_type=None, activity_key=None):
        if not self.authorize():
            return
        if not self.last_activities:
            self.last_activities = self.get_request('sync/last_activities', cache_days=0.0007)  # Cache for approx 1 minute to prevent rapid recalls
        return self._get_activity_timestamp(self.last_activities, activity_type=activity_type, activity_key=activity_key)

    def _get_sync_activity(self, activity_type=None, activity_key=None):
        if not self.sync_activities:
            self.sync_activities = cache.get_cache('sync_activity')
        if not self.sync_activities:
            return
        return self._get_activity_timestamp(self.sync_activities, activity_type=activity_type, activity_key=activity_key)

    def _get_sync_refresh_status(self, activity_type=None, activity_key=None):
        last_activity = self._get_last_activity(activity_type, activity_key)
        sync_activity = self._get_sync_activity(activity_type, activity_key) if last_activity else None
        if not sync_activity or sync_activity != last_activity:
            return last_activity

    def _get_quick_list(self, response=None, trakt_type=None, id_type=None):
        id_type = id_type or 'tmdb'
        if response and trakt_type:
            return {i.get(trakt_type, {}).get('ids', {}).get(id_type): i for i in response if i.get(trakt_type, {}).get('ids', {}).get(id_type)}

    def _get_sync_list(self, path, trakt_type, activity_type, activity_key, id_type=None, cache_days=None):
        if not self.authorize():
            return
        if not activity_type or not activity_key or not trakt_type or not path:
            return
        cache_days = cache_days or self.cache_long
        last_activity = self._get_sync_refresh_status(activity_type, activity_key)
        cache_refresh = True if last_activity else False
        response = self.get_request(
            path,
            extended='full',
            cache_name='sync_request.days_{}'.format(cache_days),
            cache_combine_name=True,
            cache_days=cache_days,
            cache_refresh=cache_refresh)
        if not response:
            return
        if last_activity:
            self._set_activity_timestamp(last_activity, activity_type=activity_type, activity_key=activity_key)
        if not id_type:
            return response
        return cache.use_cache(
            self._get_quick_list, response, trakt_type, id_type,
            cache_name='quick_list.{}.{}'.format(path, id_type),
            cache_days=cache_days,
            cache_refresh=cache_refresh)

    def get_sync_watched(self, trakt_type, id_type=None, cache_days=None):
        return self._get_sync_list(
            path='sync/watched/{}s'.format(trakt_type),
            activity_type='episode' if trakt_type == 'show' else trakt_type,
            activity_key='watched_at',
            trakt_type=trakt_type,
            cache_days=cache_days,
            id_type=id_type)

    def get_sync_watched_sc(self, trakt_type, id_type=None):
        return self.get_sync_watched(trakt_type, id_type=id_type, cache_days=self.cache_long)

    def get_sync_collection(self, trakt_type, id_type=None):
        return self._get_sync_list(
            path='sync/collection/{}s'.format(trakt_type),
            activity_type='episode' if trakt_type == 'show' else trakt_type,
            activity_key='collected_at',
            trakt_type=trakt_type,
            id_type=id_type)

    def get_sync_playback(self, trakt_type, id_type=None):
        return self._get_sync_list(
            path='sync/playback/{}s'.format(trakt_type),
            activity_type='episode' if trakt_type == 'show' else trakt_type,
            activity_key='watched_at',
            trakt_type=trakt_type,
            id_type=id_type)

    def get_sync_watchlist(self, trakt_type, id_type=None):
        return self._get_sync_list(
            path='sync/watchlist/{}s'.format(trakt_type),
            activity_type=trakt_type,
            activity_key='watchlisted_at',
            trakt_type=trakt_type,
            id_type=id_type)

    def get_sync(self, sync_type, trakt_type, id_type=None):
        if sync_type == 'watched_sc':
            func = self.get_sync_watched_sc
        elif sync_type == 'watched':
            func = self.get_sync_watched
        elif sync_type == 'collection':
            func = self.get_sync_collection
        elif sync_type == 'playback':
            func = self.get_sync_playback
        elif sync_type == 'watchlist':
            func = self.get_sync_watchlist
        else:
            return
        sync_name = '{}.{}.{}'.format(sync_type, trakt_type, id_type)
        self.sync[sync_name] = self.sync.get(sync_name) or func(trakt_type, id_type)
        return self.sync[sync_name] or {}

    def use_activity_cache(self, ac_trakt_type, ac_activity_key, ac_cache_name, ac_cache_days, func, *args, **kwargs):
        if not self.authorize():
            return

        # Get our cached data
        cache_object = cache.get_cache(ac_cache_name)

        # Cached response last_activity timestamp matches last_activity from trakt so no need to refresh
        last_activity = self._get_last_activity(ac_trakt_type, ac_activity_key)
        if cache_object and cache_object.get('last_activity') == last_activity:
            return cache_object['response']

        # Either not cached or last_activity doesn't match so get a new request
        response = func(*args, **kwargs)
        if not response:
            return

        # Cache our response
        cache.set_cache(
            {'response': response, 'last_activity': last_activity},
            cache_name=ac_cache_name, cache_days=ac_cache_days)

        return response
