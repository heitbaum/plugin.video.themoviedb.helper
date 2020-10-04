import xbmc
import xbmcgui
import datetime
import resources.lib.utils as utils
import resources.lib.cache as cache
import resources.lib.paginated as paginated
from resources.lib.cache import use_simple_cache
from json import loads, dumps
from resources.lib.requestapi import RequestAPI
from resources.lib.plugin import ADDON, PLUGINPATH
from resources.lib.paginated import PaginatedItems
from resources.lib.traktitems import TraktItems


API_URL = 'https://api.trakt.tv/'
CLIENT_ID = 'e6fde6173adf3c6af8fd1b0694b9b84d7c519cefc24482310e1de06c6abe5467'
CLIENT_SECRET = '15119384341d9a61c751d8d515acbc0dd801001d4ebe85d3eef9885df80ee4d9'


def use_activity_cache(activity_type=None, activity_key=None, cache_days=None, pickle_object=False):
    """ Decorator to cache and refresh if last activity changes """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if not self.authorize():
                return

            # Set cache_name
            cache_name = '{}.'.format(func.__name__)
            cache_name = '{}.{}'.format(self.__class__.__name__, cache_name)
            cache_name = cache.format_name(cache_name, *args, **kwargs)

            # Get our cached data
            cache_object = utils.get_pickle(cache_name) if pickle_object else cache.get_cache(cache_name)

            # Cached response last_activity timestamp matches last_activity from trakt so no need to refresh
            last_activity = self._get_last_activity(activity_type, activity_key)
            if cache_object and cache_object.get('last_activity') == last_activity:
                if cache_object.get('response'):
                    return cache_object['response']

            # Either not cached or last_activity doesn't match so get a new request and cache it
            response = func(self, *args, **kwargs)
            if not response:
                return
            cache_func = utils.set_pickle if pickle_object else cache.set_cache
            cache_func(
                {'response': response, 'last_activity': last_activity},
                cache_name=cache_name, cache_days=cache_days)
            return response
        return wrapper
    return decorator


