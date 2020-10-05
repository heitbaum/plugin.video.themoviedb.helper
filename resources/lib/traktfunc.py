import resources.lib.utils as utils
import resources.lib.cache as cache


def is_authorized(func):
    def wrapper(self, *args, **kwargs):
        if kwargs.get('authorize', True) and not self.authorize():
            return
        return func(self, *args, **kwargs)
    return wrapper


def use_activity_cache(activity_type=None, activity_key=None, cache_days=None, pickle_object=False):
    """
    Decorator to cache and refresh if last activity changes
    Optionally can pickle instead of cache if necessary (useful for large objects like sync lists)
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if not self.authorize():
                return

            # Setup getter/setter cache funcs
            func_get = utils.get_pickle if pickle_object else cache.get_cache
            func_set = utils.set_pickle if pickle_object else cache.set_cache

            # Set cache_name
            cache_name = '{}.'.format(func.__name__)
            cache_name = '{}.{}'.format(self.__class__.__name__, cache_name)
            cache_name = cache.format_name(cache_name, *args, **kwargs)

            # Cached response last_activity timestamp matches last_activity from trakt so no need to refresh
            last_activity = self._get_last_activity(activity_type, activity_key)
            cache_object = func_get(cache_name) if last_activity else None
            if cache_object and cache_object.get('last_activity') == last_activity:
                if cache_object.get('response'):
                    return cache_object['response']

            # Either not cached or last_activity doesn't match so get a new request and cache it
            response = func(self, *args, **kwargs)
            if not response:
                return
            func_set(
                {'response': response, 'last_activity': last_activity},
                cache_name=cache_name, cache_days=cache_days)
            return response
        return wrapper
    return decorator
