# -*- coding: utf-8 -*-
# Module: default
# Author: jurialmunkey
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html
import xbmc
import xbmcgui
import resources.lib.utils as utils
from resources.lib.traktapi import TraktAPI
from resources.lib.plugin import ADDON


def _sync_item_methods():
    return [
        {
            'method': 'history',
            'sync_type': 'watched',
            'allow_episodes': True,
            'name_add': xbmc.getLocalizedString(16103),
            'name_remove': xbmc.getLocalizedString(16104)},
        {
            'method': 'collection',
            'sync_type': 'collection',
            'allow_episodes': True,
            'name_add': ADDON.getLocalizedString(32289),
            'name_remove': ADDON.getLocalizedString(32290)},
        {
            'method': 'watchlist',
            'sync_type': 'watchlist',
            'name_add': ADDON.getLocalizedString(32291),
            'name_remove': ADDON.getLocalizedString(32292)},
        {
            'method': 'recommendations',
            'sync_type': 'recommendations',
            'name_add': ADDON.getLocalizedString(32293),
            'name_remove': ADDON.getLocalizedString(32294)}]


class SyncItem():
    def __init__(self, trakt_type, unique_id, season=None, episode=None, id_type=None):
        self.trakt_type = trakt_type
        self.unique_id = unique_id
        self.season = utils.try_parse_int(season) if season is not None else None
        self.episode = utils.try_parse_int(episode) if episode is not None else None
        self.id_type = id_type

    def _build_choices(self):
        choices = [{'name': ADDON.getLocalizedString(32298), 'method': 'userlist'}]
        choices += [j for j in (self._sync_item_check(**i) for i in _sync_item_methods()) if j]
        return choices

    def _sync_item_check(self, sync_type=None, method=None, name_add=None, name_remove=None, allow_episodes=False):
        if self.season is not None and (not allow_episodes or not self.episode):
            return
        if TraktAPI().is_sync(self.trakt_type, self.unique_id, self.season, self.episode, self.id_type, sync_type):
            return {'name': name_remove, 'method': '{}/remove'.format(method)}
        return {'name': name_add, 'method': method}

    def _sync_userlist(self):
        with utils.busy_dialog():
            list_sync = TraktAPI().get_list_of_lists('users/me/lists') or []
            list_sync.append({'label': ADDON.getLocalizedString(32299)})
        x = xbmcgui.Dialog().contextmenu([i.get('label') for i in list_sync])
        if x == -1:
            return
        if list_sync[x].get('label') == ADDON.getLocalizedString(32299):
            return  # TODO: CREATE NEW LIST
        list_slug = list_sync[x].get('params', {}).get('list_slug')
        if not list_slug:
            return
        with utils.busy_dialog():
            return TraktAPI().add_list_item(
                list_slug, self.trakt_type, self.unique_id, self.id_type,
                season=self.season, episode=self.episode)

    def _sync_item(self, method):
        if method == 'userlist':
            return self._sync_userlist()
        with utils.busy_dialog():
            return TraktAPI().sync_item(
                method, self.trakt_type, self.unique_id, self.id_type,
                season=self.season, episode=self.episode)

    def sync(self):
        with utils.busy_dialog():
            choices = self._build_choices()
        x = xbmcgui.Dialog().contextmenu([i.get('name') for i in choices])
        if x == -1:
            return
        name = choices[x].get('name')
        method = choices[x].get('method')
        item_sync = self._sync_item(method)
        if item_sync and item_sync.status_code in [200, 201, 204]:
            xbmcgui.Dialog().ok(
                ADDON.getLocalizedString(32295),
                ADDON.getLocalizedString(32297).format(
                    name, self.trakt_type, self.id_type.upper(), self.unique_id))
            xbmc.executebuiltin('Container.Refresh')
            return
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(32295),
            ADDON.getLocalizedString(32296).format(
                name, self.trakt_type, self.id_type.upper(), self.unique_id))