class _TraktItemLists():
    @use_simple_cache(cache_days=cache.CACHE_SHORT)
    def get_sorted_list(self, path, sort_by=None, sort_how=None, extended=None, trakt_type=None, permitted_types=None, cache_refresh=False):
        response = self.get_response(path, extended=extended, limit=0)
        if not response:
            return
        return TraktItems(response.json(), headers=response.headers).build_items(
            sort_by=sort_by or response.headers.get('X-Sort-By'),
            sort_how=sort_how or response.headers.get('X-Sort-How'),
            permitted_types=permitted_types)

    @use_simple_cache(cache_days=cache.CACHE_SHORT)
    def get_simple_list(self, *args, **kwargs):
        trakt_type = kwargs.pop('trakt_type', None)
        response = self.get_response(*args, **kwargs)
        if not response:
            return
        return TraktItems(response.json(), headers=response.headers, trakt_type=trakt_type).configure_items()

    def get_basic_list(self, path, trakt_type, page=1, limit=20, params=None, authorize=False, sort_by=None, sort_how=None, extended=None):
        if authorize and not self.authorize():
            return
        # TODO: Add argument to check whether to refresh on first page (e.g. for user lists)
        # Also: Think about whether need to do it for standard response
        cache_refresh = True if utils.try_parse_int(page, fallback=1) == 1 else False
        # Sorted list needs to be manually paginated because we need to pull ALL items first
        if sort_by is not None:
            trakt_items = self.get_sorted_list(
                path, sort_by, sort_how, extended=extended, cache_refresh=cache_refresh)
            response = PaginatedItems(items=trakt_items['items'], page=page, limit=limit).get_dict()
        # Unsorted lists can be automatically paginated by the API since we don't need to sort them
        # Can't pass all lists through get_sorted_list as 'unsorted' because some lists in API force pagination
        else:
            response = self.get_simple_list(path, extended=extended, page=page, limit=limit, trakt_type=trakt_type)
        if not response:
            return
        return response['items'] + paginated.get_next_page(response['headers'])

    def get_custom_list(self, list_slug, user_slug=None, page=1, limit=20, params=None, authorize=False, sort_by=None, sort_how=None, extended=None):
        if authorize and not self.authorize():
            return
        path = 'users/{}/lists/{}/items'.format(user_slug or 'me', list_slug)
        # Refresh cache on first page for user list because it might've changed
        cache_refresh = True if utils.try_parse_int(page, fallback=1) == 1 else False
        trakt_items = self.get_sorted_list(
            path, sort_by, sort_how,
            extended=extended,
            permitted_types=['movie', 'show'],
            cache_refresh=cache_refresh)
        paginated_items = PaginatedItems(items=trakt_items['items'], page=page, limit=limit)
        return {
            'items': paginated_items.items,
            'movies': trakt_items.get('movies', []),
            'tvshows': trakt_items.get('shows', []),
            'next_page': paginated_items.next_page}

    @use_activity_cache(cache_days=cache.CACHE_SHORT)
    def _get_sync_list(self, sync_type, trakt_type, sort_by=None, sort_how=None):
        return TraktItems(
            items=self.get_sync(sync_type, trakt_type),
            trakt_type=trakt_type).build_items(sort_by, sort_how)

    def get_sync_list(self, sync_type, trakt_type, page=1, limit=20, params=None, sort_by=None, sort_how=None, next_page=True):
        trakt_items = self._get_sync_list(sync_type, trakt_type, sort_by=sort_by, sort_how=sort_how)
        response = PaginatedItems(items=trakt_items['items'], page=page, limit=limit).get_dict()
        if not response:
            return
        if not next_page:
            return response['items']
        return response['items'] + paginated.get_next_page(response['headers'])

    def get_inprogress_shows_list(self, page=1, limit=20, params=None):
        response = PaginatedItems(
            items=TraktItems(self._get_inprogress_shows(), trakt_type='show').build_items()['items'],
            page=page, limit=limit).get_dict()
        if not response:
            return
        return response['items'] + paginated.get_next_page(response['headers'])

    @use_activity_cache(cache_days=cache.CACHE_SHORT)
    def _get_upnext_episodes_list(self, page=1, limit=20, sort_by_premiered=False):
        items = []
        for i in self._get_inprogress_shows():
            next_episode = self.get_upnext_episodes(
                uid=i.get('show', {}).get('ids', {}).get('slug'),
                tvshow_details=i.get('show', {}),  # Pass show details so we don't need to relookup
                get_single_episode=True)
            if not next_episode:
                continue
            items.append(next_episode)
        if not sort_by_premiered:
            return items
        return sorted(items, key=lambda i: i.get('infolabels', {}).get('premiered'), reverse=True)

    def get_upnext_episodes_list(self, page=1, limit=20, sort_by_premiered=True):
        response = PaginatedItems(
            self._get_upnext_episodes_list(page, limit, sort_by_premiered),
            page=page, limit=utils.try_parse_int(limit) or 20)
        return response.items + response.next_page

    def get_upnext_list(self, unique_id, id_type='slug', page=1, limit=20):
        slug = unique_id if id_type == 'slug' else self.get_id(
            id_type=id_type, unique_id=unique_id, trakt_type='show', output_type='slug')
        if not slug:
            return
        response = PaginatedItems(
            self.get_upnext_episodes(slug),
            page=page,
            limit=utils.try_parse_int(limit) or 20)
        if response and response.items:
            return response.items + response.next_page

    def get_list_of_lists(self, path, page=1, limit=250, authorize=False):
        if authorize and not self.authorize():
            return
        response = self.get_response(path, page=page, limit=limit)
        if not response:
            return
        items = []
        for i in response.json():
            if i.get('list', {}).get('name'):
                i = i.get('list', {})
            elif not i.get('name'):
                continue
            item = {}
            item['label'] = i.get('name')
            item['infolabels'] = {'plot': i.get('description')}
            item['infoproperties'] = {k: v for k, v in i.items() if v and type(v) not in [list, dict]}
            item['art'] = {}
            item['params'] = {
                'info': 'trakt_userlist',
                'list_slug': i.get('ids', {}).get('slug'),
                'user_slug': i.get('user', {}).get('ids', {}).get('slug')}
            item['unique_ids'] = {
                'trakt': i.get('ids', {}).get('trakt'),
                'slug': i.get('ids', {}).get('slug'),
                'user': i.get('user', {}).get('ids', {}).get('slug')}
            path = '{}?info={info}&list_slug={list_slug}&user_slug={user_slug}'.format(PLUGINPATH, **item['params'])
            item['context_menu'] = [
                ('{}: {}'.format(ADDON.getLocalizedString(32287), ADDON.getLocalizedString(32286)),
                    'Container.Update({}&sort_by=rank&sort_how=asc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), ADDON.getLocalizedString(32106)),
                    'Container.Update({}&sort_by=added&sort_how=desc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(369)),
                    'Container.Update({}&sort_by=title&sort_how=asc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(345)),
                    'Container.Update({}&sort_by=year&sort_how=desc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(590)),
                    'Container.Update({}&sort_by=random)'.format(path))]
            items.append(item)
        return items + paginated.get_next_page(response.headers)

    def _get_calendar_episodes_list(self, startdate=0, days=1):
        response = self.get_calendar_episodes(startdate=startdate, days=days)
        if not response:
            return

        # Reverse items for date ranges in past
        traktitems = reversed(response) if startdate < -1 else response

        items = []
        for i in traktitems:
            # Do some timezone conversion so we check that we're in the date range for our timezone
            if not utils.date_in_range(i.get('first_aired'), utc_convert=True, start_date=startdate, days=days):
                continue
            air_date = utils.convert_timestamp(i.get('first_aired'), utc_convert=True)
            item = {}
            item['label'] = i.get('episode', {}).get('title')
            item['infolabels'] = {
                'mediatype': 'episode',
                'premiered': air_date.strftime('%Y-%m-%d'),
                'year': air_date.strftime('%Y'),
                'title': item['label'],
                'episode': i.get('episode', {}).get('number'),
                'season': i.get('episode', {}).get('season'),
                'tvshowtitle': i.get('show', {}).get('title'),
                'duration': utils.try_parse_int(i.get('episode', {}).get('runtime', 0)) * 60,
                'plot': i.get('episode', {}).get('overview'),
                'mpaa': i.get('show', {}).get('certification')}
            item['infoproperties'] = {
                'air_date': utils.get_region_date(air_date, 'datelong'),
                'air_time': utils.get_region_date(air_date, 'time'),
                'air_day': air_date.strftime('%A'),
                'air_day_short': air_date.strftime('%a'),
                'air_date_short': air_date.strftime('%d %b')}
            item['unique_ids'] = {'tvshow.{}'.format(k): v for k, v in i.get('show', {}).get('ids', {}).items()}
            item['path'] = PLUGINPATH,
            item['params'] = {
                'info': 'details',
                'tmdb_type': 'tv',
                'tmdb_id': i.get('show', {}).get('ids', {}).get('tmdb'),
                'episode': i.get('episode', {}).get('number'),
                'season': i.get('episode', {}).get('season')}
            items.append(item)
        return items

    def get_calendar_episodes_list(self, startdate=0, days=1, page=1, limit=20):
        cache_name = 'trakt.calendar.episodes.{}.{}'.format(startdate, days)
        response_items = cache.use_cache(
            self._get_calendar_episodes_list, startdate, days,
            cache_name=cache_name,
            cache_refresh=True,
            cache_days=1)
        response = PaginatedItems(response_items, page=page, limit=limit)
        if response and response.items:
            return response.items + response.next_page


