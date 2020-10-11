import xbmc
import resources.lib.helpers.plugin as plugin
from resources.lib.helpers.parser import try_int, try_type, try_float
from resources.lib.helpers.setutils import iter_props, dict_to_list, get_params
from resources.lib.helpers.timedate import format_date
from resources.lib.helpers.constants import IMAGEPATH_ORIGINAL, IMAGEPATH_POSTER, TMDB_GENRE_IDS


UPDATE_BASEKEY = 1


def get_imagepath_poster(v):
    return '{}{}'.format(IMAGEPATH_POSTER, v)


def get_imagepath_fanart(v):
    return '{}{}'.format(IMAGEPATH_ORIGINAL, v)


def get_formatted(v, fmt_str, *args, **kwargs):
    return fmt_str.format(v, *args, **kwargs)


def get_runtime(v, *args, **kwargs):
    if isinstance(v, list):
        v = v[0]
    return try_int(v) * 60


def get_iter_props(v, base_name, *args, **kwargs):
    infoproperties = {}
    if kwargs.get('basic_keys'):
        infoproperties = iter_props(
            v, base_name, infoproperties, **kwargs['basic_keys'])
    if kwargs.get('image_keys'):
        infoproperties = iter_props(
            v, base_name, infoproperties, func=get_imagepath_poster, **kwargs['image_keys'])
    return infoproperties


def _get_genre_by_id(genre_id):
    for k, v in TMDB_GENRE_IDS.items():
        if v == try_int(genre_id):
            return k


def get_genres_by_id(v):
    genre_ids = v or []
    return [_get_genre_by_id(genre_id) for genre_id in genre_ids if _get_genre_by_id(genre_id)]


def get_episode_to_air(v, name):
    i = v or {}
    infoproperties = {}
    infoproperties['{}'.format(name)] = format_date(i.get('air_date'), xbmc.getRegion('dateshort'))
    infoproperties['{}.long'.format(name)] = format_date(i.get('air_date'), xbmc.getRegion('datelong'))
    infoproperties['{}.day'.format(name)] = format_date(i.get('air_date'), "%A")
    infoproperties['{}.episode'.format(name)] = i.get('episode_number')
    infoproperties['{}.name'.format(name)] = i.get('name')
    infoproperties['{}.tmdb_id'.format(name)] = i.get('id')
    infoproperties['{}.plot'.format(name)] = i.get('overview')
    infoproperties['{}.season'.format(name)] = i.get('season_number')
    infoproperties['{}.rating'.format(name)] = '{:0,.1f}'.format(try_float(i.get('vote_average')))
    infoproperties['{}.votes'.format(name)] = i.get('vote_count')
    infoproperties['{}.thumb'.format(name)] = get_imagepath_poster(i.get('still_path'))
    return infoproperties


def map_item(i, item):
    am = ADVANCED_MAPPING
    sm = STANDARD_MAPPING

    for k, v in i.items():
        if not v:
            continue
        # Simple mapping is quicker so do that first if we can
        if k in sm:
            item[sm[k][0]][sm[k][1]] = v
            continue
        # Check key is in advanced map before trying to map it
        if k not in am:
            continue
        # Iterate over list of dictionaries
        for d in am[k]:
            # Run through slicer
            if 'slice' in d:
                v = v[d['slice']]
            # Run through type conversion
            if 'type' in d:
                v = try_type(v, d['type'])
            # Run through func
            if 'func' in d:
                v = d['func'](v, *d.get('args', []), **d.get('kwargs', {}))
            # Map value onto item dict parent/child keys
            for p, c in d['keys']:
                if c == UPDATE_BASEKEY:
                    item[p].update(v)
                elif 'extend' in d and isinstance(item[p].get(c), list) and isinstance(v, list):
                    item[p][c] += v
                else:
                    item[p][c] = v
    return item


def set_base(item=None):
    item = item or {}
    item.setdefault('art', {})
    item.setdefault('cast', [])
    item.setdefault('infolabels', {})
    item.setdefault('infoproperties', {})
    item.setdefault('unique_ids', {})
    item.setdefault('params', {})
    return item


