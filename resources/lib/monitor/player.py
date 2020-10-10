import xbmc
import resources.lib.helpers.rpc as rpc
from resources.lib.monitor.common import CommonMonitorFunctions
from resources.lib.helpers.parser import try_int, try_decode


class PlayerMonitor(xbmc.Player, CommonMonitorFunctions):
    def __init__(self):
        xbmc.Player.__init__(self)
        CommonMonitorFunctions.__init__(self)
        self.exit = False

    # def onAVStarted(self):
    #     self.reset_properties()
    #     self.get_playingitem()

    # def onPlayBackEnded(self):
    #     self.set_watched()
    #     self.reset_properties()

    # def onPlayBackStopped(self):
    #     self.set_watched()
    #     self.reset_properties()

    # def get_dbid(self):
    #     self.kodi_db = rpc.KodiLibrary(dbtype='movie').get_info(info='dbid', **self.playerstring)
    #     if not dbid:
    #         return

    def set_watched(self):
        if not self.dbid or not self.playerstring or not self.playerstring.get('tmdb_id'):
            return
        if not self.current_time or not self.total_time:
            return
        if '{}'.format(self.playerstring.get('tmdb_id')) != '{}'.format(self.details.get('tmdb_id')):
            return  # Item in the player doesn't match so don't mark as watched

        # Only update if progress is 75% or more
        progress = ((self.current_time / self.total_time) * 100)
        if progress < 75:
            return

        if self.playerstring.get('tmdb_type') == 'episode':
            rpc.set_watched(dbid=self.dbid, dbtype='episode')
        elif self.playerstring.get('tmdb_type') == 'movie':
            rpc.set_watched(dbid=self.dbid, dbtype='movie')
