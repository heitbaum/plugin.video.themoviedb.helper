import resources.lib.plugin as plugin
import resources.lib.constants as constants
from resources.lib.tmdb.api import TMDb


class TMDbLists():
    def list_tmdb(self, info, tmdb_type, tmdb_id=None, page=None, **kwargs):
        info_model = constants.TMDB_BASIC_LISTS.get(info)
        info_tmdb_type = info_model.get('tmdb_type') or tmdb_type
        items = TMDb().get_basic_list(
            path=info_model.get('path', '').format(tmdb_type=tmdb_type, tmdb_id=tmdb_id, **kwargs),
            tmdb_type=info_tmdb_type,
            base_tmdb_type=tmdb_type,
            key=info_model.get('key', 'results'),
            params=info_model.get('params'),
            page=page)
        self.kodi_db = self.get_kodi_database(info_tmdb_type)
        self.library = plugin.convert_type(info_tmdb_type, plugin.TYPE_LIBRARY)
        self.container_content = plugin.convert_type(info_tmdb_type, plugin.TYPE_CONTAINER)
        return items

    def list_seasons(self, tmdb_id, **kwargs):
        items = TMDb().get_season_list(tmdb_id)
        self.kodi_db = self.get_kodi_database('tv')
        self.container_content = plugin.convert_type('season', plugin.TYPE_CONTAINER)
        return items

    def list_episodes(self, tmdb_id, season, **kwargs):
        items = TMDb().get_episode_list(tmdb_id, season)
        self.kodi_db = self.get_kodi_database('tv')
        self.container_content = plugin.convert_type('episode', plugin.TYPE_CONTAINER)
        return items

    def list_cast(self, tmdb_id, tmdb_type, season=None, episode=None, **kwargs):
        items = TMDb().get_cast_list(tmdb_id, tmdb_type, season=season, episode=episode)
        self.container_content = plugin.convert_type('person', plugin.TYPE_CONTAINER)
        return items

    def list_crew(self, tmdb_id, tmdb_type, season=None, episode=None, **kwargs):
        items = TMDb().get_cast_list(tmdb_id, tmdb_type, season=season, episode=episode, keys=['crew'])
        self.container_content = plugin.convert_type('person', plugin.TYPE_CONTAINER)
        return items

    def list_all_items(self, tmdb_type, page=None, **kwargs):
        items = TMDb().get_all_items_list(tmdb_type, page=page)
        self.kodi_db = self.get_kodi_database(tmdb_type)
        self.library = plugin.convert_type(tmdb_type, plugin.TYPE_LIBRARY)
        self.container_content = plugin.convert_type(tmdb_type, plugin.TYPE_CONTAINER)
        return items