def get_info(item, tmdb_type, base_item=None, **kwargs):
    base_item = set_base()
    base_item = map_item(item, base_item) or {}
    base_item['label'] = base_item['infolabels'].get('title')
    base_item['infolabels']['mediatype'] = plugin.convert_type(tmdb_type, plugin.TYPE_DB)
    base_item['art']['thumb'] = base_item['art'].get('thumb') or base_item['art'].get('poster')
    base_item['params'] = get_params(
        item, tmdb_type, base_item.get('params', {}),
        definition=kwargs.get('params_definition'),
        base_tmdb_type=kwargs.get('base_tmdb_type'))
    return base_item


""" Mapping dictionary
keys:       list of tuples containing parent and child key to add value. [('parent', 'child')]
            parent keys: art, unique_ids, infolabels, infoproperties, params
func:       function to call to manipulate values (omit to skip and pass value directly)
(kw)args:   list/dict of args/kwargs to pass to func.
            func is also always passed v as first argument

"""

ADVANCED_MAPPING = {
    'poster_path': [{
        'keys': [('art', 'poster')],
        'func': get_imagepath_poster}],
    'profile_path': [{
        'keys': [('art', 'poster')],
        'func': get_imagepath_poster}],
    'file_path': [{
        'keys': [('art', 'poster')],
        'func': get_imagepath_fanart}],
    'still_path': [{
        'keys': [('art', 'thumb')],
        'func': get_imagepath_fanart}],
    'backdrop_path': [{
        'keys': [('art', 'fanart')],
        'func': get_imagepath_fanart}],
    'release_date': [{
        'keys': [('infolabels', 'premiered')]}, {
        'keys': [('infolabels', 'year')],
        'slice': slice(0, 4)}],
    'first_air_date': [{
        'keys': [('infolabels', 'premiered')]}, {
        'keys': [('infolabels', 'year')],
        'slice': slice(0, 4)}],
    'genre_ids': [{
        'keys': [('infolabels', 'genre')],
        'func': get_genres_by_id}],
    'popularity': [{
        'keys': [('infoproperties', 'popularity')],
        'type': str}],
    'vote_count': [{
        'keys': [('infolabels', 'votes')],
        'type': float,
        'func': get_formatted,
        'args': ['{:0,.0f}']}],
    'vote_average': [{
        'keys': [('infolabels', 'rating')],
        'type': float,
        'func': get_formatted,
        'args': ['{:0,.0f}']}],
    'created_by': [{
        'keys': [('infoproperties', UPDATE_BASEKEY)],
        'func': get_iter_props,
        'args': ['creator'],
        'kwargs': {
            'basic_keys': {'name': 'name', 'tmdb_id': 'id'},
            'image_keys': {'thumb': 'profile_path'}}}],
    'episode_run_time': [{
        'keys': [('infolabels', 'duration')],
        'func': get_runtime}],
    'genres': [{
        'keys': [('infolabels', 'genre')],
        'func': dict_to_list,
        'args': ['name']}],
    'networks': [{
        'keys': [('infolabels', 'studio')],
        'extend': True,
        'func': dict_to_list,
        'args': ['name']}],
    'production_companies': [{
        'keys': [('infolabels', 'studio')],
        'extend': True,
        'func': dict_to_list,
        'args': ['name']}],
    'last_episode_to_air': [{
        'keys': [('infoproperties', UPDATE_BASEKEY)],
        'func': get_episode_to_air,
        'args': ['last_aired']}],
    'next_episode_to_air': [{
        'keys': [('infoproperties', UPDATE_BASEKEY)],
        'func': get_episode_to_air,
        'args': ['next_aired']}]
}


STANDARD_MAPPING = {
    'overview': ('infolabels', 'plot'),
    'id': ('unique_ids', 'tmdb'),
    'original_title': ('infolabels', 'originaltitle'),
    'original_name': ('infolabels', 'originaltitle'),
    'title': ('infolabels', 'title'),
    'name': ('infolabels', 'title'),
    'origin_country': ('infolabels', 'country'),
    'status': ('infolabels', 'status'),
    'season_number': ('infolabels', 'season')
}
