import random
import resources.lib.utils as utils
import resources.lib.cache as cache
import resources.lib.paginated as paginated
from resources.lib.paginated import PaginatedItems


class _TraktItemLists():
    def _sort_itemlist(self, items, sort_by=None, sort_how=None, trakt_type=None):
        reverse = True if sort_how == 'desc' else False
        if sort_by == 'unsorted':
            return items
        elif sort_by == 'rank':
            return sorted(items, key=lambda i: i.get('rank'), reverse=reverse)
        elif sort_by == 'plays':
            return sorted(items, key=lambda i: i.get('plays'), reverse=reverse)
        elif sort_by == 'watched':
            return sorted(items, key=lambda i: i.get('last_watched_at'), reverse=reverse)
        elif sort_by == 'paused':
            return sorted(items, key=lambda i: i.get('paused_at'), reverse=reverse)
        elif sort_by == 'added':
            return sorted(items, key=lambda i: i.get('listed_at'), reverse=reverse)
        elif sort_by == 'title':
            return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('title'), reverse=reverse)
        elif sort_by == 'released':
            return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('first_aired')
                          if (trakt_type or i.get('type')) == 'show'
                          else i.get(trakt_type or i.get('type'), {}).get('released'), reverse=reverse)
        elif sort_by == 'runtime':
            return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('runtime'), reverse=reverse)
        elif sort_by == 'popularity':
            return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('comment_count'), reverse=reverse)
        elif sort_by == 'percentage':
            return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('rating'), reverse=reverse)
        elif sort_by == 'votes':
            return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('votes'), reverse=reverse)
        elif sort_by == 'random':
            random.shuffle(items)
            return items
        return sorted(items, key=lambda i: i.get('listed_at'), reverse=True)

    def get_itemlist_sorted(self, *args, **kwargs):
        response = self.get_response(*args, extended=kwargs.get('extended'))
        if not response:
            return
        return self._sort_itemlist(
            items=response.json(),
            sort_by=kwargs.get('sort_by') or response.headers.get('X-Sort-By'),
            sort_how=kwargs.get('sort_how') or response.headers.get('X-Sort-How'),
            trakt_type=kwargs.get('trakt_type'))

    def get_itemlist_cached(self, *args, **kwargs):
        params = {
            'cache_name': 'trakt.sortedlist',
            'cache_combine_name': True,
            'cache_days': 0.125,
            'cache_refresh': kwargs.get('cache_refresh', False),
            'sort_by': kwargs.get('sort_by', None),
            'sort_how': kwargs.get('sort_how', None),
            'trakt_type': kwargs.get('trakt_type', None),
            'extended': kwargs.get('extended', None)}
        items = cache.use_cache(self.get_itemlist_sorted, *args, **params)
        return PaginatedItems(items, page=kwargs.get('page'), limit=kwargs.get('limit'))

    def get_synclist_cached(self, sync_type, trakt_type, activity_type, activity_key, item_key=None, page=1, limit=20, params=None, sort_by=None, sort_how=None, next_page=True):
        cache_name = 'trakt.synclist.{}.{}.{}.{}'.format(sync_type, trakt_type, sort_by, sort_how)
        response_items = self.use_activity_cache(
            activity_type, activity_key, cache_name, self.cache_long,
            func=self._sort_itemlist,
            items=self.get_sync(sync_type, trakt_type),
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_type=trakt_type)
        response = PaginatedItems(response_items, page=page, limit=limit)
        if not response:
            return
        items = self.get_list_info(response.json(), trakt_type, item_key=item_key, params=params)
        if not items:
            return
        if next_page:
            items += paginated.get_next_page(response.headers)
        return items

    def get_basic_list(self, path, trakt_type, item_key=None, page=1, limit=20, params=None, authorize=False, sort_by=None, sort_how=None, extended=None):
        if authorize and not self.authorize():
            return
        func = self.get_itemlist_cached if sort_by is not None else self.get_response
        response = func(
            path, page=page, limit=limit, sort_by=sort_by, sort_how=sort_how, extended=extended,
            trakt_type=trakt_type if sort_by is not None else None)
        if not response:
            return
        items = self.get_list_info(response.json(), trakt_type, item_key=item_key, params=params)
        if not items:
            return
        return items + paginated.get_next_page(response.headers)

    def get_userlist(self, list_slug, user_slug=None, page=1, limit=20, params=None, authorize=False, sort_by=None, sort_how=None, extended=None):
        if authorize and not self.authorize():
            return
        user_slug = user_slug or 'me'
        path = 'users/{}/lists/{}/items'.format(user_slug, list_slug)
        response = self.get_itemlist_cached(
            path, page=page, limit=limit, sort_by=sort_by, sort_how=sort_how, extended=extended)
        if not response:
            return
        items = []
        movies = []
        shows = []
        for i in response.json():
            trakt_type = i.get('type')
            if trakt_type not in ['movie', 'show']:
                continue
            item = self.get_info(i, trakt_type, item_key=trakt_type, params_definition=params)
            if not item:
                continue
            items.append(item)
            if trakt_type == 'movie':
                movies.append(item)
            elif trakt_type == 'show':
                shows.append(item)
        if not items:
            return
        return {
            'items': items,
            'movies': movies,
            'tvshows': shows,
            'next_page': paginated.get_next_page(response.headers)}

    def get_imdb_top250(self):
        return self.get_itemlist_cached(
            'users', 'nielsz', 'lists', 'active-imdb-top-250', 'items',
            sort_by='rank', sort_how='asc', limit=250)

    def get_inprogress_shows_list(self, page=1, limit=20, params=None):
        page = utils.try_parse_int(page) or 1
        response = PaginatedItems(
            self._get_inprogress_shows(),
            page=page, limit=utils.try_parse_int(limit) or 20)
        items = self.get_list_info(response.items, 'show', item_key='show', params=params)
        if not items:
            return
        return items + response.next_page

    def get_upnext_episodes_list(self, page=1, limit=20):
        page = utils.try_parse_int(page) or 1
        response = PaginatedItems(
            self._get_inprogress_shows(), page=page, limit=utils.try_parse_int(limit) or 20)
        if not response or not response.items:
            return
        items = []
        for i in response.items:
            next_episode = self.get_upnext_episodes(i.get('show', {}), get_single_episode=True)
            if not next_episode:
                continue
            items.append(next_episode)
        return items

    def get_upnext_list(self, unique_id, id_type='slug', page=1, limit=20):
        page = utils.try_parse_int(page) or 1
        slug = unique_id if id_type == 'slug' else self.get_id(
            id_type=id_type, unique_id=unique_id, trakt_type='show', output_type='slug')
        if not slug:
            return
        tvshow_details = self.get_details('show', slug)
        if not tvshow_details:
            return
        response = PaginatedItems(
            self.get_upnext_episodes(tvshow_details),
            page=page,
            limit=utils.try_parse_int(limit) or 20)
        if not response or not response.items:
            return
        return response.items + response.next_page

    def get_list_of_lists(self, path, page=1, limit=250, authorize=False):
        if authorize and not self.authorize():
            return
        page = utils.try_parse_int(page) or 1
        response = self.get_response(path, page=page, limit=limit)
        if not response:
            return
        items = []
        for i in response.json():
            if i.get('list', {}).get('name'):
                i = i.get('list', {})
            elif not i.get('name'):
                continue
            item = {}
            item['label'] = i.get('name')
            item['infolabels'] = {'plot': i.get('description')}
            item['infoproperties'] = {k: v for k, v in i.items() if v and type(v) not in [list, dict]}
            item['art'] = {}
            item['params'] = {
                'info': 'trakt_userlist',
                'list_slug': i.get('ids', {}).get('slug'),
                'user_slug': i.get('user', {}).get('ids', {}).get('slug')}
            item['unique_ids'] = {
                'trakt': i.get('ids', {}).get('trakt'),
                'slug': i.get('ids', {}).get('slug'),
                'user': i.get('user', {}).get('ids', {}).get('slug')}
            items.append(item)
        return items + paginated.get_next_page(response.headers)
