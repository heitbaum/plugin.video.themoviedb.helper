import datetime
import simplecache
import resources.lib.utils as utils
_cache = simplecache.SimpleCache()
_cache_name = 'plugin.video.themoviedb.helper.v4_0_0'


def get_cache(cache_name):
    cache_name = cache_name or ''
    return _cache.get('{}.{}'.format(_cache_name, cache_name))


def set_cache(my_object, cache_name, cache_days=14, force=False):
    cache_name = cache_name or ''
    if force or (my_object and cache_name and cache_days):
        _cache.set('{}.{}'.format(_cache_name, cache_name), my_object, expiration=datetime.timedelta(days=cache_days))
    return my_object


def use_cache(func, *args, **kwargs):
    """
    Simplecache takes func with args and kwargs
    Returns the cached item if it exists otherwise does the function
    """
    cache_days = kwargs.pop('cache_days', 14)
    cache_name = kwargs.pop('cache_name', '') or ''
    cache_only = kwargs.pop('cache_only', False)
    cache_refresh = kwargs.pop('cache_refresh', False)
    if not cache_name:
        for arg in args:
            if arg:
                cache_name = u'{0}/{1}'.format(cache_name, arg)
        for key, value in kwargs.items():
            if value:
                cache_name = u'{0}&{1}={2}'.format(cache_name, key, value)
    my_cache = get_cache(cache_name) if not cache_refresh else None
    if my_cache:
        return my_cache
    elif not cache_only:
        my_object = func(*args, **kwargs)
        return set_cache(my_object, cache_name, cache_days)


def get_search_history(tmdb_type=None):
    if not tmdb_type:
        return []
    cache_name = 'search.history.{}'.format(tmdb_type)
    return get_cache(cache_name) or []


def _add_search_history(tmdb_type=None, query=None, max_entries=9, **kwargs):
    search_history = get_search_history(tmdb_type)
    if query in search_history:  # Remove query if in history because we want it to be first in list
        search_history.remove(query)
    if max_entries and len(search_history) > max_entries:
        search_history.pop(0)  # Remove the oldest query if we hit our max so we don't accumulate months worth of queries
    if query:
        search_history.append(query)
    return search_history


def _replace_search_history(tmdb_type=None, query=None, replace=None, **kwargs):
    search_history = get_search_history(tmdb_type)
    if not isinstance(replace, int) and replace in search_history:
        replace = search_history.index(replace)  # If not an int then we need to look-up index of the item to replace
    if not isinstance(replace, int):
        return  # If we can't find an index don't update the cache so we don't cause unintended modification
    try:  # Use a try block to catch index out of range errors or other issues with updating history
        if query:
            search_history[replace] = query
        else:
            search_history.pop(replace)
    except Exception as exc:
        utils.kodi_log(exc, 1)
        return
    return search_history


def set_search_history(tmdb_type=None, query=None, cache_days=120, clear_cache=False, max_entries=9, replace=False):
    if not tmdb_type:
        return
    cache_name = 'search.history.{}'.format(tmdb_type)
    if not clear_cache:
        func = _add_search_history if replace is False else _replace_search_history
        search_history = func(tmdb_type=tmdb_type, query=query, max_entries=max_entries, replace=replace)
        set_cache(search_history, cache_name=cache_name, cache_days=cache_days)
    return set_cache(None, cache_name, 0, force=True) if clear_cache else query