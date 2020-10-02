import resources.lib.utils as utils
import resources.lib.cache as cache
import resources.lib.plugin as plugin
from resources.lib.plugin import PLUGINPATH


class _TraktMethodsMixin():
    def _get_id(self, id_type, unique_id, trakt_type=None, output_type=None):
        response = self.get_request_lc('search', id_type, unique_id, type=trakt_type)
        for i in response:
            if i.get('type') != trakt_type:
                continue
            if '{}'.format(i.get(trakt_type, {}).get('ids', {}).get(id_type)) != '{}'.format(unique_id):
                continue
            if not output_type:
                return i.get(trakt_type, {}).get('ids', {})
            return i.get(trakt_type, {}).get('ids', {}).get(output_type)

    def get_id(self, id_type, unique_id, trakt_type=None, output_type=None):
        """
        trakt_type: movie, show, episode, person, list
        output_type: trakt, slug, imdb, tmdb, tvdb
        """
        return cache.use_cache(
            self._get_id, id_type, unique_id, trakt_type=trakt_type, output_type=output_type,
            cache_name='trakt_get_id.{}.{}.{}.{}'.format(id_type, unique_id, trakt_type, output_type),
            cache_days=self.cache_long)

    def get_details(self, trakt_type, id_num, season=None, episode=None, extended='full'):
        if not season or not episode:
            return self.get_response_json(trakt_type + 's', id_num, extended=extended)
        return self.get_response_json(trakt_type + 's', id_num, 'seasons', season, 'episodes', episode, extended=extended)

    def get_title(self, item):
        return item.get('title', '')

    def get_infolabels(self, item, trakt_type, infolabels=None, detailed=True):
        infolabels = infolabels or {}
        infolabels['title'] = self.get_title(item)
        infolabels['year'] = item.get('year')
        infolabels['mediatype'] = plugin.convert_type(plugin.convert_trakt_type(trakt_type), plugin.TYPE_DB)
        return utils.del_empty_keys(infolabels)

    def get_unique_ids(self, item, unique_ids=None):
        unique_ids = unique_ids or {}
        unique_ids['tmdb'] = item.get('ids', {}).get('tmdb')
        unique_ids['imdb'] = item.get('ids', {}).get('imdb')
        unique_ids['tvdb'] = item.get('ids', {}).get('tvdb')
        unique_ids['slug'] = item.get('ids', {}).get('slug')
        unique_ids['trakt'] = item.get('ids', {}).get('trakt')
        return utils.del_empty_keys(unique_ids)

    def get_info(self, item, trakt_type, base_item=None, detailed=True, params_definition=None, item_key=None):
        base_item = base_item or {}
        item_info = item.get(item_key) or {} if item_key else item
        if item and trakt_type:
            base_item['label'] = self.get_title(item_info)
            base_item['infolabels'] = self.get_infolabels(item_info, trakt_type, base_item.get('infolabels', {}), detailed=detailed)
            base_item['unique_ids'] = self.get_unique_ids(item_info, base_item.get('unique_ids', {}))
            base_item['params'] = utils.get_params(
                item_info, plugin.convert_trakt_type(trakt_type),
                tmdb_id=base_item.get('unique_ids', {}).get('tmdb'),
                params=base_item.get('params', {}),
                definition=params_definition)
            base_item['path'] = PLUGINPATH
        return base_item

    def get_list_info(self, response_json, trakt_type, item_key=None, params=None):
        if not item_key:
            return [self.get_info(i, trakt_type, params_definition=params)
                    for i in response_json if i.get('ids', {}).get('tmdb')]
        return [self.get_info(i, trakt_type, params_definition=params, item_key=item_key)
                for i in response_json if i.get(item_key, {}).get('ids', {}).get('tmdb')]

    def get_hiddenitems(self, trakt_type, progress_watched=True, progress_collected=True, calendar=True, id_type='slug'):
        hidden_items = set()
        if not self.authorize() or not trakt_type or not id_type:
            return hidden_items
        if progress_watched:
            response = self.get_response_json('users', 'hidden', 'progress_watched', type=trakt_type)
            hidden_items |= {i.get(trakt_type, {}).get('ids', {}).get(id_type) for i in response}
        if progress_collected:
            response = self.get_response_json('users', 'hidden', 'progress_collected', type=trakt_type)
            hidden_items |= {i.get(trakt_type, {}).get('ids', {}).get(id_type) for i in response}
        if calendar:
            response = self.get_response_json('users', 'hidden', 'calendar', type=trakt_type)
            hidden_items |= {i.get(trakt_type, {}).get('ids', {}).get(id_type) for i in response}
        return hidden_items