class _TraktProgressMixin():
    @use_activity_cache('movies', 'watched_at', cache_days=cache.CACHE_LONG)
    def get_movie_playcount(self, id_type, unique_id):
        return self.get_sync('watched', 'movie', id_type).get(unique_id, {}).get('plays')

    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_LONG)
    def get_episode_playcount(self, id_type, unique_id, season, episode):
        season = utils.try_parse_int(season, fallback=-2)  # Make fallback -2 to prevent matching on 0
        episode = utils.try_parse_int(episode, fallback=-2)  # Make fallback -2 to prevent matching on 0
        for i in self.get_sync('watched', 'show', id_type).get(unique_id, {}).get('seasons', []):
            if i.get('number', -1) != season:
                continue
            for j in i.get('episodes', []):
                if j.get('number', -1) == episode:
                    return j.get('plays', 1)

    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_episodes_airedcount(self, id_type, unique_id, season=None):
        # For seasons we need to lookup indiviual seasons as Trakt doesn't provide aired count per season in watched sync
        if season is not None:
            season = utils.try_parse_int(season, fallback=-2)
            slug = self.get_id(id_type, unique_id, trakt_type='show', output_type='slug')
            for i in self.get_request_sc('shows', slug, 'seasons', extended='full'):
                if i.get('number', -1) == season:
                    return i.get('aired_episodes')
            return 0
        return self.get_sync('watched', 'show', id_type).get(unique_id, {}).get('show', {}).get('aired_episodes')

    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_LONG)
    def get_episodes_watchcount(self, id_type=None, unique_id=None, season=None, exclude_specials=True, tvshow=None):
        if (not unique_id or not id_type) and not tvshow:
            return
        count = 0
        season = utils.try_parse_int(season) if season is not None else None
        tvshow = tvshow or self.get_sync('watched', 'show', id_type).get(unique_id, {})
        reset_at = tvshow.get('reset_at')
        for i in tvshow.get('seasons', []):
            if season is not None and i.get('number', -1) != season:
                continue
            if exclude_specials and i.get('number') == 0:
                continue
            count += self._get_episodes_watchcount(i.get('episodes', []), reset_at=reset_at)
        return count

    def _get_episodes_watchcount(self, episodes, reset_at=None):
        count = 0
        reset_at = utils.convert_timestamp(reset_at) if reset_at else None
        for episode in episodes:
            last_watched_at = episode.get('last_watched_at')
            if not last_watched_at:
                continue
            if reset_at:
                try:
                    if utils.convert_timestamp(last_watched_at) < reset_at:
                        continue
                except Exception as exc:
                    utils.kodi_log(exc, 1)
            count += 1
        return count

    def _is_inprogress_show(self, item, hidden_shows=[]):
        if item.get('show', {}).get('ids', {}).get('slug') in hidden_shows:
            return
        if not item.get('show', {}).get('aired_episodes'):
            return
        if item.get('show', {}).get('aired_episodes') > self.get_episodes_watchcount(
                unique_id=item.get('show', {}).get('ids', {}).get('slug'),
                id_type='slug', tvshow=item):
            return item

    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def _get_inprogress_shows(self):
        if not self.authorize():
            return
        recently_watched = TraktItems(self.get_sync('watched', 'show')).sort_items(
            sort_by='watched', sort_how='desc')
        hidden_shows = self.get_hiddenitems('show')
        return [i for i in recently_watched if self._is_inprogress_show(i, hidden_shows)]

    @use_activity_cache(cache_days=cache.CACHE_LONG)
    def get_hiddenitems(self, trakt_type, progress_watched=True, progress_collected=True, calendar=True, id_type='slug'):
        hidden_items = set()
        if not self.authorize() or not trakt_type or not id_type:
            return hidden_items
        if progress_watched:
            response = self.get_response_json('users', 'hidden', 'progress_watched', type=trakt_type)
            hidden_items |= {i.get(trakt_type, {}).get('ids', {}).get(id_type) for i in response}
        if progress_collected:
            response = self.get_response_json('users', 'hidden', 'progress_collected', type=trakt_type)
            hidden_items |= {i.get(trakt_type, {}).get('ids', {}).get(id_type) for i in response}
        if calendar:
            response = self.get_response_json('users', 'hidden', 'calendar', type=trakt_type)
            hidden_items |= {i.get(trakt_type, {}).get('ids', {}).get(id_type) for i in response}
        return hidden_items

    @use_activity_cache(cache_days=cache.CACHE_SHORT)
    def get_show_progress(self, uid, hidden=False, specials=False, count_specials=False):
        if not uid:
            return
        return self.get_response_json('shows', uid, 'progress/watched')

    @use_activity_cache(cache_days=cache.CACHE_SHORT)
    def get_upnext_episodes(self, uid, tvshow_details=None, get_single_episode=False):
        if not tvshow_details and uid:
            tvshow_details = self.get_details('show', uid)
        if not tvshow_details or not tvshow_details.get('ids', {}).get('slug'):
            return
        return self._get_upnext_episodes(tvshow_details, get_single_episode=get_single_episode)

    def _get_upnext_episodes(self, tvshow_details, get_single_episode=False):
        items = []
        slug = tvshow_details.get('ids', {}).get('slug')
        response = self.get_show_progress(slug)
        if not response:
            return
        reset_at = utils.convert_timestamp(response['reset_at']) if response.get('reset_at') else None
        for season in response.get('seasons') or []:
            s_num = season.get('number')
            for episode in season.get('episodes') or []:
                if episode.get('completed'):
                    if not reset_at:
                        continue  # Already watched and user hasn't restarted watching so not an upnext episode
                    elif utils.convert_timestamp(episode.get('last_watched_at')) >= reset_at:
                        continue  # Already watched since user restarted watching so not an upnext episode
                e_num = episode.get('number')
                item = {
                    'path': PLUGINPATH,
                    'params': {
                        'info': 'details',
                        'tmdb_id': tvshow_details.get('ids', {}).get('tmdb'),
                        'tmdb_type': 'tv',
                        'season': s_num,
                        'episode': e_num},
                    'art': {},
                    'infoproperties': {},
                    'infolabels': {
                        'tvshowtitle': tvshow_details.get('title'),
                        'mediatype': 'episode',
                        'season': s_num,
                        'episode': e_num},
                    'unique_ids': {'tvshow.{}'.format(k): v for k, v in tvshow_details.get('ids', {}).items()}}

                # Get some extra info about air date etc if only getting a single episode
                if get_single_episode:
                    episode_details = self.get_details('show', slug, s_num, e_num)
                    air_date = utils.convert_timestamp(episode_details.get('first_aired'), utc_convert=True)
                    item['infolabels']['premiered'] = air_date.strftime('%Y-%m-%d')
                    item['infolabels']['year'] = air_date.strftime('%Y')
                    item['infolabels']['duration'] = utils.try_parse_int(episode_details.get('runtime')) // 60
                    item['infolabels']['plot'] = episode_details.get('overview')
                    item['infolabels']['title'] = item['label'] = episode_details.get('title')
                    for k, v in episode_details.get('ids', {}).items():
                        if v and k not in item['unique_ids']:
                            item['unique_ids'][k] = v
                    return item

                items.append(item)
        if not get_single_episode:
            return items  # TODO: Return first season if none for upnext season (maybe do elsewhere)

    def get_calendar(self, tmdbtype, user=True, start_date=None, days=None):
        user = 'my' if user else 'all'
        return self.get_response_json('calendars', user, tmdbtype, start_date, days, extended='full')

    @use_activity_cache(cache_days=cache.CACHE_SHORT)
    def get_calendar_episodes(self, startdate=0, days=1):
        if not self.authorize():
            return

        # Broaden date range in case utc conversion bumps into different day
        mod_date = utils.try_parse_int(startdate) - 1
        mod_days = utils.try_parse_int(days) + 2

        # Get our calendar response
        date = datetime.date.today() + datetime.timedelta(days=mod_date)
        return self.get_calendar('shows', True, start_date=date.strftime('%Y-%m-%d'), days=mod_days)


