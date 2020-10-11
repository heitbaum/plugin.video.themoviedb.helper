import resources.lib.helpers.plugin as plugin
from resources.lib.helpers.parser import try_int, try_type
from resources.lib.helpers.constants import IMAGEPATH_ORIGINAL, IMAGEPATH_POSTER, TMDB_GENRE_IDS


def get_imagepath_poster(v, *args, **kwargs):
    return '{}{}'.format(IMAGEPATH_POSTER, v)


def get_imagepath_fanart(v, *args, **kwargs):
    return '{}{}'.format(IMAGEPATH_ORIGINAL, v)


def get_formatted(v, fmt_str, *args, **kwargs):
    return fmt_str.format(v, *args, **kwargs)


def _get_genre_by_id(genre_id):
    for k, v in TMDB_GENRE_IDS.items():
        if v == try_int(genre_id):
            return k


def get_genres_by_id(v, *args, **kwargs):
    genre_ids = v or []
    return [_get_genre_by_id(genre_id) for genre_id in genre_ids if _get_genre_by_id(genre_id)]


def map_item(i, item):
    m = MAPPING
    for k, v in i.items():
        if k not in m:
            continue
        # Iterate over list of dictionaries
        for d in m[k]:
            # Run through type conversion
            if 'type' in d:
                v = try_type(v, d['type'])
            # Run through slicer
            if 'slice' in d:
                v = v[d['slice']]
            # Run through func
            if 'func' in d:
                v = d['func'](v, *d.get('args', []), **d.get('kwargs', {}))
            # Map value onto item dict parent/child keys
            for p, c in d['keys']:
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


def get_info(item, tmdb_type, *args, **kwargs):
    base_item = set_base()
    base_item = map_item(item, base_item) or {}
    base_item['label'] = base_item['infolabels'].get('title')
    base_item['infolabels']['mediatype'] = plugin.convert_type(tmdb_type, plugin.TYPE_DB)
    return base_item


""" Mapping dictionary
keys:       list of tuples containing parent and child key to add value. [('parent', 'child')]
            parent keys: art, unique_ids, infolabels, infoproperties, params
func:       function to call to manipulate values (omit to skip and pass value directly)
(kw)args:   list/dict of args/kwargs to pass to func.
            func is also always passed v as first argument
"""
# TODO: Split mappings into types with a base generic type and combine as needed?
MAPPING = {
    'poster_path': [{
        'keys': [('art', 'poster')],
        'func': get_imagepath_poster}],
    'overview': [{
        'keys': [('infolabels', 'plot')]}],
    'release_date': [{
        'keys': [('infolabels', 'premiered')]}, {
        'keys': [('infolabels', 'year')],
        'slice': slice(0, 4)}],
    'genre_ids': [{
        'keys': [('infolabels', 'plot')],
        'func': get_genres_by_id}],
    'id': [{
        'keys': [('unique_ids', 'tmdb')]}],
    'original_title': [{
        'keys': [('infolabels', 'originaltitle')]}],
    'title': [{
        'keys': [('infolabels', 'title')]}],
    'backdrop_path': [{
        'keys': [('art', 'fanart')],
        'func': get_imagepath_fanart}],
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
        'args': ['{:0,.0f}']}]
}
