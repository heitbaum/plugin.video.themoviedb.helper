# -*- coding: utf-8 -*-
# Module: default
# Author: jurialmunkey
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html
import sys
import xbmc
import xbmcgui
import resources.lib.items.basedir as basedir
import resources.lib.helpers.window as window
import resources.lib.helpers.update as update
from resources.lib.fanarttv.api import FanartTV
from resources.lib.tmdb.api import TMDb
from resources.lib.trakt.api import TraktAPI
from resources.lib.helpers.plugin import ADDON
from resources.lib.helpers.rpc import get_jsonrpc
from resources.lib.trakt.sync import SyncItem
from resources.lib.helpers.decorators import busy_dialog
from resources.lib.helpers.parser import encode_url
from resources.lib.window.manager import WindowManager
from resources.lib.player.players import Players


WM_PARAMS = ['add_path', 'add_query', 'close_dialog', 'reset_path', 'call_id', 'call_path', 'call_update']


def play_external(**kwargs):
    kwargs['tmdb_type'] = kwargs.get('play')
    if not kwargs.get('tmdb_id'):
        kwargs['tmdb_id'] = TMDb().get_tmdb_id(**kwargs)
    Players(**kwargs).play()


def split_value(split_value, separator=None, **kwargs):
    split_value = split_value or ''
    for x, i in enumerate(split_value.split(separator or ' / ')):
        name = '{}.{}'.format(kwargs.get('property') or 'TMDbHelper.Split', x)
        window.get_property(name, set_property=i, prefix=-1)


def sync_item(trakt_type, unique_id, season=None, episode=None, id_type=None, **kwargs):
    SyncItem(trakt_type, unique_id, season, episode, id_type).sync()


def manage_artwork(ftv_id=None, ftv_type=None, **kwargs):
    FanartTV().manage_artwork(ftv_id, ftv_type)


def related_lists(tmdb_id=None, tmdb_type=None, season=None, episode=None, container_update=True, **kwargs):
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
    path = path.format(encode_url(path=item.get('path'), **item.get('params')))
    xbmc.executebuiltin(path)


def refresh_details(tmdb_id=None, tmdb_type=None, season=None, episode=None, **kwargs):
    if not tmdb_id or not tmdb_type:
        return
    with busy_dialog():
        details = TMDb().get_details(tmdb_type, tmdb_id, season=season, episode=episode)
    if details:
        xbmcgui.Dialog().ok('TMDbHelper', ADDON.getLocalizedString(32234).format(tmdb_type, tmdb_id))
        xbmc.executebuiltin('Container.Refresh')


def kodi_setting(kodi_setting, **kwargs):
    method = "Settings.GetSettingValue"
    params = {"setting": kodi_setting}
    response = get_jsonrpc(method, params)
    window.get_property(
        name=kwargs.get('property') or 'TMDbHelper.KodiSetting',
        set_property=u'{}'.format(response.get('result', {}).get('value', '')))


def user_list(user_list, user_slug=None, **kwargs):
    user_slug = user_slug or 'me'
    if user_slug and user_list:
        update.add_userlist(
            user_slug=user_slug, list_slug=user_list,
            confirm=False, allow_update=True, busy_dialog=True)


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

    def router(self):
        self.params = self.get_params()
        if not self.params:
            return
        if self.params.get('authenticate_trakt'):
            return TraktAPI(force=True)
        if self.params.get('revoke_trakt'):
            return TraktAPI().logout()
        if self.params.get('split_value'):
            return split_value(**self.params)
        if self.params.get('kodi_setting'):
            return kodi_setting(**self.params)
        if self.params.get('sync_item'):
            return sync_item(**self.params)
        if self.params.get('manage_artwork'):
            return manage_artwork(**self.params)
        if self.params.get('refresh_details'):
            return refresh_details(**self.params)
        if self.params.get('related_lists'):
            return related_lists(**self.params)
        if self.params.get('user_list'):
            return user_list(**self.params)
        if any(x in WM_PARAMS for x in self.params):
            return WindowManager(**self.params).router()
        if self.params.get('play'):
            return play_external(**self.params)
        if self.params.get('restart_service'):
            # Only do the import here because this function only for debugging purposes
            from resources.lib.monitor.service import restart_service_monitor
            return restart_service_monitor()
        # TODO: monitor/add trakt lists, library update, image utils, default players set/clear
        # NOTE: possibly put trakt list functions in listitem context menu instead
