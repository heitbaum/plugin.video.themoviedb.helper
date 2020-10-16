# -*- coding: utf-8 -*-
# Module: default
# Author: jurialmunkey
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html
import sys
import xbmc
import xbmcgui
from resources.lib.helpers.update import add_userlist
from resources.lib.helpers.window import get_property
from resources.lib.items.basedir import get_basedir_details
from resources.lib.fanarttv.api import FanartTV
from resources.lib.tmdb.api import TMDb
from resources.lib.trakt.api import TraktAPI
from resources.lib.helpers.plugin import ADDON, reconfigure_legacy_params
from resources.lib.helpers.rpc import get_jsonrpc
from resources.lib.script.sync import SyncItem
from resources.lib.helpers.decorators import busy_dialog
from resources.lib.helpers.parser import encode_url
from resources.lib.window.manager import WindowManager
from resources.lib.player.players import Players
from resources.lib.monitor.images import ImageFunctions


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
        get_property(name, set_property=i, prefix=-1)


def sync_item(trakt_type, unique_id, season=None, episode=None, id_type=None, **kwargs):
    SyncItem(trakt_type, unique_id, season, episode, id_type).sync()


def sync_trakt(tmdb_id, **kwargs):
    if kwargs.get('tmdb_type') not in ['movie', 'tv'] or not tmdb_id:
        return
    trakt_type = 'show' if kwargs.get('tmdb_type') == 'tv' else 'movie'
    sync_item(trakt_type, tmdb_id, id_type='tmdb')


def manage_artwork(ftv_id=None, ftv_type=None, **kwargs):
    FanartTV().manage_artwork(ftv_id, ftv_type)


def related_lists(tmdb_id=None, tmdb_type=None, season=None, episode=None, container_update=True, **kwargs):
    if not tmdb_id or not tmdb_type:
        return
    # items = get_basedir_details(tmdb_type=tmdb_type, tmdb_id=tmdb_id, season=season, episode=episode)
    items = get_basedir_details(tmdb_type=tmdb_type, tmdb_id=tmdb_id)
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
    # if season is not None:
    #     item['params']['season'] = season
    #     if episode is not None:
    #         item['params']['episode'] = episode
    if not container_update:
        return item
    path = 'Container.Update({})' if xbmc.getCondVisibility("Window.IsMedia") else 'ActivateWindow(videos,{},return)'
    path = path.format(encode_url(path=item.get('path'), **item.get('params')))
    xbmc.executebuiltin(path)


def refresh_details(tmdb_id=None, tmdb_type=None, season=None, episode=None, **kwargs):
    if not tmdb_id or not tmdb_type:
        return
    with busy_dialog():
        details = TMDb().get_details(tmdb_type, tmdb_id, season, episode, cache_refresh=True)
    if details:
        xbmcgui.Dialog().ok('TMDbHelper', ADDON.getLocalizedString(32234).format(tmdb_type, tmdb_id))
        xbmc.executebuiltin('Container.Refresh')
        xbmc.executebuiltin('UpdateLibrary(video,/fake/path/to/force/refresh/on/home)')


def kodi_setting(kodi_setting, **kwargs):
    method = "Settings.GetSettingValue"
    params = {"setting": kodi_setting}
    response = get_jsonrpc(method, params)
    get_property(
        name=kwargs.get('property') or 'TMDbHelper.KodiSetting',
        set_property=u'{}'.format(response.get('result', {}).get('value', '')))


def user_list(user_list, user_slug=None, **kwargs):
    user_slug = user_slug or 'me'
    if user_slug and user_list:
        add_userlist(
            user_slug=user_slug, list_slug=user_list,
            confirm=False, allow_update=True, busy_dialog=True)


def set_defaultplayer(**kwargs):
    tmdb_type = kwargs.get('set_defaultplayer')
    setting_name = 'default_player_movies' if tmdb_type == 'movie' else 'default_player_episodes'
    default_player = Players(tmdb_type).select_player(detailed=True, clear_player=True)
    if not default_player:
        return
    if not default_player.get('file') or not default_player.get('mode'):
        return ADDON.setSettingString(setting_name, '')
    ADDON.setSettingString(setting_name, u'{} {}'.format(default_player['file'], default_player['mode']))


def blur_image(blur_image=None, **kwargs):
    blur_img = ImageFunctions(method='blur', artwork=blur_image)
    blur_img.setName('blur_img')
    blur_img.start()


def image_colors(image_colors=None, **kwargs):
    image_colors = ImageFunctions(method='colors', artwork=image_colors)
    image_colors.setName('image_colors')
    image_colors.start()


def sort_list(**kwargs):
    choice = xbmcgui.Dialog().contextmenu([
        '{}: {}'.format(ADDON.getLocalizedString(32287), ADDON.getLocalizedString(32286)),
        '{}: {}'.format(ADDON.getLocalizedString(32287), ADDON.getLocalizedString(32106)),
        '{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(369)),
        '{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(345)),
        '{}: {}'.format(ADDON.getLocalizedString(32287), xbmc.getLocalizedString(590))])
    if choice == 0:
        kwargs['sort_by'] = 'rank'
        kwargs['sort_how'] = 'asc'
    elif choice == 1:
        kwargs['sort_by'] = 'added'
        kwargs['sort_how'] = 'desc'
    elif choice == 2:
        kwargs['sort_by'] = 'title'
        kwargs['sort_how'] = 'asc'
    elif choice == 3:
        kwargs['sort_by'] = 'year'
        kwargs['sort_how'] = 'desc'
    elif choice == 4:
        kwargs['sort_by'] = 'random'
    else:
        return
    command = 'Container.Update({})' if xbmc.getCondVisibility("Window.IsMedia") else 'ActivateWindow(videos,{},return)'
    xbmc.executebuiltin(command.format(encode_url(**kwargs)))


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
        self.params = reconfigure_legacy_params(**self.params)
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
        if self.params.get('sync_trakt'):
            return sync_trakt(**self.params)
        if self.params.get('manage_artwork'):
            return manage_artwork(**self.params)
        if self.params.get('refresh_details'):
            return refresh_details(**self.params)
        if self.params.get('related_lists'):
            return related_lists(**self.params)
        if self.params.get('user_list'):
            return user_list(**self.params)
        if self.params.get('blur_image'):
            return blur_image(**self.params)
        if self.params.get('image_colors'):
            return image_colors(**self.params)
        if self.params.get('set_defaultplayer'):
            return set_defaultplayer(**self.params)
        if any(x in WM_PARAMS for x in self.params):
            return WindowManager(**self.params).router()
        if self.params.get('play'):
            return play_external(**self.params)
        if self.params.get('restart_service'):
            # Only do the import here because this function only for debugging purposes
            from resources.lib.monitor.service import restart_service_monitor
            return restart_service_monitor()
        # TODO: monitor/add trakt lists, library update, default players set/clear
        # NOTE: possibly put trakt list functions in listitem context menu instead
