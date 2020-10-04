import xbmc
import xbmcgui
import resources.lib.utils as utils
from resources.lib.plugin import ADDON, ADDONPATH, PLUGINPATH


class ListItem(object):
    def __init__(
            self, label=None, label2=None, path=None, library=None, is_folder=True, params=None, next_page=None,
            parent_params=None, infolabels=None, infoproperties=None, art=None, cast=None,
            context_menu=None, stream_details=None, unique_ids=None,
            **kwargs):
        self.label = label or ''
        self.label2 = label2 or ''
        self.path = path or PLUGINPATH
        self.params = params or {}
        self.parent_params = parent_params or {}
        self.library = library or 'video'
        self.is_folder = is_folder
        self.infolabels = infolabels or {}
        self.infoproperties = infoproperties or {}
        self.art = art or {}
        self.cast = cast or []
        self.context_menu = context_menu or []
        self.stream_details = stream_details or {}
        self.unique_ids = unique_ids or {}
        self.set_as_next_page(next_page)

    def set_as_next_page(self, next_page=None):
        if not next_page:
            return
        self.label = xbmc.getLocalizedString(33078)
        self.art['thumb'] = '{}/resources/icons/tmdb/nextpage.png'.format(ADDONPATH)
        self.infoproperties['specialsort'] = 'bottom'
        self.params = self.parent_params.copy()
        self.params['page'] = next_page
        self.params.pop('update_listing', None)  # Just in case we updated the listing for search results
        self.path = PLUGINPATH
        self.is_folder = True

    def set_art_fallbacks(self):
        if not self.art.get('thumb'):
            self.art['thumb'] = '{}/resources/poster.png'.format(ADDONPATH)
        if not self.art.get('fanart'):
            self.art['fanart'] = '{}/fanart.jpg'.format(ADDONPATH)
        return self.art

    def get_trakt_type(self):
        if self.infolabels.get('mediatype') == 'movie':
            return 'movie'
        if self.infolabels.get('mediatype') == 'tvshow':
            return 'show'
        if self.infolabels.get('mediatype') == 'season':
            return 'season'
        if self.infolabels.get('mediatype') == 'episode':
            return 'episode'

    def get_tmdb_type(self):
        if self.infolabels.get('mediatype') == 'movie':
            return 'movie'
        if self.infolabels.get('mediatype') in ['tvshow', 'season', 'episode']:
            return 'tv'
        if self.infoproperties.get('tmdb_type') == 'person':
            return 'person'

    def get_ftv_type(self):
        if self.infolabels.get('mediatype') == 'movie':
            return 'movies'
        if self.infolabels.get('mediatype') in ['tvshow', 'season', 'episode']:
            return 'tv'

    def get_ftv_id(self):
        if self.infolabels.get('mediatype') == 'movie':
            return self.unique_ids.get('tmdb')
        if self.infolabels.get('mediatype') == 'tvshow':
            return self.unique_ids.get('tvdb')
        if self.infolabels.get('mediatype') in ['season', 'episode']:
            return self.unique_ids.get('tvshow.tvdb')

    def get_tmdb_id(self):
        if self.infolabels.get('mediatype') in ['season', 'episode']:
            return self.unique_ids.get('tvshow.tmdb')
        return self.unique_ids.get('tmdb')

    def is_unaired(self, format_label=u'[COLOR=ffcc0000][I]{}[/I][/COLOR]', check_hide_settings=True):
        if not self.infolabels.get('mediatype') in ['movie', 'tvshow', 'season', 'episode']:
            return
        try:
            if utils.is_future_timestamp(self.infolabels.get('premiered'), "%Y-%m-%d", 10):
                if format_label:
                    self.label = format_label.format(self.label)
                if not check_hide_settings:
                    return True
                elif self.infolabels.get('mediatype') == 'movie':
                    if ADDON.getSettingBool('hide_unaired_movies'):
                        return True
                elif self.infolabels.get('mediatype') in ['tv', 'season', 'episode']:
                    if ADDON.getSettingBool('hide_unaired_episodes'):
                        return True
        except Exception as exc:
            utils.kodi_log(u'Error: {}'.format(exc), 1)

    def _context_item_get_ftv_artwork(self):
        ftv_id = self.get_ftv_id()
        ftv_type = self.get_ftv_type()
        if not ftv_type or not ftv_id:
            return []
        path = 'manage_artwork,ftv_type={},ftv_id={}'.format(ftv_type, ftv_id)
        return [(ADDON.getLocalizedString(32222), 'RunScript(plugin.video.themoviedb.helper,{})'.format(path))]

    def _context_item_refresh_details(self):
        tmdb_id = self.get_tmdb_id()
        tmdb_type = self.get_tmdb_type()
        if not tmdb_type or not tmdb_id:
            return []
        path = 'refresh_details,tmdb_type={},tmdb_id={}'.format(tmdb_type, tmdb_id)
        return [(ADDON.getLocalizedString(32233), 'RunScript(plugin.video.themoviedb.helper,{})'.format(path))]

    def _context_item_related_lists(self):
        tmdb_id = self.get_tmdb_id()
        tmdb_type = self.get_tmdb_type()
        if not tmdb_type or not tmdb_id:
            return []
        path = 'related_lists,tmdb_type={},tmdb_id={}'.format(tmdb_type, tmdb_id)
        if self.infolabels.get('mediatype') == 'episode':
            path = '{},season={}'.format(path, self.infolabels.get('season'))
            path = '{},episode={}'.format(path, self.infolabels.get('episode'))
        return [(ADDON.getLocalizedString(32235), 'RunScript(plugin.video.themoviedb.helper,{})'.format(path))]

    def _context_item_trakt_sync(self):
        tmdb_id = self.get_tmdb_id()
        trakt_type = self.get_trakt_type()
        if not trakt_type or not tmdb_id:
            return []
        path = 'sync_item,trakt_type={},unique_id={},id_type=tmdb'.format(trakt_type, tmdb_id)
        if self.infolabels.get('mediatype') == 'season':
            path = '{},season={}'.format(path, self.infolabels.get('season'))
        elif self.infolabels.get('mediatype') == 'episode':
            path = '{},season={}'.format(path, self.infolabels.get('season'))
            path = '{},episode={}'.format(path, self.infolabels.get('episode'))
        return [('Trakt management', 'RunScript(plugin.video.themoviedb.helper,{})'.format(path))]

    def set_standard_context_menu(self):
        self.context_menu += self._context_item_related_lists()
        self.context_menu += self._context_item_get_ftv_artwork()
        self.context_menu += self._context_item_refresh_details()
        self.context_menu += self._context_item_trakt_sync()
        return self.context_menu

    def set_playcount(self, playcount):
        playcount = utils.try_parse_int(playcount)
        if self.infolabels.get('mediatype') in ['movie', 'episode']:
            if playcount:
                self.infolabels['playcount'] = playcount
                self.infolabels['overlay'] = 5
        elif self.infolabels.get('mediatype') in ['tvshow', 'season']:
            if utils.try_parse_int(self.infolabels.get('episode')):
                self.infoproperties['watchedepisodes'] = playcount
                self.infoproperties['totalepisodes'] = utils.try_parse_int(self.infolabels.get('episode'))
                self.infoproperties['unwatchedepisodes'] = self.infoproperties.get('totalepisodes') - utils.try_parse_int(self.infoproperties.get('watchedepisodes'))
                if playcount and not self.infoproperties.get('unwatchedepisodes'):
                    self.infolabels['playcount'] = playcount
                    self.infolabels['overlay'] = 5

    def set_details(self, details=None, reverse=False):
        if not details:
            return
        self.stream_details = utils.merge_two_dicts(details.get('stream_details', {}), self.stream_details, reverse=reverse)
        self.infolabels = utils.merge_two_dicts(details.get('infolabels', {}), self.infolabels, reverse=reverse)
        self.infoproperties = utils.merge_two_dicts(details.get('infoproperties', {}), self.infoproperties, reverse=reverse)
        self.art = utils.merge_two_dicts(details.get('art', {}), self.art, reverse=reverse)
        self.unique_ids = utils.merge_two_dicts(details.get('unique_ids', {}), self.unique_ids, reverse=reverse)
        self.cast = self.cast or details.get('cast', [])

    def set_params_info_reroute(self):
        if self.params.get('info') != 'details':
            return
        if self.infoproperties.get('tmdb_type') == 'person':
            self.params['info'] = 'related'
            self.params['tmdb_type'] = 'person'
            self.params['tmdb_id'] = self.unique_ids.get('tmdb')
            self.is_folder = False
        elif self.infolabels.get('mediatype') in ['movie', 'episode', 'video']:
            self.params['info'] = 'play'
            self.is_folder = False
        elif self.infolabels.get('mediatype') == 'tvshow':
            self.params['info'] = 'seasons'
        elif self.infolabels.get('mediatype') == 'season':
            self.params['info'] = 'episodes'
        elif self.infolabels.get('mediatype') == 'set':
            self.params['info'] = 'collection'

    def set_episode_label(self, format_label=u'{season}x{episode:0>2}. {label}'):
        if not self.infolabels.get('mediatype') == 'episode':
            return
        season = utils.try_parse_int(self.infolabels.get('season', 0))
        episode = utils.try_parse_int(self.infolabels.get('episode', 0))
        if not season or not episode:
            return
        self.label = format_label.format(season=season, episode=episode, label=self.infolabels.get('title', ''))

    def set_unique_ids_to_infoproperties(self):
        for k, v in self.unique_ids.items():
            if not v:
                continue
            self.infoproperties['{}_id'.format(k)] = v

    def get_url(self):
        return utils.get_url(self.path, **self.params)

    def get_listitem(self):
        listitem = xbmcgui.ListItem(label=self.label, label2=self.label2, path=self.get_url())
        listitem.setLabel2(self.label2)
        listitem.setUniqueIDs(self.unique_ids)
        listitem.setInfo(self.library, self.infolabels)
        listitem.setProperties(self.infoproperties)
        listitem.setArt(self.set_art_fallbacks())
        listitem.setCast(self.cast)
        listitem.addContextMenuItems(self.context_menu)

        if self.stream_details:
            for k, v in self.stream_details.items():
                if not k or not v:
                    continue
                for i in v:
                    if not i:
                        continue
                    listitem.addStreamInfo(k, i)

        return listitem