class _TraktSyncMixin():
    def sync_item(self, method, trakt_type, unique_id, id_type, season=None, episode=None):
        """
        methods = history watchlist collection recommendations
        trakt_type = movie, show, season, episode
        """
        if not unique_id or not id_type or not trakt_type or not method:
            return
        base_trakt_type = 'show' if trakt_type in ['season', 'episode'] else trakt_type
        if id_type != 'slug':
            unique_id = self.get_id(id_type, unique_id, base_trakt_type, output_type='slug')
        if not unique_id:
            return
        item = self.get_details(base_trakt_type, unique_id, season=season, episode=episode, extended=None)
        if not item:
            return
        return self.post_response('sync', method, postdata={'{}s'.format(trakt_type): [item]})

    def _get_activity_timestamp(self, activities, activity_type=None, activity_key=None):
        if not activities:
            return
        if not activity_type:
            return activities.get('all', '')
        if not activity_key:
            return activities.get('{}s'.format(activity_type), {})
        return activities.get('{}s'.format(activity_type), {}).get(activity_key)

    def _get_last_activity(self, activity_type=None, activity_key=None):
        if not self.authorize():
            return
        if not self.last_activities:
            self.last_activities = self.get_response_json('sync/last_activities')
            # self.last_activities = self.get_request('sync/last_activities', cache_days=0.0007)  # Cache for approx 1 minute to prevent rapid recalls
        return self._get_activity_timestamp(self.last_activities, activity_type=activity_type, activity_key=activity_key)

    @use_activity_cache(cache_days=cache.CACHE_SHORT, pickle_object=True)
    def _get_sync_response(self, path, extended=None):
        """ Quick sub-cache routine to avoid recalling full sync list if we also want to quicklist it """
        return self.get_response_json(path, extended=extended, limit=0)

    def _get_sync(self, path, trakt_type, id_type=None, extended=None):
        """ Get sync list """
        if not self.authorize():
            return
        response = self._get_sync_response(path, extended=extended)
        if not id_type:
            return response
        if response and trakt_type:
            return {i.get(trakt_type, {}).get('ids', {}).get(id_type): i
                    for i in response
                    if i.get(trakt_type, {}).get('ids', {}).get(id_type)}

    @use_activity_cache('movies', 'watched_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_watched_movies(self, trakt_type, id_type=None):
        return self._get_sync('sync/watched/movies', 'movie', id_type=id_type)

    # Watched shows sync uses short cache as needed for progress checks and new episodes might air tomorrow
    @use_activity_cache('episodes', 'watched_at', cache.CACHE_SHORT, pickle_object=True)
    def get_sync_watched_shows(self, trakt_type, id_type=None):
        return self._get_sync('sync/watched/shows', 'show', id_type=id_type)

    @use_activity_cache('movies', 'collected_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_collection_movies(self, trakt_type, id_type=None):
        return self._get_sync('sync/collection/movies', 'movie', id_type=id_type)

    @use_activity_cache('episodes', 'collected_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_collection_shows(self, trakt_type, id_type=None):
        return self._get_sync('sync/collection/shows', trakt_type, id_type=id_type)

    @use_activity_cache('movies', 'watched_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_playback_movies(self, trakt_type, id_type=None):
        return self._get_sync('sync/playback/movies', 'movie', id_type=id_type)

    @use_activity_cache('episodes', 'watched_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_playback_shows(self, trakt_type, id_type=None):
        return self._get_sync('sync/playback/episodes', trakt_type, id_type=id_type)

    @use_activity_cache('movies', 'watchlisted_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_watchlist_movies(self, trakt_type, id_type=None):
        return self._get_sync('sync/watchlist/movies', 'movie', id_type=id_type)

    @use_activity_cache('shows', 'watchlisted_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_watchlist_shows(self, trakt_type, id_type=None):
        return self._get_sync('sync/watchlist/shows', 'shows', id_type=id_type)

    @use_activity_cache('movies', 'recommendations_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_recommendations_movies(self, trakt_type, id_type=None):
        return self._get_sync('sync/recommendations/movies', 'movie', id_type=id_type)

    @use_activity_cache('shows', 'recommendations_at', cache.CACHE_LONG, pickle_object=True)
    def get_sync_recommendations_shows(self, trakt_type, id_type=None):
        return self._get_sync('sync/recommendations/shows', 'shows', id_type=id_type)

    def get_sync(self, sync_type, trakt_type, id_type=None):
        if sync_type == 'watched':
            func = self.get_sync_watched_movies if trakt_type == 'movie' else self.get_sync_watched_shows
        elif sync_type == 'collection':
            func = self.get_sync_collection_movies if trakt_type == 'movie' else self.get_sync_collection_shows
        elif sync_type == 'playback':
            func = self.get_sync_playback_movies if trakt_type == 'movie' else self.get_sync_playback_shows
        elif sync_type == 'watchlist':
            func = self.get_sync_watchlist_movies if trakt_type == 'movie' else self.get_sync_watchlist_shows
        elif sync_type == 'recommendations':
            func = self.get_sync_recommendations_movies if trakt_type == 'movie' else self.get_sync_recommendations_shows
        else:
            return
        sync_name = '{}.{}.{}'.format(sync_type, trakt_type, id_type)
        self.sync[sync_name] = self.sync.get(sync_name) or func(trakt_type, id_type)
        return self.sync[sync_name] or {}


class TraktAPI(RequestAPI, _TraktSyncMixin, _TraktItemLists, _TraktProgressMixin):
    def __init__(self):
        super(TraktAPI, self).__init__(req_api_url=API_URL, req_api_name='Trakt')
        self.authorization = ''
        self.attempted_login = False
        self.dialog_noapikey_header = u'{0} {1} {2}'.format(ADDON.getLocalizedString(32007), self.req_api_name, ADDON.getLocalizedString(32011))
        self.dialog_noapikey_text = ADDON.getLocalizedString(32012)
        self.client_id = CLIENT_ID
        self.client_secret = CLIENT_SECRET
        self.headers = {'trakt-api-version': '2', 'trakt-api-key': self.client_id, 'Content-Type': 'application/json'}
        self.last_activities = {}
        self.sync_activities = {}
        self.sync = {}
        self.authorize()

    def authorize(self, login=False):
        # Already got authorization so return credentials
        if self.authorization:
            return self.authorization

        # Get our saved credentials from previous login
        token = self.get_stored_token()
        if token.get('access_token'):
            self.authorization = token
            self.headers['Authorization'] = 'Bearer {0}'.format(self.authorization.get('access_token'))

        # No saved credentials and user trying to use a feature that requires authorization so ask them to login
        elif login:
            if not self.attempted_login and xbmcgui.Dialog().yesno(
                    self.dialog_noapikey_header,
                    self.dialog_noapikey_text,
                    nolabel=xbmc.getLocalizedString(222),
                    yeslabel=xbmc.getLocalizedString(186)):
                self.login()
            self.attempted_login = True

        # First time authorization in this session so let's confirm
        if self.authorization and xbmcgui.Window(10000).getProperty('TMDbHelper.TraktIsAuth') != 'True':
            # Check if we can get a response from user account
            utils.kodi_log('Checking Trakt authorization', 1)
            response = self.get_simple_api_request('https://api.trakt.tv/sync/last_activities', headers=self.headers)
            # 401 is unauthorized error code so let's try refreshing the token
            if response.status_code == 401:
                utils.kodi_log('Trakt unauthorized!', 1)
                self.authorization = self.refresh_token()
            # Authorization confirmed so let's set a window property for future reference in this session
            if self.authorization:
                utils.kodi_log('Trakt user account authorized', 1)
                xbmcgui.Window(10000).setProperty('TMDbHelper.TraktIsAuth', 'True')

        return self.authorization

    def get_stored_token(self):
        try:
            token = loads(ADDON.getSettingString('trakt_token')) or {}
        except Exception as exc:
            token = {}
            utils.kodi_log(exc, 1)
        return token

    def logout(self):
        token = self.get_stored_token()

        if not xbmcgui.Dialog().yesno(ADDON.getLocalizedString(32212), ADDON.getLocalizedString(32213)):
            return

        if token:
            response = self.get_api_request('https://api.trakt.tv/oauth/revoke', dictify=False, postdata={
                'token': token.get('access_token', ''),
                'client_id': self.client_id,
                'client_secret': self.client_secret})
            if response and response.status_code == 200:
                msg = ADDON.getLocalizedString(32216)
                ADDON.setSettingString('trakt_token', '')
            else:
                msg = ADDON.getLocalizedString(32215)
        else:
            msg = ADDON.getLocalizedString(32214)

        xbmcgui.Dialog().ok(ADDON.getLocalizedString(32212), msg)

    def login(self):
        self.code = self.get_api_request('https://api.trakt.tv/oauth/device/code', postdata={'client_id': self.client_id})
        if not self.code.get('user_code') or not self.code.get('device_code'):
            return  # TODO: DIALOG: Authentication Error
        self.progress = 0
        self.interval = self.code.get('interval', 5)
        self.expires_in = self.code.get('expires_in', 0)
        self.auth_dialog = xbmcgui.DialogProgress()
        self.auth_dialog.create(
            ADDON.getLocalizedString(32097),
            ADDON.getLocalizedString(32096),
            ADDON.getLocalizedString(32095) + ': [B]' + self.code.get('user_code') + '[/B]')
        self.poller()

    def refresh_token(self):
        utils.kodi_log('Attempting to refresh Trakt token', 1)
        if not self.authorization or not self.authorization.get('refresh_token'):
            utils.kodi_log('Trakt refresh token not found!', 1)
            return
        postdata = {
            'refresh_token': self.authorization.get('refresh_token'),
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
            'grant_type': 'refresh_token'}
        self.authorization = self.get_api_request('https://api.trakt.tv/oauth/token', postdata=postdata)
        if not self.authorization or not self.authorization.get('access_token'):
            utils.kodi_log('Failed to refresh Trakt token!', 1)
            return
        self.on_authenticated(auth_dialog=False)
        utils.kodi_log('Trakt token refreshed', 1)
        return self.authorization

    def poller(self):
        if not self.on_poll():
            self.on_aborted()
            return
        if self.expires_in <= self.progress:
            self.on_expired()
            return
        self.authorization = self.get_api_request('https://api.trakt.tv/oauth/device/token', postdata={'code': self.code.get('device_code'), 'client_id': self.client_id, 'client_secret': self.client_secret})
        if self.authorization:
            self.on_authenticated()
            return
        xbmc.Monitor().waitForAbort(self.interval)
        if xbmc.Monitor().abortRequested():
            return
        self.poller()

    def on_aborted(self):
        """Triggered when device authentication was aborted"""
        utils.kodi_log(u'Trakt authentication aborted!', 1)
        self.auth_dialog.close()

    def on_expired(self):
        """Triggered when the device authentication code has expired"""
        utils.kodi_log(u'Trakt authentication expired!', 1)
        self.auth_dialog.close()

    def on_authenticated(self, auth_dialog=True):
        """Triggered when device authentication has been completed"""
        utils.kodi_log(u'Trakt authenticated successfully!', 1)
        ADDON.setSettingString('trakt_token', dumps(self.authorization))
        self.headers['Authorization'] = 'Bearer {0}'.format(self.authorization.get('access_token'))
        if auth_dialog:
            self.auth_dialog.close()

    def on_poll(self):
        """Triggered before each poll"""
        if self.auth_dialog.iscanceled():
            self.auth_dialog.close()
            return False
        else:
            self.progress += self.interval
            progress = (self.progress * 100) / self.expires_in
            self.auth_dialog.update(int(progress))
            return True

    def post_response(self, *args, **kwargs):
        postdata = kwargs.pop('postdata', None)
        if not postdata:
            return
        return self.get_simple_api_request(
            self.get_request_url(*args, **kwargs), headers=self.headers, postdata=dumps(postdata))

    def get_response(self, *args, **kwargs):
        return self.get_api_request(self.get_request_url(*args, **kwargs), headers=self.headers)

    def get_response_json(self, *args, **kwargs):
        try:
            return self.get_api_request(self.get_request_url(*args, **kwargs), headers=self.headers).json()
        except ValueError:
            return {}
        except AttributeError:
            return {}

    def _get_id(self, id_type, unique_id, trakt_type=None, output_type=None):
        response = self.get_request_lc('search', id_type, unique_id, type=trakt_type)
        for i in response:
            if i.get('type') != trakt_type:
                continue
            if '{}'.format(i.get(trakt_type, {}).get('ids', {}).get(id_type)) != '{}'.format(unique_id):
                continue
            if not output_type:
                return i.get(trakt_type, {}).get('ids', {})
            return i.get(trakt_type, {}).get('ids', {}).get(output_type)

    def get_id(self, id_type, unique_id, trakt_type=None, output_type=None):
        """
        trakt_type: movie, show, episode, person, list
        output_type: trakt, slug, imdb, tmdb, tvdb
        """
        return cache.use_cache(
            self._get_id, id_type, unique_id, trakt_type=trakt_type, output_type=output_type,
            cache_name='trakt_get_id.{}.{}.{}.{}'.format(id_type, unique_id, trakt_type, output_type),
            cache_days=cache.CACHE_LONG)

    def get_details(self, trakt_type, id_num, season=None, episode=None, extended='full'):
        if not season or not episode:
            return self.get_request_sc(trakt_type + 's', id_num, extended=extended)
        return self.get_request_sc(trakt_type + 's', id_num, 'seasons', season, 'episodes', episode, extended=extended)
