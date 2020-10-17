import resources.lib.helpers.rpc as rpc
from resources.lib.trakt.api import TraktAPI
from resources.lib.tmdb.api import TMDb
from resources.lib.helpers.parser import try_int
from resources.lib.helpers.plugin import ADDON, viewitems
# from resources.lib.helpers.decorators import timer_report


class ItemUtils(object):
    def __init__(self, kodi_db=None, ftv_api=None, trakt_api=None, tmdb_api=None):
        self.trakt_watched_movies = {}
        self.trakt_watched_tvshows = {}
        self.ftv_api = ftv_api
        self.kodi_db = kodi_db
        self.kodi_db_tv = {}
        self.trakt_api = trakt_api or TraktAPI()
        self.tmdb_api = tmdb_api or TMDb()
        self.trakt_watchedindicators = ADDON.getSettingBool('trakt_watchedindicators')

    # @timer_report('get_ftv_details')
    def get_ftv_details(self, listitem):
        """ merges art with fanarttv art - must pass through fanarttv api object """
        if not self.ftv_api:
            return
        artwork = self.ftv_api.get_all_artwork(listitem.get_ftv_id(), listitem.get_ftv_type())
        if not artwork:
            return
        if listitem.infolabels.get('mediatype') in ['season', 'episode']:
            artwork = {u'tvshow.{}'.format(k): v for k, v in viewitems(artwork) if v}
        return {'art': artwork}

    def get_external_ids(self, listitem, season=None, episode=None):
        unique_id, trakt_type = None, None
        if listitem.infolabels.get('mediatype') == 'movie':
            unique_id = listitem.unique_ids.get('tmdb')
            trakt_type = 'movie'
        elif listitem.infolabels.get('mediatype') == 'tvshow':
            unique_id = listitem.unique_ids.get('tmdb')
            trakt_type = 'show'
        elif listitem.infolabels.get('mediatype') in ['season', 'episode']:
            unique_id = listitem.unique_ids.get('tvshow.tmdb')
            trakt_type = 'show'
        if not unique_id or not trakt_type:
            return
        trakt_slug = self.trakt_api.get_id(id_type='tmdb', unique_id=unique_id, trakt_type=trakt_type, output_type='slug')
        if not trakt_slug:
            return
        details = self.trakt_api.get_details(trakt_type, trakt_slug, extended=None)
        if not details:
            return
        if listitem.infolabels.get('mediatype') in ['movie', 'tvshow', 'season']:
            return {
                'unique_ids': {
                    'tmdb': unique_id,
                    'tvdb': details.get('ids', {}).get('tvdb'),
                    'imdb': details.get('ids', {}).get('imdb'),
                    'slug': details.get('ids', {}).get('slug'),
                    'trakt': details.get('ids', {}).get('trakt')}}
        episode_details = self.trakt_api.get_details(
            trakt_type, trakt_slug,
            season=season or listitem.infolabels.get('season'),
            episode=episode or listitem.infolabels.get('episode'),
            extended=None)
        if episode_details:
            return {
                'unique_ids': {
                    'tvshow.tmdb': unique_id,
                    'tvshow.tvdb': details.get('ids', {}).get('tvdb'),
                    'tvshow.imdb': details.get('ids', {}).get('imdb'),
                    'tvshow.slug': details.get('ids', {}).get('slug'),
                    'tvshow.trakt': details.get('ids', {}).get('trakt'),
                    'tvdb': episode_details.get('ids', {}).get('tvdb'),
                    'tmdb': episode_details.get('ids', {}).get('tmdb'),
                    'imdb': episode_details.get('ids', {}).get('imdb'),
                    'slug': episode_details.get('ids', {}).get('slug'),
                    'trakt': episode_details.get('ids', {}).get('trakt')}}

    def get_tmdb_details(self, listitem, cache_only=True):
        return TMDb().get_details(
            listitem.get_tmdb_type(),
            listitem.unique_ids.get('tvshow.tmdb') if listitem.infolabels.get('mediatype') == 'episode' else listitem.unique_ids.get('tmdb'),
            listitem.infolabels.get('season') if listitem.infolabels.get('mediatype') in ['season', 'episode'] else None,
            listitem.infolabels.get('episode') if listitem.infolabels.get('mediatype') == 'episode' else None,
            cache_only=cache_only)

    def get_kodi_parent_dbid(self, listitem):
        if not self.kodi_db:
            return
        if listitem.infolabels.get('mediatype') in ['movie', 'tvshow']:
            return self.kodi_db.get_info(
                info='dbid',
                imdb_id=listitem.unique_ids.get('imdb'),
                tmdb_id=listitem.unique_ids.get('tmdb'),
                tvdb_id=listitem.unique_ids.get('tvdb'),
                originaltitle=listitem.infolabels.get('originaltitle'),
                title=listitem.infolabels.get('title'),
                year=listitem.infolabels.get('year'))
        if listitem.infolabels.get('mediatype') in ['season', 'episode']:
            return self.kodi_db.get_info(
                info='dbid',
                imdb_id=listitem.unique_ids.get('tvshow.imdb'),
                tmdb_id=listitem.unique_ids.get('tvshow.tmdb'),
                tvdb_id=listitem.unique_ids.get('tvshow.tvdb'),
                title=listitem.infolabels.get('tvshowtitle'))

    def get_kodi_details(self, listitem):
        if not self.kodi_db:
            return
        dbid = self.get_kodi_parent_dbid(listitem)
        if not dbid:
            return
        if listitem.infolabels.get('mediatype') == 'movie':
            return rpc.get_movie_details(dbid)
        if listitem.infolabels.get('mediatype') == 'tvshow':
            return rpc.get_tvshow_details(dbid)
        if listitem.infolabels.get('mediatype') == 'season':
            return self.get_kodi_tvchild_details(
                tv_dbid=dbid,
                season=listitem.infolabels.get('season'),
                is_season=True)
        if listitem.infolabels.get('mediatype') == 'episode':
            return self.get_kodi_tvchild_details(
                tv_dbid=dbid,
                season=listitem.infolabels.get('season'),
                episode=listitem.infolabels.get('episode'))

    def get_kodi_tvchild_details(self, tv_dbid, season=None, episode=None, is_season=False):
        if not tv_dbid or not season or (not episode and not is_season):
            return
        library = 'season' if is_season else 'episode'
        self.kodi_db_tv[tv_dbid] = self.kodi_db_tv.get(tv_dbid) or rpc.KodiLibrary(library, tv_dbid)
        if not self.kodi_db_tv[tv_dbid].database:
            return
        dbid = self.kodi_db_tv[tv_dbid].get_info('dbid', season=season, episode=episode)
        if not dbid:
            return
        details = rpc.get_season_details(dbid) if is_season else rpc.get_episode_details(dbid)
        details['infoproperties']['tvshow.dbid'] = tv_dbid
        return details

    def get_playcount_from_trakt(self, listitem):
        if not self.trakt_watchedindicators:
            return
        if listitem.infolabels.get('mediatype') == 'movie':
            return self.trakt_api.get_movie_playcount(
                id_type='tmdb',
                unique_id=try_int(listitem.unique_ids.get('tmdb')))
        if listitem.infolabels.get('mediatype') == 'episode':
            return self.trakt_api.get_episode_playcount(
                id_type='tmdb',
                unique_id=try_int(listitem.unique_ids.get('tvshow.tmdb')),
                season=listitem.infolabels.get('season'),
                episode=listitem.infolabels.get('episode'))
        if listitem.infolabels.get('mediatype') == 'tvshow':
            listitem.infolabels['episode'] = self.trakt_api.get_episodes_airedcount(
                id_type='tmdb',
                unique_id=try_int(listitem.unique_ids.get('tmdb')))
            return self.trakt_api.get_episodes_watchcount(
                id_type='tmdb',
                unique_id=try_int(listitem.unique_ids.get('tmdb')))
        if listitem.infolabels.get('mediatype') == 'season':
            listitem.infolabels['episode'] = self.trakt_api.get_episodes_airedcount(
                id_type='tmdb',
                unique_id=try_int(listitem.unique_ids.get('tmdb')),
                season=listitem.infolabels.get('season'))
            return self.trakt_api.get_episodes_watchcount(
                id_type='tmdb',
                unique_id=try_int(listitem.unique_ids.get('tmdb')),
                season=listitem.infolabels.get('season'))
