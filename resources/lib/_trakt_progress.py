import datetime
import resources.lib.utils as utils
from resources.lib.plugin import PLUGINPATH


class _TraktProgressMixin():
    def get_movie_playcount(self, id_type, unique_id):
        return self.get_sync('watched', 'movie', id_type).get(unique_id, {}).get('plays')

    def get_episode_playcount(self, id_type, unique_id, season, episode):
        season = utils.try_parse_int(season, fallback=-2)  # Make fallback -2 to prevent matching on 0
        episode = utils.try_parse_int(episode, fallback=-2)  # Make fallback -2 to prevent matching on 0
        for i in self.get_sync('watched', 'show', id_type).get(unique_id, {}).get('seasons', []):
            if i.get('number', -1) != season:
                continue
            for j in i.get('episodes', []):
                if j.get('number', -1) == episode:
                    return j.get('plays', 1)

    def get_episodes_airedcount(self, id_type, unique_id, season=None):
        # For seasons we need to lookup indiviual seasons as Trakt doesn't provide aired count per season in watched sync
        if season is not None:
            season = utils.try_parse_int(season, fallback=-2)
            slug = self.get_id(id_type, unique_id, trakt_type='show', output_type='slug')
            for i in self.get_request_sc('shows', slug, 'seasons', extended='full'):
                if i.get('number', -1) == season:
                    return i.get('aired_episodes')
            return 0
        # For shows aired count we use short (not long) cache watched sync because aired numbers can change day to day
        return self.get_sync('watched_sc', 'show', id_type).get(
            unique_id, {}).get('show', {}).get('aired_episodes')

    def get_episodes_watchcount(self, id_type=None, unique_id=None, season=None, exclude_specials=True, tvshow=None):
        if (not unique_id or not id_type) and not tvshow:
            return
        count = 0
        season = utils.try_parse_int(season) if season is not None else None
        tvshow = tvshow or self.get_sync('watched', 'show', id_type).get(unique_id, {})
        reset_at = tvshow.get('reset_at')
        for i in tvshow.get('seasons', []):
            if season is not None and i.get('number', -1) != season:
                continue
            if exclude_specials and i.get('number') == 0:
                continue
            count += self._get_episodes_watchcount(i.get('episodes', []), reset_at=reset_at)
        return count

    def _get_episodes_watchcount(self, episodes, reset_at=None):
        count = 0
        reset_at = utils.convert_timestamp(reset_at) if reset_at else None
        for episode in episodes:
            last_watched_at = episode.get('last_watched_at')
            if not last_watched_at:
                continue
            if reset_at:
                try:
                    if utils.convert_timestamp(last_watched_at) < reset_at:
                        continue
                except Exception as exc:
                    utils.kodi_log(exc, 1)
            count += 1
        return count

    def _get_inprogress_shows(self):
        items = []
        if not self.authorize():
            return
        recently_watched = self._sort_itemlist(self.get_sync('watched_sc', 'show'), sort_by='watched', sort_how='desc')
        hidden_shows = self.get_hiddenitems('show')
        for i in recently_watched:
            if i.get('show', {}).get('ids', {}).get('slug') in hidden_shows:
                continue  # Show is hidden so skip
            if i.get('show', {}).get('aired_episodes') > self.get_episodes_watchcount(tvshow=i):
                items.append(i)  # More aired episodes than watched so must be in-progress
        return items

    def get_show_progress(self, uid, hidden=False, specials=False, count_specials=False):
        if not uid:
            return
        return self.use_activity_cache(
            'show', 'watched_at', 'trakt.shows.{}.progress.watched'.format(uid), self.cache_short,
            self.get_response_json, 'shows', uid, 'progress/watched')

    def get_upnext_episodes(self, tvshow_details, get_single_episode=False):
        if not tvshow_details or not tvshow_details.get('ids', {}).get('slug'):
            return
        cache_name = 'trakt.shows.{}.{}.upnext.episodes'.format(
            tvshow_details.get('ids', {}).get('slug'), get_single_episode)
        return self.use_activity_cache(
            'show', 'watched_at', cache_name, self.cache_short,
            self._get_upnext_episodes, tvshow_details, get_single_episode=get_single_episode)

    def _get_upnext_episodes(self, tvshow_details, get_single_episode=False):
        items = []
        slug = tvshow_details.get('ids', {}).get('slug')
        response = self.get_show_progress(slug)
        reset_at = utils.convert_timestamp(response['reset_at']) if response.get('reset_at') else None
        for season in response.get('seasons') or []:
            s_num = season.get('number')
            for episode in season.get('episodes') or []:
                if episode.get('completed'):
                    if not reset_at:
                        continue  # Already watched and user hasn't restarted watching so not an upnext episode
                    elif utils.convert_timestamp(episode.get('last_watched_at')) >= reset_at:
                        continue  # Already watched since user restarted watching so not an upnext episode
                item = {
                    'path': PLUGINPATH,
                    'params': {
                        'info': 'details',
                        'tmdb_id': tvshow_details.get('ids', {}).get('tmdb'),
                        'tmdb_type': 'tv',
                        'season': s_num,
                        'episode': episode.get('number')},
                    'art': {},
                    'infoproperties': {},
                    'infolabels': {
                        'tvshowtitle': tvshow_details.get('title'),
                        'mediatype': 'episode',
                        'season': s_num,
                        'episode': episode.get('number')},
                    'unique_ids': {
                        'tvshow.tmdb': tvshow_details.get('ids', {}).get('tmdb'),
                        'tvshow.tvdb': tvshow_details.get('ids', {}).get('tvdb'),
                        'tvshow.imdb': tvshow_details.get('ids', {}).get('imdb'),
                        'tvshow.slug': tvshow_details.get('ids', {}).get('slug'),
                        'tvshow.trakt': tvshow_details.get('ids', {}).get('trakt')}}
                if get_single_episode:
                    return item
                items.append(item)
        if not get_single_episode:
            return items  # TODO: Return first season if none for upnext season (maybe do elsewhere)

    def get_calendar(self, tmdbtype, user=True, start_date=None, days=None):
        user = 'my' if user else 'all'
        return self.get_response_json('calendars', user, tmdbtype, start_date, days, extended='full')

    def get_calendar_episodes(self, startdate=0, days=1):
        if not self.authorize():
            return

        # Broaden date range in case utc conversion bumps into different day
        mod_date = utils.try_parse_int(startdate) - 1
        mod_days = utils.try_parse_int(days) + 2

        # Get our calendar response
        date = datetime.date.today() + datetime.timedelta(days=mod_date)
        return self.get_calendar('shows', True, start_date=date.strftime('%Y-%m-%d'), days=mod_days)
