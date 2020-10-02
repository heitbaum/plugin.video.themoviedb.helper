
import sys
import xbmc
import xbmcplugin
import resources.lib.utils as utils
import resources.lib.plugin as plugin
import resources.lib.constants as constants
import resources.lib.rpc as rpc
from resources.lib.script import Script
from resources.lib.listitem import ListItem
from resources.lib.tmdb import TMDb
from resources.lib.fanarttv import FanartTV
from resources.lib.itemutils import ItemUtils
from resources.lib.players import Players
from resources.lib.plugin import ADDON
from resources.lib.basedir import BaseDirLists
from resources.lib.tmdblists import TMDbLists
from resources.lib.traktlists import TraktLists
from resources.lib.search import SearchLists
from resources.lib.userdiscover import UserDiscoverLists


class Container(object, TMDbLists, BaseDirLists, SearchLists, UserDiscoverLists, TraktLists):
    def __init__(self):
        self.handle = int(sys.argv[1])
        self.paramstring = utils.try_decode_string(sys.argv[2][1:])
        self.params = utils.parse_paramstring(sys.argv[2][1:])
        self.allow_pagination = True
        self.update_listing = False
        self.plugin_category = ''
        self.container_content = ''
        self.container_update = None
        self.container_refresh = False
        self.item_type = None
        self.kodi_db = None
        self.library = None
        self.tmdb_cache_only = True
        self.ftv_lookup = ADDON.getSettingBool('fanarttv_lookup')
        self.ftv_widget_lookup = ADDON.getSettingBool('widget_fanarttv_lookup')
        self.is_widget = True if self.params.get('widget') else False

        # Filters and Exclusions
        self.filter_key = self.params.get('filter_key', None)
        self.filter_value = utils.split_items(self.params.get('filter_value', None))[0]
        self.exclude_key = self.params.get('exclude_key', None)
        self.exclude_value = utils.split_items(self.params.get('exclude_value', None))[0]

        # Legacy code clean-up for back compatibility
        # TODO: Maybe only necessary for player code??
        if 'type' in self.params:
            self.params['tmdb_type'] = self.params.pop('type')
        if self.params.get('tmdb_type') in ['season', 'episode']:
            self.params['tmdb_type'] = 'tv'

    def add_items(self, items=None, allow_pagination=True, parent_params=None, kodi_db=None, tmdb_cache_only=True):
        if not items:
            return
        listitem_utils = ItemUtils(
            kodi_db=self.kodi_db,
            ftv_api=FanartTV(cache_only=self.ftv_is_cache_only(is_widget=self.is_widget)))
        for i in items:
            if not allow_pagination and 'next_page' in i:
                continue
            if self.item_is_excluded(i):
                continue  # TODO: Filter out unaired items and/or format labels
            listitem = ListItem(parent_params=parent_params, **i)
            listitem.set_details(details=listitem_utils.get_tmdb_details(listitem, cache_only=tmdb_cache_only))  # Quick because only get cached
            listitem.set_episode_label()
            if parent_params.get('info') not in constants.NO_LABEL_FORMATTING and listitem.is_unaired():
                continue
            listitem.set_details(details=listitem_utils.get_ftv_details(listitem), reverse=True)  # Slow when not cache only
            listitem.set_details(details=listitem_utils.get_kodi_details(listitem), reverse=True)  # Quick because local db
            listitem.set_playcount(playcount=listitem_utils.get_playcount_from_trakt(listitem))  # Quick because of agressive caching of Trakt object and pre-emptive dict comprehension
            listitem.set_standard_context_menu()  # Set the context menu items
            listitem.set_unique_ids_to_infoproperties()  # Add unique ids to properties so accessible in skins
            listitem.set_params_info_reroute()  # Reroute details to proper end point
            xbmcplugin.addDirectoryItem(
                handle=self.handle,
                url=listitem.get_url(),
                listitem=listitem.get_listitem(),
                isFolder=listitem.is_folder)

    def set_params_to_container(self, **kwargs):
        for k, v in kwargs.items():
            if not k or not v:
                continue
            try:
                xbmcplugin.setProperty(self.handle, u'Param.{}'.format(k), u'{}'.format(v))  # Set params to container properties
            except Exception as exc:
                utils.kodi_log(u'Error: {}\nUnable to set Param.{} to {}'.format(exc, k, v), 1)

    def finish_container(self, update_listing=False, plugin_category='', container_content=''):
        xbmcplugin.setPluginCategory(self.handle, plugin_category)  # Container.PluginCategory
        xbmcplugin.setContent(self.handle, container_content)  # Container.Content
        xbmcplugin.endOfDirectory(self.handle, updateListing=update_listing)

    def ftv_is_cache_only(self, is_widget=False):
        if is_widget and self.ftv_widget_lookup:
            return False
        if not is_widget and self.ftv_lookup:
            return False
        return True

    def item_is_excluded(self, item):
        if self.filter_key and self.filter_value:
            if self.filter_key in item.get('infolabels', {}):
                if utils.filtered_item(item['infolabels'], self.filter_key, self.filter_value):
                    return True
            elif self.filter_key in item.get('infoproperties', {}):
                if utils.filtered_item(item['infoproperties'], self.filter_key, self.filter_value):
                    return True
        if self.exclude_key and self.exclude_value:
            if self.exclude_key in item.get('infolabels', {}):
                if utils.filtered_item(item['infolabels'], self.exclude_key, self.exclude_value, True):
                    return True
            elif self.exclude_key in item.get('infoproperties', {}):
                if utils.filtered_item(item['infoproperties'], self.exclude_key, self.exclude_value, True):
                    return True

    def get_kodi_database(self, tmdb_type):
        if tmdb_type == 'movie':
            return rpc.KodiLibrary(dbtype='movie')
        if tmdb_type == 'tv':
            return rpc.KodiLibrary(dbtype='tvshow')

    def get_container_content(self, tmdb_type, season=None, episode=None):
        if tmdb_type == 'tv' and season and episode:
            return plugin.convert_type('episode', plugin.TYPE_CONTAINER)
        elif tmdb_type == 'tv' and season:
            return plugin.convert_type('season', plugin.TYPE_CONTAINER)
        return plugin.convert_type(tmdb_type, plugin.TYPE_CONTAINER)

    def get_items(self, **kwargs):
        info = kwargs.get('info')
        if info == 'pass':
            return
        if info == 'dir_search':
            return self.list_searchdir_router(**kwargs)
        if info == 'search':
            return self.list_search(**kwargs)
        if info == 'user_discover':
            return self.list_userdiscover(**kwargs)
        if info == 'dir_discover':
            return self.list_discoverdir_router(**kwargs)
        if info == 'discover':
            return self.list_discover(**kwargs)
        if info == 'all_items':
            return self.list_all_items(**kwargs)

        if not kwargs.get('tmdb_id'):
            kwargs['tmdb_id'] = TMDb().get_tmdb_id(**kwargs)

        if info == 'details':
            return self.list_details(**kwargs)
        if info == 'seasons':
            return self.list_seasons(**kwargs)
        if info == 'episodes':
            return self.list_episodes(**kwargs)
        if info == 'cast':
            return self.list_cast(**kwargs)
        if info == 'crew':
            return self.list_crew(**kwargs)
        if info == 'trakt_inprogress':
            return self.list_inprogress(**kwargs)
        if info == 'trakt_nextepisodes':
            return self.list_nextepisodes(**kwargs)
        if info == 'trakt_upnext':
            return self.list_upnext(**kwargs)
        if info == 'trakt_userlist':
            return self.list_userlist(**kwargs)
        if info in ['trakt_becauseyouwatched', 'trakt_becausemostwatched']:
            return self.list_becauseyouwatched(**kwargs)
        if info in constants.TMDB_BASIC_LISTS:
            return self.list_tmdb(**kwargs)
        if info in constants.TRAKT_BASIC_LISTS:
            return self.list_trakt(**kwargs)
        if info in constants.TRAKT_SYNC_LISTS:
            return self.list_sync(**kwargs)
        if info in constants.TRAKT_LIST_OF_LISTS:
            return self.list_lists(**kwargs)
        return self.list_basedir(info)

    def get_directory(self):
        items = self.get_items(**self.params)
        if not items:
            return
        self.add_items(
            items,
            allow_pagination=self.allow_pagination,
            parent_params=self.params,
            kodi_db=self.kodi_db,
            tmdb_cache_only=self.tmdb_cache_only)
        self.finish_container(
            update_listing=self.update_listing,
            plugin_category=self.plugin_category,
            container_content=self.container_content)
        self.set_params_to_container(**self.params)
        if self.container_update:
            xbmc.executebuiltin('Container.Update({})'.format(self.container_update))
        if self.container_refresh:
            xbmc.executebuiltin('Container.Refresh')

    def play_external(self):
        if not self.params.get('tmdb_id'):
            self.params['tmdb_id'] = TMDb().get_tmdb_id(**self.params)
        Players(**self.params).play()

    def context_related(self):
        if not self.params.get('tmdb_id'):
            self.params['tmdb_id'] = TMDb().get_tmdb_id(**self.params)
        self.params['container_update'] = True
        Script().related_lists(**self.params)

    def router(self):
        if self.params.get('info') == 'play':
            return self.play_external()
        if self.params.get('info') == 'related':
            return self.context_related()
        return self.get_directory()
