import xbmc
import xbmcgui
import random
import datetime
import resources.lib.utils as utils
import resources.lib.cache as cache
import resources.lib.plugin as plugin
import resources.lib.paginated as paginated
from json import loads, dumps
from resources.lib.requestapi import RequestAPI
from resources.lib.plugin import ADDON, PLUGINPATH
from resources.lib.paginated import PaginatedItems


def _sort_itemlist(items, sort_by=None, sort_how=None, trakt_type=None):
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
    elif sort_by == 'year':
        return sorted(items, key=lambda i: i.get(trakt_type or i.get('type'), {}).get('year'), reverse=reverse)
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


class TraktItems():
    def __init__(self, items, sort_by=None, sort_how=None, trakt_type=None):
        self.items = items or []
        self.trakt_type = trakt_type
        self.sort_by = sort_by or 'unsorted'
        self.sort_how = sort_how

    def get_sorted_items(self, sort_by=None, sort_how=None):
        self.sort_by = sort_by or self.sort_by
        self.sort_how = sort_how or self.sort_how
        self.items = _sort_itemlist(self.items, self.sort_by, self.sort_how, self.trakt_type)
        return self.items
