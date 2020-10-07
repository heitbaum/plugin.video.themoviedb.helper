import datetime
import resources.lib.utils as utils
import resources.lib.cache as cache
from resources.lib.cache import use_simple_cache
from resources.lib.paginated import PaginatedItems
from resources.lib.traktitems import TraktItems
from resources.lib.traktfunc import is_authorized, use_activity_cache


class _TraktProgress():
    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_inprogress_shows_list(self, page=1, limit=20, params=None, next_page=True):
        response = TraktItems(self._get_inprogress_shows(), trakt_type='show').build_items()
        response = PaginatedItems(response['items'], page=page, limit=limit)
        if not next_page:
            return response.items
        return response.items + response.next_page

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def _get_inprogress_shows(self):
        response = self.get_sync('watched', 'show')
        response = TraktItems(response).sort_items('watched', 'desc')
        hidden_shows = self.get_hiddenitems('show')
        return [i for i in response if self._is_inprogress_show(i, hidden_shows)]

    def _is_inprogress_show(self, item, hidden_shows=None):
        """
        Checks whether the show passed is in progress by comparing total and watched
        Optionally can pass a list of hidden_shows trakt slugs to ignore
        """
        slug = item.get('show', {}).get('ids', {}).get('slug')
        if hidden_shows and slug in hidden_shows:
            return
        aired_episodes = item.get('show', {}).get('aired_episodes', 0)
        if not aired_episodes:
            return
        watch_episodes = self.get_episodes_watchcount(slug, 'slug', tvshow=item, count_progress=True)
        if aired_episodes > watch_episodes:
            return item

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_LONG)
    def get_episodes_watchcount(
            self, unique_id, id_type, season=None, exclude_specials=True,
            tvshow=None, count_progress=False):
        """
        Get the number of episodes watched in a show or season
        Pass tvshow dict directly for speed otherwise will look-up ID from watched sync list
        Use count_progress to check progress against reset_at value rather than just count watched
        """
        season = utils.try_parse_int(season) if season is not None else None
        if not tvshow and id_type and unique_id:
            tvshow = self.get_sync('watched', 'show', id_type).get(unique_id)
        if not tvshow:
            return
        reset_at = None
        if count_progress and tvshow.get('reset_at'):
            reset_at = utils.convert_timestamp(tvshow['reset_at'])
        count = 0
        for i in tvshow.get('seasons', []):
            if season is not None and i.get('number', -1) != season:
                continue
            if exclude_specials and i.get('number') == 0:
                continue
            # Reset_at is None so just count length of watched episode list
            if not reset_at:
                count += len(i.get('episodes', []))
                continue
            # Reset_at has a value so check progress rather than just watched count
            for j in i.get('episodes', []):
                if utils.convert_timestamp(j.get('last_watched_at')) >= reset_at:
                    continue
                count += 1
        return count

    @is_authorized
    @use_activity_cache(cache_days=cache.CACHE_LONG)
    def get_hiddenitems(
            self, trakt_type, progress_watched=True, progress_collected=True,
            calendar=True, id_type='slug'):
        """ Get items that are hidden on Trakt """
        hidden_items = set()
        if not trakt_type or not id_type:
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

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_upnext_list(self, unique_id, id_type=None, page=1, limit=20):
        """ Gets the next episodes for a show that user should watch next """
        if id_type != 'slug':
            unique_id = self.get_id(unique_id, id_type, 'show', output_type='slug')
        if unique_id:
            showitem = self.get_details('show', unique_id)
            response = self.get_upnext_episodes(unique_id, showitem)
            response = TraktItems(response, trakt_type='episode').configure_items(params_definition={
                'info': 'details', 'tmdb_type': '{tmdb_type}', 'tmdb_id': '{tmdb_id}',
                'season': '{season}', 'episode': '{number}'})
            response = PaginatedItems(response, page=page, limit=utils.try_parse_int(limit) or 20)
            return response.items + response.next_page

    @is_authorized
    def get_upnext_episodes_list(self, page=1, limit=20, sort_by_premiered=False):
        """ Gets a list of episodes for in-progress shows that user should watch next """
        response = self._get_upnext_episodes_list(sort_by_premiered=sort_by_premiered)
        response = TraktItems(response, trakt_type='episode').configure_items(params_definition={
            'info': 'details', 'tmdb_type': '{tmdb_type}', 'tmdb_id': '{tmdb_id}',
            'season': '{season}', 'episode': '{number}'})
        response = PaginatedItems(response['items'], page=page, limit=utils.try_parse_int(limit) or 20)
        return response.items + response.next_page

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def _get_upnext_episodes_list(self, sort_by_premiered=False):
        shows = self._get_inprogress_shows() or []
        items = [j for j in (self.get_upnext_episodes(
            i.get('show', {}).get('ids', {}).get('slug'), i.get('show', {}), get_single_episode=True)
            for i in shows) if j]
        if sort_by_premiered:
            items = [
                {'show': i.get('show'), 'episode': self.get_details(
                    'show', i.get('show', {}).get('ids', {}).get('slug'),
                    season=i.get('episode', {}).get('season'),
                    episode=i.get('episode', {}).get('number')) or i.get('episode')}
                for i in items]
            items = TraktItems(items, trakt_type='episode').sort_items('released', 'desc')
        return items

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_show_progress(self, uid, hidden=False, specials=False, count_specials=False):
        # TODO: Check last_activity stamp of show to see if we need to cache_refresh
        return self.get_response_json('shows', uid, 'progress/watched') if uid else None

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_upnext_episodes(self, slug, show, get_single_episode=False):
        """
        Get the next episode(s) to watch for a show
        Even though show dict is passed, slug is needed for cache naming purposes
        Set get_single_episode to only retrieve the next_episode value
        Otherwise returns a list of episodes to watch
        """
        # Get show progress
        response = self.get_show_progress(slug)
        if not response:
            return
        # For single episodes just grab next episode and add in show details
        if get_single_episode:
            if not response.get('next_episode'):
                return
            item = {'show': show, 'episode': response['next_episode']}
            return item
        # For list of episodes we need to build them
        # Get show reset_at value
        reset_at = None
        if response.get('reset_at'):
            reset_at = utils.convert_timestamp(response['reset_at'])
        # Get next episode items
        return [
            {'show': show, 'episode': {'number': episode.get('number'), 'season': season.get('number')}}
            for season in response.get('seasons', []) for episode in season
            if not episode.get('completed')
            or (reset_at and utils.convert_timestamp(episode.get('last_watched_at')) < reset_at)]

    @is_authorized
    @use_activity_cache('movies', 'watched_at', cache_days=cache.CACHE_LONG)
    def get_movie_playcount(self, unique_id, id_type):
        return self.get_sync('watched', 'movie', id_type).get(unique_id, {}).get('plays')

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_LONG)
    def get_episode_playcount(self, unique_id, id_type, season, episode):
        season = utils.try_parse_int(season, fallback=-2)  # Make fallback -2 to prevent matching on 0
        episode = utils.try_parse_int(episode, fallback=-2)  # Make fallback -2 to prevent matching on 0
        for i in self.get_sync('watched', 'show', id_type).get(unique_id, {}).get('seasons', []):
            if i.get('number', -1) != season:
                continue
            for j in i.get('episodes', []):
                if j.get('number', -1) == episode:
                    return j.get('plays', 1)

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_episodes_airedcount(self, unique_id, id_type, season=None):
        """ Gets the number of aired episodes for a tvshow """
        if season is not None:
            return self.get_season_episodes_airedcount(unique_id, id_type, season)
        return self.get_sync('watched', 'show', id_type).get(unique_id, {}).get('show', {}).get('aired_episodes')

    @is_authorized
    @use_activity_cache('episodes', 'watched_at', cache_days=cache.CACHE_SHORT)
    def get_season_episodes_airedcount(self, unique_id, id_type, season):
        season = utils.try_parse_int(season, fallback=-2)
        slug = self.get_id(unique_id, id_type, trakt_type='show', output_type='slug')
        for i in self.get_request_sc('shows', slug, 'seasons', extended='full'):
            if i.get('number', -1) == season:
                return i.get('aired_episodes')

    def get_calendar(self, tmdbtype, user=True, start_date=None, days=None):
        user = 'my' if user else 'all'
        return self.get_response_json('calendars', user, tmdbtype, start_date, days, extended='full')

    @is_authorized
    @use_simple_cache(cache_days=cache.CACHE_SHORT)
    def get_calendar_episodes(self, startdate=0, days=1):
        # Broaden date range in case utc conversion bumps into different day
        mod_date = utils.try_parse_int(startdate) - 1
        mod_days = utils.try_parse_int(days) + 2
        date = datetime.date.today() + datetime.timedelta(days=mod_date)
        return self.get_calendar('shows', True, start_date=date.strftime('%Y-%m-%d'), days=mod_days)
