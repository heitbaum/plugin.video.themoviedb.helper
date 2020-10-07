import xbmc
import resources.lib.utils as utils
from resources.lib.tmdb import TMDb
from resources.lib.omdb import OMDb
from resources.lib.plugin import ADDON

SETMAIN = {
    'label', 'tmdb_id', 'imdb_id'}
SETMAIN_ARTWORK = {
    'icon', 'poster', 'thumb', 'fanart', 'discart', 'clearart', 'clearlogo', 'landscape', 'banner'}
SETINFO = {
    'title', 'originaltitle', 'tvshowtitle', 'plot', 'rating', 'votes', 'premiered', 'year',
    'imdbnumber', 'tagline', 'status', 'episode', 'season', 'genre', 'set', 'studio', 'country',
    'MPAA', 'director', 'writer', 'trailer', 'top250'}
SETPROP = {
    'tvdb_id', 'tvshow.tvdb_id', 'tvshow.tmdb_id', 'tvshow.imdb_id', 'biography', 'birthday', 'age',
    'deathday', 'character', 'department', 'job', 'known_for', 'role', 'born', 'creator', 'aliases',
    'budget', 'revenue', 'set.tmdb_id', 'set.name', 'set.poster', 'set.fanart'}
SETPROP_RATINGS = {
    'awards', 'metacritic_rating', 'imdb_rating', 'imdb_votes', 'rottentomatoes_rating',
    'rottentomatoes_image', 'rottentomatoes_reviewtotal', 'rottentomatoes_reviewsfresh',
    'rottentomatoes_reviewsrotten', 'rottentomatoes_consensus', 'rottentomatoes_usermeter',
    'rottentomatoes_userreviews', 'trakt_rating', 'trakt_votes', 'goldenglobe_wins',
    'goldenglobe_nominations', 'oscar_wins', 'oscar_nominations', 'award_wins', 'award_nominations',
    'tmdb_rating', 'tmdb_votes'}


class CommonMonitorFunctions(object):
    def __init__(self):
        self.properties = set()
        self.index_properties = set()
        self.tmdb_api = TMDb()
        self.omdb_api = OMDb() if ADDON.getSettingString('omdb_apikey') else None

    def clear_property(self, key):
        key = 'ListItem.{}'.format(key)
        try:
            utils.get_property(key, clear_property=True)
        except Exception as exc:
            utils.kodi_log(u'Func: clear_property\n{0}{1}'.format(key, exc), 1)

    def set_property(self, key, value):
        key = 'ListItem.{}'.format(key)
        try:
            if value is None:
                utils.get_property(key, clear_property=True)
            else:
                utils.get_property(key, set_property=u'{0}'.format(value))
        except Exception as exc:
            utils.kodi_log(u'{}{}'.format(key, exc), 1)

    def set_iter_properties(self, dictionary, keys):
        if not isinstance(dictionary, dict):
            return
        for k in keys:
            try:
                v = dictionary.get(k, '')
                if isinstance(v, list):
                    try:
                        v = ' / '.join(v)
                    except Exception as exc:
                        utils.kodi_log(u'Func: set_iter_properties - list\n{0}'.format(exc), 1)
                self.properties.add(k)
                self.set_property(k, v)
            except Exception as exc:
                'k: {} e: {}'.format(k, exc)

    def set_indexed_properties(self, dictionary):
        if not isinstance(dictionary, dict):
            return

        index_properties = set()
        for k, v in dictionary.items():
            if k in self.properties or k in SETPROP_RATINGS or k in SETMAIN_ARTWORK:
                continue
            try:
                v = v or ''
                self.set_property(k, v)
                index_properties.add(k)
            except Exception as exc:
                utils.kodi_log(u'k: {0} v: {1} e: {2}'.format(k, v, exc), 1)

        for k in (self.index_properties - index_properties):
            self.clear_property(k)
        self.index_properties = index_properties.copy()

    def set_list_properties(self, items, key, prop):
        if not isinstance(items, list):
            return
        try:
            joinlist = [i[key] for i in items[:10] if i.get(key)]
            joinlist = ' / '.join(joinlist)
            self.properties.add(prop)
            self.set_property(prop, joinlist)
        except Exception as exc:
            utils.kodi_log(u'Func: set_list_properties\n{0}'.format(exc), 1)

    def set_time_properties(self, duration):
        try:
            minutes = duration // 60 % 60
            hours = duration // 60 // 60
            totalmin = duration // 60
            self.set_property('Duration', totalmin)
            self.set_property('Duration_H', hours)
            self.set_property('Duration_M', minutes)
            self.set_property('Duration_HHMM', '{0:02d}:{1:02d}'.format(hours, minutes))
            self.properties.update(['Duration', 'Duration_H', 'Duration_M', 'Duration_HHMM'])
        except Exception as exc:
            'Func: set_time_properties\n{0}'.format(exc)

    def set_properties(self, item):
        self.set_iter_properties(item, SETMAIN)
        self.set_iter_properties(item.get('infolabels', {}), SETINFO)
        self.set_iter_properties(item.get('infoproperties', {}), SETPROP)
        self.set_time_properties(item.get('infolabels', {}).get('duration', 0))
        self.set_list_properties(item.get('cast', []), 'name', 'cast')
        if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisableExtendedProperties)"):
            self.set_indexed_properties(item.get('infoproperties', {}))

    def get_tmdb_id(self, tmdb_type, imdb_id=None, query=None, year=None, episode_year=None):
        try:
            if imdb_id and imdb_id.startswith('tt'):
                return self.tmdb_api.get_tmdb_id(tmdb_type=tmdb_type, imdb_id=imdb_id)
            return self.tmdb_api.get_tmdb_id(tmdb_type=tmdb_type, query=query, year=year, episode_year=episode_year)
        except Exception as exc:
            utils.kodi_log(u'Func: get_tmdb_id\n{0}'.format(exc), 1)
            return

    def get_omdb_ratings(self, item, cache_only=False):
        if not self.omdb_api:
            return item
        imdb_id = item.get('infolabels', {}).get('imdbnumber')
        if not imdb_id or not imdb_id.startswith('tt'):
            imdb_id = item.get('unique_ids', {}).get('imdb')
        if not imdb_id or not imdb_id.startswith('tt'):
            imdb_id = item.get('unique_ids', {}).get('tvshow.imdb')
        if not imdb_id:
            return item
        ratings_awards = self.omdb_api.get_ratings_awards(imdb_id=imdb_id, cache_only=cache_only)
        if ratings_awards:
            item['infoproperties'] = utils.merge_two_dicts(
                item.get('infoproperties', {}), ratings_awards)
        return item

    def clear_properties(self, ignore_keys=None):
        ignore_keys = ignore_keys or set()
        for k in self.properties - ignore_keys:
            self.clear_property(k)
        self.properties = set()
        for k in self.index_properties:
            self.clear_property(k)
        self.index_properties = set()
        self.pre_item = None

    def clear_property_list(self, properties):
        for k in properties:
            self.clear_property(k)
