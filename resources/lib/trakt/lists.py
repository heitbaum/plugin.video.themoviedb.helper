import random
import resources.lib.helpers.plugin as plugin
import resources.lib.helpers.constants as constants
from resources.lib.helpers.plugin import ADDON
from resources.lib.helpers.parser import try_int
# from resources.lib.helpers.decorators import timer_report


class TraktLists():
    def list_trakt(self, info, tmdb_type, page=None, randomise=False, **kwargs):
        info_model = constants.TRAKT_BASIC_LISTS.get(info)
        info_tmdb_type = info_model.get('tmdb_type') or tmdb_type
        trakt_type = plugin.convert_type(tmdb_type, plugin.TYPE_TRAKT)
        items = self.trakt_api.get_basic_list(
            path=info_model.get('path', '').format(trakt_type=trakt_type, **kwargs),
            trakt_type=trakt_type,
            params=info_model.get('params'),
            page=page,
            authorize=info_model.get('authorize', False),
            sort_by=info_model.get('sort_by', None),
            sort_how=info_model.get('sort_how', None),
            extended=info_model.get('extended', None),
            randomise=randomise)
        self.tmdb_cache_only = False
        self.kodi_db = self.get_kodi_database(info_tmdb_type)
        self.library = plugin.convert_type(info_tmdb_type, plugin.TYPE_LIBRARY)
        self.container_content = plugin.convert_type(info_tmdb_type, plugin.TYPE_CONTAINER)
        return items

    def list_sync(self, info, tmdb_type, page=None, **kwargs):
        info_model = constants.TRAKT_SYNC_LISTS.get(info)
        info_tmdb_type = info_model.get('tmdb_type') or tmdb_type
        items = self.trakt_api.get_sync_list(
            sync_type=info_model.get('sync_type', ''),
            trakt_type=plugin.convert_type(tmdb_type, plugin.TYPE_TRAKT),
            page=page,
            params=info_model.get('params'),
            sort_by=info_model.get('sort_by', None),
            sort_how=info_model.get('sort_how', None))
        self.tmdb_cache_only = False
        self.kodi_db = self.get_kodi_database(info_tmdb_type)
        self.library = plugin.convert_type(info_tmdb_type, plugin.TYPE_LIBRARY)
        self.container_content = plugin.convert_type(info_tmdb_type, plugin.TYPE_CONTAINER)
        return items

    def list_lists(self, info, page=None, **kwargs):
        info_model = constants.TRAKT_LIST_OF_LISTS.get(info)
        items = self.trakt_api.get_list_of_lists(
            path=info_model.get('path', '').format(**kwargs),
            page=page,
            authorize=info_model.get('authorize', False))
        self.library = 'video'
        return items

    def list_userlist(self, list_slug, user_slug=None, page=None, **kwargs):
        response = self.trakt_api.get_custom_list(
            page=page or 1,
            list_slug=list_slug,
            user_slug=user_slug,
            sort_by=kwargs.get('sort_by', None),
            sort_how=kwargs.get('sort_how', None),
            authorize=False if user_slug else True)
        if not response:
            return []
        self.tmdb_cache_only = False
        self.library = 'video'
        lengths = [
            len(response.get('movies', [])),
            len(response.get('tvshows', [])),
            len(response.get('persons', []))]
        if lengths.index(max(lengths)) == 0:
            self.container_content = 'movies'
        elif lengths.index(max(lengths)) == 1:
            self.container_content = 'tvshows'
        elif lengths.index(max(lengths)) == 2:
            self.container_content = 'actors'
        return response.get('items', []) + response.get('next_page', [])

    def list_becauseyouwatched(self, info, tmdb_type, page=None, **kwargs):
        trakt_type = plugin.convert_type(tmdb_type, plugin.TYPE_TRAKT)
        watched_items = self.trakt_api.get_sync_list(
            sync_type='watched',
            trakt_type=trakt_type,
            page=1,
            limit=5,
            next_page=False,
            params=None,
            sort_by='plays' if info == 'trakt_becausemostwatched' else 'watched',
            sort_how='desc')
        item = watched_items[random.randint(0, len(watched_items) - 1)]
        self.plugin_category = '{} {}'.format(ADDON.getLocalizedString(32288), item.get('label'))
        return self.list_tmdb(
            info='recommendations',
            tmdb_type=item.get('params', {}).get('tmdb_type'),
            tmdb_id=item.get('params', {}).get('tmdb_id'),
            page=1)

    def list_inprogress(self, info, tmdb_type, page=None, **kwargs):
        if tmdb_type != 'tv':
            return self.list_sync(info, tmdb_type, page, **kwargs)
        items = self.trakt_api.get_inprogress_shows_list(
            page=page, params={
                'info': 'trakt_upnext',
                'tmdb_type': 'tv',
                'tmdb_id': '{tmdb_id}'})
        self.tmdb_cache_only = False
        self.kodi_db = self.get_kodi_database(tmdb_type)
        self.library = plugin.convert_type(tmdb_type, plugin.TYPE_LIBRARY)
        self.container_content = plugin.convert_type(tmdb_type, plugin.TYPE_CONTAINER)
        return items

    def list_nextepisodes(self, info, tmdb_type, page=None, **kwargs):
        if tmdb_type != 'tv':
            return
        sort_by_premiered = True if ADDON.getSettingString('trakt_nextepisodesort') == 'airdate' else False
        items = self.trakt_api.get_upnext_episodes_list(page=page, sort_by_premiered=sort_by_premiered)
        self.tmdb_cache_only = False
        # self.kodi_db = self.get_kodi_database(tmdb_type)
        self.library = 'video'
        self.container_content = 'episodes'
        return items

    def list_trakt_calendar(self, info, startdate, days, page=None, **kwargs):
        items = self.trakt_api.get_calendar_episodes_list(
            try_int(startdate),
            try_int(days),
            page=page)
        self.tmdb_cache_only = False
        self.kodi_db = self.get_kodi_database('tv')
        self.library = 'video'
        self.container_content = 'episodes'
        return items

    def list_upnext(self, info, tmdb_type, tmdb_id, page=None, **kwargs):
        if tmdb_type != 'tv':
            return
        items = self.trakt_api.get_upnext_list(unique_id=tmdb_id, id_type='tmdb', page=page)
        self.tmdb_cache_only = False
        # self.kodi_db = self.get_kodi_database(tmdb_type)
        self.library = 'video'
        self.container_content = 'episodes'
        return items
