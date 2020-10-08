import xbmc
import xbmcgui
import datetime
import resources.lib.helpers.plugin as plugin
import resources.lib.helpers.cache as cache
from resources.lib.request.api import RequestAPI
from resources.lib.helpers.downloader import Downloader
from resources.lib.items.listitem import ListItem
from resources.lib.helpers.plugin import ADDON, PLUGINPATH
from resources.lib.helpers.constants import TMDB_ALL_ITEMS_LISTS
from resources.lib.helpers.parser import try_int, try_float
from resources.lib.helpers.timedate import format_date, age_difference
from resources.lib.helpers.setutils import dict_to_list, merge_two_items, del_empty_keys, iter_props, get_params
from resources.lib.helpers.fileutils import use_pickle
from json import loads


IMAGEPATH_ORIGINAL = 'https://image.tmdb.org/t/p/original'
IMAGEPATH_POSTER = 'https://image.tmdb.org/t/p/w500'
API_URL = 'https://api.themoviedb.org/3'
TMDB_GENRE_IDS = {
    "Action": 28, "Adventure": 12, "Animation": 16, "Comedy": 35, "Crime": 80, "Documentary": 99, "Drama": 18,
    "Family": 10751, "Fantasy": 14, "History": 36, "Horror": 27, "Kids": 10762, "Music": 10402, "Mystery": 9648,
    "News": 10763, "Reality": 10764, "Romance": 10749, "Science Fiction": 878, "Sci-Fi & Fantasy": 10765, "Soap": 10766,
    "Talk": 10767, "TV Movie": 10770, "Thriller": 53, "War": 10752, "War & Politics": 10768, "Western": 37}
APPEND_TO_RESPONSE = 'credits,release_dates,content_ratings,external_ids,movie_credits,tv_credits,keywords,reviews'


