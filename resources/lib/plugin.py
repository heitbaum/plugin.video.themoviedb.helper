#!/usr/bin/env python
# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import resources.lib.constants as constants


ADDON = xbmcaddon.Addon('plugin.video.themoviedb.helper')
ADDONPATH = ADDON.getAddonInfo('path')
PLUGINPATH = u'plugin://plugin.video.themoviedb.helper/'
ADDONDATA = 'special://profile/addon_data/plugin.video.themoviedb.helper/'

TYPE_PLURAL = 1
TYPE_CONTAINER = 2
TYPE_TRAKT = 3
TYPE_DB = 4
TYPE_LIBRARY = 5


def get_language():
    if ADDON.getSettingInt('language'):
        return constants.LANGUAGES[ADDON.getSettingInt('language')]
    return 'en-US'


def get_mpaa_prefix():
    if ADDON.getSettingString('mpaa_prefix'):
        return '{} '.format(ADDON.getSettingString('mpaa_prefix'))
    return ''


def convert_trakt_type(trakt_type):
    if trakt_type == 'movie':
        return 'movie'
    elif trakt_type == 'show':
        return 'tv'
    elif trakt_type == 'season':
        return 'season'
    elif trakt_type == 'episode':
        return 'episode'
    elif trakt_type == 'person':
        return 'person'


def convert_type(tmdb_type, output, season=None, episode=None):
    if tmdb_type == 'tv' and season is not None:
        tmdb_type == 'episode' if episode is not None else 'season'
    if output == TYPE_PLURAL:
        if tmdb_type == 'movie':
            return xbmc.getLocalizedString(342)
        elif tmdb_type == 'tv':
            return xbmc.getLocalizedString(20343)
        elif tmdb_type == 'person':
            return ADDON.getLocalizedString(32172)
        elif tmdb_type == 'collection':
            return ADDON.getLocalizedString(32187)
        elif tmdb_type == 'review':
            return ADDON.getLocalizedString(32188)
        elif tmdb_type == 'keyword':
            return xbmc.getLocalizedString(21861)
        elif tmdb_type == 'network':
            return ADDON.getLocalizedString(32189)
        elif tmdb_type == 'studio':
            return ADDON.getLocalizedString(32190)
        elif tmdb_type == 'image':
            return ADDON.getLocalizedString(32191)
        elif tmdb_type == 'genre':
            return xbmc.getLocalizedString(135)
        elif tmdb_type == 'season':
            return xbmc.getLocalizedString(33054)
        elif tmdb_type == 'episode':
            return xbmc.getLocalizedString(20360)
        elif tmdb_type == 'video':
            return xbmc.getLocalizedString(10025)
    elif output == TYPE_CONTAINER:
        if tmdb_type == 'movie':
            return 'movies'
        elif tmdb_type == 'tv':
            return 'tvshows'
        elif tmdb_type == 'person':
            return 'actors'
        elif tmdb_type == 'collection':
            return 'sets'
        elif tmdb_type == 'image':
            return 'images'
        elif tmdb_type == 'genre':
            return 'genres'
        elif tmdb_type == 'studio':
            return 'studios'
        elif tmdb_type == 'network':
            return 'studios'
        elif tmdb_type == 'season':
            return 'seasons'
        elif tmdb_type == 'episode':
            return 'episodes'
        elif tmdb_type == 'video':
            return 'videos'
    elif output == TYPE_TRAKT:
        if tmdb_type == 'movie':
            return 'movie'
        elif tmdb_type == 'tv':
            return 'show'
        elif tmdb_type == 'season':
            return 'season'
        elif tmdb_type == 'episode':
            return 'episode'
    elif output == TYPE_DB:
        if tmdb_type == 'movie':
            return 'movie'
        elif tmdb_type == 'tv':
            return 'tvshow'
        elif tmdb_type == 'person':
            return 'video'
        elif tmdb_type == 'collection':
            return 'set'
        elif tmdb_type == 'genre':
            return 'genre'
        elif tmdb_type == 'studio':
            return 'studio'
        elif tmdb_type == 'network':
            return 'studio'
        elif tmdb_type == 'season':
            return 'season'
        elif tmdb_type == 'episode':
            return 'episode'
        elif tmdb_type == 'video':
            return 'video'
    elif output == TYPE_LIBRARY:
        if tmdb_type == 'image':
            return 'pictures'
        else:
            return 'video'
    return ''
