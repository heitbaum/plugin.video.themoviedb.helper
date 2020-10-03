import xbmc
import xbmcgui
import datetime
import resources.lib.utils as utils
import resources.lib.cache as cache
import resources.lib.plugin as plugin
import resources.lib.paginated as paginated
from json import loads, dumps
from resources.lib.requestapi import RequestAPI
from resources.lib.plugin import ADDON, PLUGINPATH
from resources.lib.paginated import PaginatedItems
from resources.lib.traktitems import TraktItems


API_URL = 'https://api.trakt.tv/'
CLIENT_ID = 'e6fde6173adf3c6af8fd1b0694b9b84d7c519cefc24482310e1de06c6abe5467'
CLIENT_SECRET = '15119384341d9a61c751d8d515acbc0dd801001d4ebe85d3eef9885df80ee4d9'


class _TraktItemLists():
    def get_itemlist_sorted(self, *args, **kwargs):
        response = self.get_response(*args, extended=kwargs.get('extended'), limit=0)
        if not response:
            return
        return TraktItems(
            items=response.json(),
            trakt_type=kwargs.get('trakt_type'),
            sort_by=kwargs.get('sort_by') or response.headers.get('X-Sort-By'),
            sort_how=kwargs.get('sort_how') or response.headers.get('X-Sort-How')).get_sorted_items()

    def get_itemlist_cached(self, *args, **kwargs):
        params = {
            'cache_name': 'trakt.sortedlist',
            'cache_combine_name': True,
            'cache_days': 0.125,
            'cache_refresh': kwargs.get('cache_refresh', False),
            'sort_by': kwargs.get('sort_by', None),
            'sort_how': kwargs.get('sort_how', None),
            'trakt_type': kwargs.get('trakt_type', None),
            'extended': kwargs.get('extended', None)}
        items = cache.use_cache(self.get_itemlist_sorted, *args, **params)
        return PaginatedItems(items, page=kwargs.get('page'), limit=kwargs.get('limit'))

    def _get_itemlist_finished(self, response, trakt_type, item_key=None, params=None, next_page=False):
        if not response:
            return
        items = self.get_list_info(response.json(), trakt_type, item_key=item_key, params=params)
        if not items:
            return
        if next_page:
            items += paginated.get_next_page(response.headers)
        return items

    def get_synclist_cached(self, sync_type, trakt_type, activity_type, activity_key, item_key=None, page=1, limit=20, params=None, sort_by=None, sort_how=None, next_page=True):
        cache_name = 'trakt.synclist.{}.{}.{}.{}'.format(sync_type, trakt_type, sort_by, sort_how)
        response_items = self.use_activity_cache(
            activity_type, activity_key, cache_name, self.cache_long,
            func=TraktItems(
                items=self.get_sync(sync_type, trakt_type),
                trakt_type=trakt_type,
                sort_by=sort_by,
                sort_how=sort_how).get_sorted_items)
        response = PaginatedItems(response_items, page=page, limit=limit)
        return self._get_itemlist_finished(
            response, trakt_type, item_key=item_key, params=params, next_page=next_page)

    def get_basic_list(self, path, trakt_type, item_key=None, page=1, limit=20, params=None, authorize=False, sort_by=None, sort_how=None, extended=None):
        if authorize and not self.authorize():
            return
        func = self.get_itemlist_cached if sort_by is not None else self.get_response
        response = func(
            path, page=page, limit=limit, sort_by=sort_by, sort_how=sort_how, extended=extended,
            trakt_type=trakt_type if sort_by is not None else None)
        return self._get_itemlist_finished(
            response, trakt_type, item_key=item_key, params=params, next_page=True)

    def get_userlist(self, list_slug, user_slug=None, page=1, limit=20, params=None, authorize=False, sort_by=None, sort_how=None, extended=None):
        if authorize and not self.authorize():
            return
        path = 'users/{}/lists/{}/items'.format(user_slug or 'me', list_slug)
        response = self.get_itemlist_cached(
            path, page=page, limit=limit, sort_by=sort_by, sort_how=sort_how, extended=extended)
        if not response:
            return
        items, movies, shows = [], [], []
        for i in response.json():
            trakt_type = i.get('type')
            if trakt_type not in ['movie', 'show']:
                continue
            item = self.get_info(i, trakt_type, item_key=trakt_type, params_definition=params)
            if not item:
                continue
            items.append(item)
            if trakt_type == 'movie':
                movies.append(item)
            elif trakt_type == 'show':
                shows.append(item)
        if not items:
            return
        return {
            'items': items,
            'movies': movies,
            'tvshows': shows,
            'next_page': paginated.get_next_page(response.headers)}

    def get_imdb_top250(self):
        return self.get_itemlist_cached(
            'users', 'nielsz', 'lists', 'active-imdb-top-250', 'items',
            sort_by='rank', sort_how='asc', limit=250)

    def get_inprogress_shows_list(self, page=1, limit=20, params=None):
        response = PaginatedItems(
            self._get_inprogress_shows(),
            page=page, limit=utils.try_parse_int(limit) or 20)
        return self._get_itemlist_finished(
            response, 'show', item_key='show', params=params, next_page=True)

    def get_upnext_episodes_list(self, page=1, limit=20):
        response = PaginatedItems(
            self._get_inprogress_shows(), page=page, limit=utils.try_parse_int(limit) or 20)
        if not response or not response.items:
            return
        items = []
        for i in response.items:
            next_episode = self.get_upnext_episodes(i.get('show', {}), get_single_episode=True)
            if not next_episode:
                continue
            items.append(next_episode)
        return items

    def get_upnext_list(self, unique_id, id_type='slug', page=1, limit=20):
        slug = unique_id if id_type == 'slug' else self.get_id(
            id_type=id_type, unique_id=unique_id, trakt_type='show', output_type='slug')
        if not slug:
            return
        tvshow_details = self.get_details('show', slug)
        if not tvshow_details:
            return
        response = PaginatedItems(
            self.get_upnext_episodes(tvshow_details),
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
                ('{}: {}'.format(ADDON.getLocalizedString(32287), ADDON.getLocalizedString(32286)), 'Container.Update({}&sort_by=rank&sort_how=asc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), ADDON.getLocalizedString(32106)), 'Container.Update({}&sort_by=added&sort_how=desc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(369)), 'Container.Update({}&sort_by=title&sort_how=asc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(345)), 'Container.Update({}&sort_by=year&sort_how=desc)'.format(path)),
                ('{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(590)), 'Container.Update({}&sort_by=random)'.format(path))]
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


class _TraktMethodsMixin():
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
            cache_days=self.cache_long)

    def get_details(self, trakt_type, id_num, season=None, episode=None, extended='full'):
        if not season or not episode:
            return self.get_response_json(trakt_type + 's', id_num, extended=extended)
        return self.get_response_json(trakt_type + 's', id_num, 'seasons', season, 'episodes', episode, extended=extended)

    def get_title(self, item):
        return item.get('title', '')

    def get_infolabels(self, item, trakt_type, infolabels=None, detailed=True):
        infolabels = infolabels or {}
        infolabels['title'] = self.get_title(item)
        infolabels['year'] = item.get('year')
        infolabels['mediatype'] = plugin.convert_type(plugin.convert_trakt_type(trakt_type), plugin.TYPE_DB)
        return utils.del_empty_keys(infolabels)

    def get_unique_ids(self, item, unique_ids=None):
        unique_ids = unique_ids or {}
        unique_ids['tmdb'] = item.get('ids', {}).get('tmdb')
        unique_ids['imdb'] = item.get('ids', {}).get('imdb')
        unique_ids['tvdb'] = item.get('ids', {}).get('tvdb')
        unique_ids['slug'] = item.get('ids', {}).get('slug')
        unique_ids['trakt'] = item.get('ids', {}).get('trakt')
        return utils.del_empty_keys(unique_ids)

    def get_info(self, item, trakt_type, base_item=None, detailed=True, params_definition=None, item_key=None):
        base_item = base_item or {}
        item_info = item.get(item_key) or {} if item_key else item
        if item and trakt_type:
            base_item['label'] = self.get_title(item_info)
            base_item['infolabels'] = self.get_infolabels(item_info, trakt_type, base_item.get('infolabels', {}), detailed=detailed)
            base_item['unique_ids'] = self.get_unique_ids(item_info, base_item.get('unique_ids', {}))
            base_item['params'] = utils.get_params(
                item_info, plugin.convert_trakt_type(trakt_type),
                tmdb_id=base_item.get('unique_ids', {}).get('tmdb'),
                params=base_item.get('params', {}),
                definition=params_definition)
            base_item['path'] = PLUGINPATH
        return base_item

    def get_list_info(self, response_json, trakt_type, item_key=None, params=None):
        if not item_key:
            return [self.get_info(i, trakt_type, params_definition=params)
                    for i in response_json if i.get('ids', {}).get('tmdb')]
        return [self.get_info(i, trakt_type, params_definition=params, item_key=item_key)
                for i in response_json if i.get(item_key, {}).get('ids', {}).get('tmdb')]

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


class _TraktProgressMixin():
    def get_movie_playcount(self, id_type, unique_id):
        return self.get_sync('watched', 'movie', id_type).get(unique_id, {}).get('plays')

    def get_episode_playcount(self, id_type, unique_id, season, episode):
        season = utils.try_parse_int(season, fallback=-2)  # Make fallback -2 to prevent matching on 0
        episode = utils.try_parse_int(episode, fallback=-2)  # Make fallback -2 to prevent matching on 0
        for i in self.get_sync('watched', 'show', id_type).get(unique_id, {}).get('seasons', []):
            if i.get('number', -1) != season:
                continue
            for j in i.get('episodes', []):
                if j.get('number', -1) == episode:
                    return j.get('plays', 1)

    def get_episodes_airedcount(self, id_type, unique_id, season=None):
        # For seasons we need to lookup indiviual seasons as Trakt doesn't provide aired count per season in watched sync
        if season is not None:
            season = utils.try_parse_int(season, fallback=-2)
            slug = self.get_id(id_type, unique_id, trakt_type='show', output_type='slug')
            for i in self.get_request_sc('shows', slug, 'seasons', extended='full'):
                if i.get('number', -1) == season:
                    return i.get('aired_episodes')
            return 0
        # For shows aired count we use short (not long) cache watched sync because aired numbers can change day to day
        return self.get_sync('watched_sc', 'show', id_type).get(
            unique_id, {}).get('show', {}).get('aired_episodes')

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

    def _get_inprogress_shows(self):
        items = []
        if not self.authorize():
            return
        recently_watched = TraktItems(self.get_sync('watched_sc', 'show'), sort_by='watched', sort_how='desc').get_sorted_items()
        hidden_shows = self.get_hiddenitems('show')
        for i in recently_watched:
            if i.get('show', {}).get('ids', {}).get('slug') in hidden_shows:
                continue  # Show is hidden so skip
            if i.get('show', {}).get('aired_episodes') > self.get_episodes_watchcount(tvshow=i):
                items.append(i)  # More aired episodes than watched so must be in-progress
        return items

    def get_show_progress(self, uid, hidden=False, specials=False, count_specials=False):
        if not uid:
            return
        return self.use_activity_cache(
            'show', 'watched_at', 'trakt.shows.{}.progress.watched'.format(uid), self.cache_short,
            self.get_response_json, 'shows', uid, 'progress/watched')

    def get_upnext_episodes(self, tvshow_details, get_single_episode=False):
        if not tvshow_details or not tvshow_details.get('ids', {}).get('slug'):
            return
        cache_name = 'trakt.shows.{}.{}.upnext.episodes'.format(
            tvshow_details.get('ids', {}).get('slug'), get_single_episode)
        return self.use_activity_cache(
            'show', 'watched_at', cache_name, self.cache_short,
            self._get_upnext_episodes, tvshow_details, get_single_episode=get_single_episode)

    def _get_upnext_episodes(self, tvshow_details, get_single_episode=False):
        items = []
        slug = tvshow_details.get('ids', {}).get('slug')
        response = self.get_show_progress(slug)
        reset_at = utils.convert_timestamp(response['reset_at']) if response.get('reset_at') else None
        for season in response.get('seasons') or []:
            s_num = season.get('number')
            for episode in season.get('episodes') or []:
                if episode.get('completed'):
                    if not reset_at:
                        continue  # Already watched and user hasn't restarted watching so not an upnext episode
                    elif utils.convert_timestamp(episode.get('last_watched_at')) >= reset_at:
                        continue  # Already watched since user restarted watching so not an upnext episode
                item = {
                    'path': PLUGINPATH,
                    'params': {
                        'info': 'details',
                        'tmdb_id': tvshow_details.get('ids', {}).get('tmdb'),
                        'tmdb_type': 'tv',
                        'season': s_num,
                        'episode': episode.get('number')},
                    'art': {},
                    'infoproperties': {},
                    'infolabels': {
                        'tvshowtitle': tvshow_details.get('title'),
                        'mediatype': 'episode',
                        'season': s_num,
                        'episode': episode.get('number')},
                    'unique_ids': {
                        'tvshow.tmdb': tvshow_details.get('ids', {}).get('tmdb'),
                        'tvshow.tvdb': tvshow_details.get('ids', {}).get('tvdb'),
                        'tvshow.imdb': tvshow_details.get('ids', {}).get('imdb'),
                        'tvshow.slug': tvshow_details.get('ids', {}).get('slug'),
                        'tvshow.trakt': tvshow_details.get('ids', {}).get('trakt')}}
                if get_single_episode:
                    return item
                items.append(item)
        if not get_single_episode:
            return items  # TODO: Return first season if none for upnext season (maybe do elsewhere)

    def get_calendar(self, tmdbtype, user=True, start_date=None, days=None):
        user = 'my' if user else 'all'
        return self.get_response_json('calendars', user, tmdbtype, start_date, days, extended='full')

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


class TraktAPI(RequestAPI, _TraktMethodsMixin, _TraktSyncMixin, _TraktItemLists, _TraktProgressMixin):
    def __init__(
            self,
            cache_short=ADDON.getSettingInt('cache_list_days'),
            cache_long=ADDON.getSettingInt('cache_details_days')):
        super(TraktAPI, self).__init__(
            cache_short=cache_short,
            cache_long=cache_long,
            req_api_url=API_URL,
            req_api_name='Trakt')
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

    def get_response(self, *args, **kwargs):
        return self.get_api_request(self.get_request_url(*args, **kwargs), headers=self.headers)

    def get_response_json(self, *args, **kwargs):
        try:
            return self.get_api_request(self.get_request_url(*args, **kwargs), headers=self.headers).json()
        except ValueError:
            return {}
        except AttributeError:
            return {}