class TMDb(RequestAPI):
    def __init__(
            self,
            api_key='a07324c669cac4d96789197134ce272b',
            language=plugin.get_language(),
            mpaa_prefix=plugin.get_mpaa_prefix()):
        super(TMDb, self).__init__(
            req_api_name='TMDb',
            req_api_url=API_URL,
            req_api_key='api_key={}'.format(api_key))
        self.iso_language = language[:2]
        self.iso_country = language[-2:]
        self.req_language = '{0}-{1}&include_image_language={0},null'.format(self.iso_language, self.iso_country)
        self.mpaa_prefix = mpaa_prefix
        self.append_to_response = APPEND_TO_RESPONSE

    def get_url_separator(self, separator=None):
        if separator == 'AND':
            return '%2C'
        elif separator == 'OR':
            return '%7C'
        elif not separator:
            return '%2C'
        else:
            return False

    def get_tmdb_id(self, tmdb_type=None, imdb_id=None, tvdb_id=None, query=None, year=None, episode_year=None, raw_data=False, **kwargs):
        func = self.get_request_sc
        if not tmdb_type:
            return
        request = None
        if tmdb_type == 'genre' and query:
            return TMDB_GENRE_IDS.get(query, '')
        elif imdb_id:
            request = func('find', imdb_id, language=self.req_language, external_source='imdb_id')
            request = request.get('{0}_results'.format(tmdb_type), [])
        elif tvdb_id:
            request = func('find', tvdb_id, language=self.req_language, external_source='tvdb_id')
            request = request.get('{0}_results'.format(tmdb_type), [])
        elif query:
            query = query.split(' (', 1)[0]  # Scrub added (Year) or other cruft in parentheses () added by Addons or TVDb
            if tmdb_type == 'tv':
                request = func('search', tmdb_type, language=self.req_language, query=query, first_air_date_year=year)
            else:
                request = func('search', tmdb_type, language=self.req_language, query=query, year=year)
            request = request.get('results', [])
        if not request:
            return
        if raw_data:
            return request
        if tmdb_type == 'tv' and episode_year and len(request) > 1:
            for i in sorted(request, key=lambda k: k.get('first_air_date', ''), reverse=True):
                if not i.get('first_air_date'):
                    continue
                if try_int(i.get('first_air_date', '9999')[:4]) <= try_int(episode_year):
                    if query in [i.get('name'), i.get('original_name')]:
                        return i.get('id')
        return request[0].get('id')

    def get_tmdb_id_from_query(self, tmdb_type, query, header=None, use_details=False, get_listitem=False):
        if not query or not tmdb_type:
            return
        response = TMDb().get_tmdb_id(tmdb_type, query=query, raw_data=True)
        items = [ListItem(**TMDb().get_info(i, tmdb_type, detailed=False)).get_listitem() for i in response]
        x = xbmcgui.Dialog().select(header, items, useDetails=use_details)
        if x != 1:
            return items[x] if get_listitem else items[x].getUniqueID('tmdb')

    def get_translated_list(self, items, tmdb_type=None, separator=None):
        """
        If tmdb_type specified will look-up IDs using search function otherwise assumes item ID is passed
        """
        separator = self.get_url_separator(separator)
        temp_list = ''
        for item in items:
            item_id = self.get_tmdb_id(tmdb_type=tmdb_type, query=item) if tmdb_type else item
            if not item_id:
                continue
            if separator:  # If we've got a url separator then concatinate the list with it
                temp_list = '{}{}{}'.format(temp_list, separator, item_id) if temp_list else item_id
            else:  # If no separator, assume that we just want to use the first found ID
                temp_list = str(item_id)
                break  # Stop once we have a item
        temp_list = temp_list if temp_list else 'null'
        return temp_list

    def get_title(self, item):
        if item.get('title'):
            return item['title']
        if item.get('name'):
            return item['name']
        if item.get('author'):
            return item['author']
        if item.get('width') and item.get('height'):
            return u'{0}x{1}'.format(item['width'], item['height'])

    def get_poster(self, item):
        if item.get('poster_path'):
            return self.get_imagepath(item['poster_path'], poster=True)
        if item.get('profile_path'):
            return self.get_imagepath(item['profile_path'], poster=True)
        if item.get('file_path'):
            return self.get_imagepath(item['file_path'])

    def get_thumb(self, item):
        if item.get('still_path'):
            return self.get_imagepath(item['still_path'])
        return self.get_poster(item)

    def get_fanart(self, item):
        if item.get('backdrop_path'):
            return self.get_imagepath(item['backdrop_path'])

    def get_imagepath(self, path_affix, poster=False):
        if poster:
            return '{}{}'.format(IMAGEPATH_POSTER, path_affix)
        return '{}{}'.format(IMAGEPATH_ORIGINAL, path_affix)

    def get_genre_by_id(self, genre_id):
        for k, v in TMDB_GENRE_IDS.items():
            if v == try_int(genre_id):
                return k

    def get_genres_by_id(self, genre_ids):
        genre_ids = genre_ids or []
        return [self.get_genre_by_id(genre_id) for genre_id in genre_ids if self.get_genre_by_id(genre_id)]

    def get_trailer(self, item):
        if not isinstance(item, dict):
            return
        videos = item.get('videos') or {}
        videos = videos.get('results') or []
        for i in videos:
            if i.get('type', '') != 'Trailer' or i.get('site', '') != 'YouTube' or not i.get('key'):
                continue
            return 'plugin://plugin.video.youtube/play/?video_id={0}'.format(i.get('key'))

    def get_mpaa_rating(self, item):
        if not item.get('release_dates', {}) or not item.get('release_dates', {}).get('results'):
            return
        for i in item.get('release_dates').get('results'):
            if not i.get('iso_3166_1') or i.get('iso_3166_1') != self.iso_country:
                continue
            for i in sorted(i.get('release_dates', []), key=lambda k: k.get('type')):
                if i.get('certification'):
                    return '{0}{1}'.format(self.mpaa_prefix, i.get('certification'))

    def get_episode_infolabel(self, item):
        if 'episode_number' in item:
            return item.get('episode_number')
        if 'episode_count' in item:
            return item.get('episode_count')
        if item.get('seasons'):
            count = 0
            for i in item.get('seasons', []):
                count += try_int(i.get('episode_count', 0))
            return count

    def get_season_infolabel(self, item):
        if 'season_number' in item:
            return item.get('season_number')
        if 'season_count' in item:
            return item.get('season_count')
        if isinstance(item.get('seasons'), list):
            return len(item.get('seasons'))

    def get_infolabels(self, item, tmdb_type, infolabels=None, detailed=True):
        infolabels = infolabels or {}
        infolabels['title'] = self.get_title(item)
        infolabels['originaltitle'] = item.get('original_title')
        infolabels['mediatype'] = plugin.convert_type(tmdb_type, plugin.TYPE_DB)
        infolabels['rating'] = '{:0,.1f}'.format(try_float(item.get('vote_average')))
        infolabels['votes'] = '{:0,.0f}'.format(item.get('vote_count')) if item.get('vote_count') else None
        infolabels['plot'] = item.get('overview') or item.get('biography') or item.get('content')
        infolabels['premiered'] = item.get('air_date') or item.get('release_date') or item.get('first_air_date') or ''
        infolabels['year'] = infolabels.get('premiered')[:4]
        infolabels['genre'] = self.get_genres_by_id(item.get('genre_ids'))
        infolabels['country'] = item.get('origin_country')
        infolabels['season'] = self.get_season_infolabel(item)
        infolabels['episode'] = self.get_episode_infolabel(item)
        infolabels = self._get_detailed_infolabels(item, tmdb_type, infolabels) if detailed else infolabels
        return del_empty_keys(infolabels)

    def _get_detailed_infolabels(self, item, tmdb_type, infolabels=None):
        infolabels = infolabels or {}
        infolabels['genre'] = dict_to_list(item.get('genres', []), 'name')
        infolabels['imdbnumber'] = item.get('imdb_id') or item.get('external_ids', {}).get('imdb_id')
        infolabels['country'] = dict_to_list(item.get('production_countries', []), 'name')
        infolabels['status'] = item.get('status')
        infolabels['tagline'] = item.get('tagline')
        infolabels['director'] = [i.get('name') for i in item.get('credits', {}).get('crew', []) if i.get('name') and i.get('job') == 'Director']
        infolabels['writer'] = [i.get('name') for i in item.get('credits', {}).get('crew', []) if i.get('name') and i.get('department') == 'Writing']
        infolabels['trailer'] = self.get_trailer(item)
        infolabels['mpaa'] = self.get_mpaa_rating(item)
        if item.get('episode_run_time'):
            infolabels['duration'] = try_int(item['episode_run_time'][0]) * 60
        elif item.get('runtime'):
            infolabels['duration'] = try_int(item['runtime']) * 60
        if item.get('networks'):
            infolabels['studio'] = infolabels.setdefault('studio', []) + dict_to_list(item.get('networks'), 'name')
        elif item.get('production_companies'):
            infolabels['studio'] = dict_to_list(item.get('production_companies', []), 'name')
        if item.get('belongs_to_collection'):
            infolabels['set'] = item['belongs_to_collection'].get('name')
        return infolabels

    def get_infoproperties(self, item, tmdb_type, infoproperties=None, detailed=True):
        infoproperties = infoproperties or {}
        infoproperties['tmdb_type'] = tmdb_type
        infoproperties['dbtype'] = plugin.convert_type(tmdb_type, plugin.TYPE_DB)
        infoproperties['role'] = item.get('character') or item.get('job') or item.get('department')
        infoproperties['character'] = item.get('character')
        infoproperties['job'] = item.get('job')
        infoproperties['department'] = item.get('department')
        infoproperties = self._get_detailed_infoproperties(item, tmdb_type, infoproperties) if detailed else infoproperties
        return del_empty_keys(infoproperties)

    def _get_detailed_infoproperties(self, item, tmdb_type, infoproperties=None):
        infoproperties = infoproperties or {}
        if tmdb_type == 'movie':
            if item.get('belongs_to_collection'):
                infoproperties['set.tmdb_id'] = item['belongs_to_collection'].get('id')
                infoproperties['set.name'] = item['belongs_to_collection'].get('name')
                infoproperties['set.poster'] = self.get_imagepath(item['belongs_to_collection'].get('poster_path'))
                infoproperties['set.fanart'] = self.get_imagepath(item['belongs_to_collection'].get('backdrop_path'))
            if item.get('budget'):
                infoproperties['budget'] = '${:0,.0f}'.format(item['budget'])
            if item.get('revenue'):
                infoproperties['revenue'] = '${:0,.0f}'.format(item['revenue'])
            if item.get('spoken_languages'):
                infoproperties = iter_props(
                    item['spoken_languages'], 'language', infoproperties,
                    name='name', iso='iso_639_1')
            if item.get('keywords', {}).get('keywords'):
                infoproperties = iter_props(
                    item['keywords']['keywords'], 'keyword', infoproperties,
                    name='name', tmdb_id='id')
            if item.get('reviews', {}).get('results'):
                infoproperties = iter_props(
                    item['reviews']['results'], 'review', infoproperties,
                    content='content', tmdb_id='id', author='author')
        elif tmdb_type == 'tv':
            infoproperties['type'] = item.get('type')
            if item.get('networks'):
                infoproperties = iter_props(
                    item['networks'], 'studio', infoproperties,
                    name='name', tmdb_id='id')
                infoproperties = iter_props(
                    item['networks'], 'studio', infoproperties,
                    icon='logo_path', func=self.get_imagepath)
            if item.get('created_by'):
                infoproperties = iter_props(
                    item['created_by'], 'creator', infoproperties,
                    name='name', tmdb_id='id')
                infoproperties = iter_props(
                    item['created_by'], 'creator', infoproperties,
                    thumb='profile_path', func=self.get_imagepath)
                infoproperties['creator'] = ' / '.join([i['name'] for i in item.get('created_by', []) if i.get('name')])
            if item.get('last_episode_to_air'):
                i = item.get('last_episode_to_air', {})
                infoproperties['last_aired'] = format_date(i.get('air_date'), xbmc.getRegion('dateshort'))
                infoproperties['last_aired.long'] = format_date(i.get('air_date'), xbmc.getRegion('datelong'))
                infoproperties['last_aired.day'] = format_date(i.get('air_date'), "%A")
                infoproperties['last_aired.episode'] = i.get('episode_number')
                infoproperties['last_aired.name'] = i.get('name')
                infoproperties['last_aired.tmdb_id'] = i.get('id')
                infoproperties['last_aired.plot'] = i.get('overview')
                infoproperties['last_aired.season'] = i.get('season_number')
                infoproperties['last_aired.rating'] = '{:0,.1f}'.format(try_float(i.get('vote_average')))
                infoproperties['last_aired.votes'] = i.get('vote_count')
                infoproperties['last_aired.thumb'] = self.get_imagepath(i.get('still_path'))
            if item.get('next_episode_to_air'):
                i = item.get('next_episode_to_air', {})
                infoproperties['next_aired'] = format_date(i.get('air_date'), xbmc.getRegion('dateshort'))
                infoproperties['next_aired.long'] = format_date(i.get('air_date'), xbmc.getRegion('datelong'))
                infoproperties['next_aired.day'] = format_date(i.get('air_date'), "%A")
                infoproperties['next_aired.episode'] = i.get('episode_number')
                infoproperties['next_aired.name'] = i.get('name')
                infoproperties['next_aired.tmdb_id'] = i.get('id')
                infoproperties['next_aired.plot'] = i.get('overview')
                infoproperties['next_aired.season'] = i.get('season_number')
                infoproperties['next_aired.thumb'] = self.get_imagepath(i.get('still_path'))
        elif tmdb_type == 'person':
            infoproperties['born'] = item.get('place_of_birth')
            infoproperties['biography'] = item.get('biography')
            infoproperties['birthday'] = item.get('birthday')
            infoproperties['deathday'] = item.get('deathday')
            infoproperties['age'] = age_difference(item.get('birthday'), item.get('deathday'))
            if item.get('gender') == 1:
                infoproperties['gender'] = ADDON.getLocalizedString(32071)
            elif item.get('gender') == 2:
                infoproperties['gender'] = ADDON.getLocalizedString(32070)
        return infoproperties

    def get_cast(self, item, cast=None):
        cast = cast or []
        if not item.get('credits') and not item.get('guest_stars'):
            return cast
        cast_item = None
        cast_list = item.get('credits', {}).get('cast', []) + item.get('guest_stars', [])
        for i in sorted(cast_list, key=lambda k: k.get('order', 0)):
            if cast_item:
                if cast_item.get('name') != i.get('name'):
                    cast.append(cast_item)
                    cast_item = None
                elif i.get('character'):
                    cast_item['role'] = u'{} / {}'.format(cast_item.get('role'), i.get('character'))
            if not cast_item:
                cast_item = {
                    'name': i.get('name'),
                    'role': i.get('character'),
                    'order': i.get('order'),
                    'thumbnail': self.get_imagepath(i.get('profile_path'), poster=True) if i.get('profile_path') else ''}
        if cast_item:
            cast.append(cast_item)
        return cast

    def get_art(self, item, art=None):
        art = art or {}
        art['thumb'] = self.get_thumb(item)
        art['poster'] = self.get_poster(item)
        art['fanart'] = self.get_fanart(item)
        return del_empty_keys(art)

    def get_unique_ids(self, item, unique_ids=None):
        unique_ids = unique_ids or {}
        unique_ids['tmdb'] = item.get('id')
        unique_ids['imdb'] = item.get('imdb_id') or item.get('external_ids', {}).get('imdb_id')
        unique_ids['tvdb'] = item.get('external_ids', {}).get('tvdb_id')
        return del_empty_keys(unique_ids)

    def get_info(self, item, tmdb_type, base_item=None, detailed=True, params_definition=None, base_tmdb_type=None):
        base_item = base_item or {}
        if item and tmdb_type:
            base_item['label'] = self.get_title(item)
            base_item['art'] = self.get_art(item, base_item.get('art', {}))
            base_item['infolabels'] = self.get_infolabels(item, tmdb_type, base_item.get('infolabels', {}), detailed=detailed)
            base_item['infoproperties'] = self.get_infoproperties(item, tmdb_type, base_item.get('infoproperties', {}), detailed=detailed)
            base_item['unique_ids'] = self.get_unique_ids(item, base_item.get('unique_ids', {}))
            base_item['params'] = get_params(item, tmdb_type, base_item.get('params', {}), definition=params_definition, base_tmdb_type=base_tmdb_type)
            base_item['path'] = PLUGINPATH
            base_item['cast'] = self.get_cast(item) or [] if detailed else []
        return base_item

    def _get_details_request(self, tmdb_type, tmdb_id, season=None, episode=None, cache_only=False, cache_refresh=False):
        path_affix = []
        if season is not None:
            path_affix += ['season', season]
        if season is not None and episode is not None:
            path_affix += ['episode', episode]
        return self.get_request_lc(
            tmdb_type, tmdb_id, *path_affix,
            append_to_response=self.append_to_response,
            cache_only=cache_only, cache_refresh=cache_refresh) or {}

    def get_details(self, tmdb_type, tmdb_id, season=None, episode=None, cache_only=False, cache_refresh=False, **kwargs):
        if not tmdb_id or not tmdb_type:
            return

        # Check if we've got a quick cached object and use that if available to save time rebuilding season/episode objects
        if not cache_refresh:
            my_cache = cache.get_cache('detailed.quick.item.{}.{}.{}.{}'.format(tmdb_type, tmdb_id, season, episode))
            if my_cache:
                return my_cache

        # Get our base details
        base_item = cache.use_cache(
            self.get_info, tmdb_type=tmdb_type,
            item=self._get_details_request(tmdb_type, tmdb_id, cache_only=cache_only, cache_refresh=cache_refresh),
            cache_name='detailed.item.{}.{}.{}.{}'.format(tmdb_type, tmdb_id, None, None),
            cache_days=cache.CACHE_LONG, cache_only=cache_only, cache_refresh=cache_refresh)

        # If we're getting season/episode details we need to add them to the base tv details
        if tmdb_type == 'tv' and season is not None:
            item = cache.use_cache(
                self.get_info, tmdb_type='tv',
                item=self._get_details_request(tmdb_type, tmdb_id, season, episode, cache_only, cache_refresh),
                cache_name='detailed.item.{}.{}.{}.{}'.format(tmdb_type, tmdb_id, season, episode),
                cache_days=cache.CACHE_LONG, cache_only=cache_only, cache_refresh=cache_refresh)
            if item:
                item = merge_two_items(base_item, item)
                item['infolabels']['tvshowtitle'] = base_item.get('infolabels', {}).get('title')
                item['unique_ids']['tvshow.tmdb'] = tmdb_id
                item['params']['tmdb_id'] = tmdb_id
                item['params']['season'] = season
                if episode is not None:
                    item['params']['episode'] = episode
                base_item = item

        # Save our item as a quick cache object so we don't need to remerge season/episodes every time
        return cache.set_cache(
            base_item, cache_days=cache.CACHE_LONG,
            cache_name='detailed.quick.item.{}.{}.{}.{}'.format(tmdb_type, tmdb_id, season, episode))

    def get_season_list(self, tmdb_id):
        request = self.get_request_sc('tv/{}'.format(tmdb_id))
        base_item = self.get_details('tv', tmdb_id)
        items = []
        items_end = []
        tvshow_title = self.get_details('tv', tmdb_id).get('infolabels', {}).get('title')
        for i in request.get('seasons', []) if request else []:
            item = self.get_info(i, 'tv', base_item.copy())
            item['infolabels']['mediatype'] = 'season'
            item['infolabels']['tvshowtitle'] = tvshow_title
            item['unique_ids']['tvshow.tmdb'] = tmdb_id
            item['unique_ids']['tmdb'] = tmdb_id
            item['params']['tmdb_id'] = tmdb_id
            item['params']['season'] = i.get('season_number')
            items.append(item) if i.get('season_number') != 0 else items_end.append(item)
        return items + items_end

    def get_episode_list(self, tmdb_id, season):
        request = self.get_request_sc('tv/{}/season/{}'.format(tmdb_id, season))
        base_item = self.get_details('tv', tmdb_id, season=season)
        items = []
        for i in request.get('episodes', []) if request else []:
            item = self.get_info(i, 'tv', base_item=base_item.copy())
            item['infolabels']['mediatype'] = 'episode'
            item['unique_ids']['tvshow.tmdb'] = tmdb_id
            item['unique_ids']['tmdb'] = tmdb_id
            item['params']['tmdb_id'] = tmdb_id
            item['params']['season'] = i.get('season_number')
            item['params']['episode'] = i.get('episode_number')
            items.append(item)
        return items

    def get_cast_list(self, tmdb_id, tmdb_type, season=None, episode=None, keys=['cast', 'guest_stars']):
        items = []
        prev_item = {}
        if season is not None and episode is not None:
            affix = 'season/{}/episode/{}'.format(season, episode)
        elif season is not None:
            affix = 'season/{}'.format(season)
        else:
            affix = None
        response = self.get_request_lc(tmdb_type, tmdb_id, affix, 'credits')
        if not response:
            return items
        # Avoid re-adding the same cast/crew member if multiple roles
        # Instead merge infoproperties (ie roles / jobs / departments etc) together and make one item
        prev_item = None
        cast_list = []
        for key in keys:
            cast_list += response.get(key) or []
        for i in cast_list:
            this_item = self.get_info(i, 'person', detailed=False)
            if prev_item and prev_item.get('label') != this_item.get('label'):
                items.append(prev_item)
            elif prev_item:
                infoproperties = prev_item.get('infoproperties', {})
                for k, v in this_item.get('infoproperties', {}).items():
                    if not v:
                        continue
                    if not infoproperties.get(k):
                        infoproperties[k] = v
                    elif infoproperties.get(k) != v:
                        infoproperties[k] = '{} / {}'.format(infoproperties[k], v)
                this_item['infoproperties'] = infoproperties
            prev_item = this_item
        items.append(prev_item) if prev_item else None
        return items

    def _get_downloaded_list(self, export_list, sorting=None, reverse=False, datestamp=None):
        if not export_list or not datestamp:
            return
        download_url = 'https://files.tmdb.org/p/exports/{}_ids_{}.json.gz'.format(export_list, datestamp)
        raw_list = [loads(i) for i in Downloader(download_url=download_url).get_gzip_text().splitlines()]
        return sorted(raw_list, key=lambda k: k.get(sorting, ''), reverse=reverse) if sorting else raw_list

    def get_daily_list(self, export_list, sorting=None, reverse=False):
        if not export_list:
            return
        datestamp = datetime.datetime.now() - datetime.timedelta(days=2)
        datestamp = datestamp.strftime("%m_%d_%Y")
        # Pickle results rather than cache due to being such a large list
        return use_pickle(
            self._get_downloaded_list,
            export_list=export_list, sorting=sorting, reverse=reverse, datestamp=datestamp,
            cache_name='TMDb.Downloaded.List.v2.{}.{}.{}'.format(export_list, sorting, reverse, datestamp))

    def get_all_items_list(self, tmdb_type, page=None):
        if tmdb_type not in TMDB_ALL_ITEMS_LISTS:
            return
        daily_list = self.get_daily_list(
            export_list=TMDB_ALL_ITEMS_LISTS.get(tmdb_type, {}).get('type'),
            sorting=False, reverse=False)
        if not daily_list:
            return
        items = []
        param = TMDB_ALL_ITEMS_LISTS.get(tmdb_type, {}).get('params', {})
        limit = TMDB_ALL_ITEMS_LISTS.get(tmdb_type, {}).get('limit', 20)
        pos_z = try_int(page, fallback=1) * limit
        pos_a = pos_z - limit
        dbtype = plugin.convert_type(tmdb_type, plugin.TYPE_DB)
        for i in daily_list[pos_a:pos_z]:
            if not i.get('id'):
                continue
            if tmdb_type in ['keyword', 'network', 'studio']:
                item = {
                    'label': i.get('name'),
                    'infolabels': {'mediatype': dbtype},
                    'infoproperties': {'dbtype': dbtype},
                    'unique_ids': {'tmdb': i.get('id')},
                    'params': {}}
            else:
                item = self.get_details(tmdb_type, i.get('id'))
            if not item:
                continue
            for k, v in param.items():
                item['params'][k] = v.format(tmdb_id=i.get('id'))
            items.append(item)
        if not items:
            return []
        if TMDB_ALL_ITEMS_LISTS.get(tmdb_type, {}).get('sort'):
            items = sorted(items, key=lambda k: k.get('label', ''))
        if len(daily_list) > pos_z:
            items.append({'next_page': try_int(page, fallback=1) + 1})
        return items

    def get_search_list(self, tmdb_type, **kwargs):
        """ standard kwargs: query= page= """
        kwargs['key'] = 'results'
        return self.get_basic_list('search/{}'.format(tmdb_type), tmdb_type, **kwargs)

    def get_basic_list(self, path, tmdb_type, key='results', params=None, base_tmdb_type=None, **kwargs):
        response = self.get_request_sc(path, **kwargs)
        results = response.get(key, []) if response else []
        items = [self.get_info(
            i, tmdb_type,
            detailed=False,
            params_definition=params,
            base_tmdb_type=base_tmdb_type) for i in results if i]
        if try_int(response.get('page', 0)) < try_int(response.get('total_pages', 0)):
            items.append({'next_page': try_int(response.get('page', 0)) + 1})
        return items

    def get_discover_list(self, tmdb_type, with_id=True, with_separator='AND', **kwargs):
        # TODO: Add with_id=False look-ups and with_separator translations
        # TODO: Check what regions etc we need to have
        path = 'discover/{}'.format(tmdb_type)
        return self.get_basic_list(path, tmdb_type, **kwargs)

    def get_request_sc(self, *args, **kwargs):
        """ Get API request using the short cache """
        kwargs['cache_days'] = cache.CACHE_SHORT
        kwargs['region'] = self.iso_country
        kwargs['language'] = self.req_language
        return self.get_request(*args, **kwargs)

    def get_request_lc(self, *args, **kwargs):
        """ Get API request using the long cache """
        kwargs['cache_days'] = cache.CACHE_LONG
        kwargs['region'] = self.iso_country
        kwargs['language'] = self.req_language
        return self.get_request(*args, **kwargs)
