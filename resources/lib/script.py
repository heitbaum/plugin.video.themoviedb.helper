# -*- coding: utf-8 -*-
# Module: default
# Author: jurialmunkey
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html
import sys
import xbmc
import xbmcgui
import resources.lib.utils as utils
import resources.lib.basedir as basedir
from resources.lib.fanarttv import FanartTV
from resources.lib.tmdb import TMDb
from resources.lib.plugin import ADDON
from resources.lib.syncitem import SyncItem


class Script(object):
    def get_params(self):
        params = {}
        for arg in sys.argv:
            if arg == 'script.py':
                pass
            elif '=' in arg:
                arg_split = arg.split('=', 1)
                if arg_split[0] and arg_split[1]:
                    key, value = arg_split
                    value = value.strip('\'').strip('\"')
                    params.setdefault(key, value)
            else:
                params.setdefault(arg, True)
        return params

    def related_lists(self, tmdb_id=None, tmdb_type=None, season=None, episode=None, container_update=True, **kwargs):
        if not tmdb_id or not tmdb_type:
            return
        items = basedir.get_basedir_details(tmdb_type=tmdb_type, tmdb_id=tmdb_id, season=season, episode=episode)
        if not items or len(items) <= 1:
            return
        choice = xbmcgui.Dialog().contextmenu([i.get('label') for i in items])
        if choice == -1:
            return
        item = items[choice]
        params = item.get('params')
        if not params:
            return
        item['params']['tmdb_id'] = tmdb_id
        item['params']['tmdb_type'] = tmdb_type
        if season is not None:
            item['params']['season'] = season
            if episode is not None:
                item['params']['episode'] = episode
        if not container_update:
            return item
        path = 'Container.Update({})' if xbmc.getCondVisibility("Window.IsMedia") else 'ActivateWindow(videos,{},return)'
        path = path.format(utils.get_url(path=item.get('path'), **item.get('params')))
        xbmc.executebuiltin(path)

    def refresh_details(self, tmdb_id=None, tmdb_type=None, season=None, episode=None, **kwargs):
        if not tmdb_id or not tmdb_type:
            return
        with utils.busy_dialog():
            details = TMDb().get_details(tmdb_type, tmdb_id, season=season, episode=episode)
        if details:
            xbmcgui.Dialog().ok('TMDbHelper', ADDON.getLocalizedString(32234).format(tmdb_type, tmdb_id))
            xbmc.executebuiltin('Container.Refresh')

    def sync_item(self, trakt_type, unique_id, season=None, episode=None, id_type=None, **kwargs):
        SyncItem(trakt_type, unique_id, season, episode, id_type).sync()

    def manage_artwork(self, ftv_id=None, ftv_type=None, **kwargs):
        FanartTV().manage_artwork(ftv_id, ftv_type)

    def router(self):
        self.params = self.get_params()
        if not self.params:
            return
        if self.params.get('sync_item'):
            return self.sync_item(**self.params)
        if self.params.get('manage_artwork'):
            return self.manage_artwork(**self.params)
        if self.params.get('refresh_details'):
            return self.refresh_details(**self.params)
        if self.params.get('related_lists'):
            return self.related_lists(**self.params)
