import xbmc
import datetime
import resources.lib.utils as utils
from threading import Thread
from resources.lib.plugin import ADDON


class CronJobMonitor(Thread):
    def __init__(self, update_hour=0):
        Thread.__init__(self)
        self.exit = False
        self.poll_time = 1800  # Poll every 30 mins since we don't need to get exact time for update
        self.update_hour = update_hour

    def run(self):
        xbmc.Monitor().waitForAbort(600)  # Wait 10 minutes before doing updates to give boot time
        self.next_time = datetime.datetime.combine(datetime.datetime.today(), datetime.time(utils.try_parse_int(self.update_hour)))  # Get today at hour
        self.last_time = xbmc.getInfoLabel('Skin.String(TMDbHelper.AutoUpdate.LastTime)')  # Get last update
        self.last_time = utils.convert_timestamp(self.last_time) if self.last_time else None
        if self.last_time and self.last_time > self.next_time:
            self.next_time += datetime.timedelta(hours=24)  # Already updated today so set for tomorrow

        while not xbmc.Monitor().abortRequested() and not self.exit and self.poll_time:
            if ADDON.getSettingBool('library_autoupdate'):
                if datetime.datetime.now() > self.next_time:  # Scheduled time has past so lets update
                    xbmc.executebuiltin('RunScript(plugin.video.themoviedb.helper,library_autoupdate)')
                    xbmc.executebuiltin('Skin.SetString(TMDbHelper.AutoUpdate.LastTime,{})'.format(datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")))
                    self.next_time += datetime.timedelta(hours=24)  # Set next update for tomorrow
            xbmc.Monitor().waitForAbort(self.poll_time)
