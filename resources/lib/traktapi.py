import xbmc
import xbmcgui
import resources.lib.utils as utils
from json import loads, dumps
from resources.lib.requestapi import RequestAPI
from resources.lib.plugin import ADDON
from resources.lib._trakt_methods import _TraktMethodsMixin
from resources.lib._trakt_sync import _TraktSyncMixin
from resources.lib._trakt_items import _TraktItemLists
from resources.lib._trakt_progress import _TraktProgressMixin


API_URL = 'https://api.trakt.tv/'
CLIENT_ID = 'e6fde6173adf3c6af8fd1b0694b9b84d7c519cefc24482310e1de06c6abe5467'
CLIENT_SECRET = '15119384341d9a61c751d8d515acbc0dd801001d4ebe85d3eef9885df80ee4d9'


class TraktAPI(RequestAPI, _TraktMethodsMixin, _TraktSyncMixin, _TraktItemLists, _TraktProgressMixin):
    def __init__(
            self,
            cache_short=ADDON.getSettingInt('cache_list_days'),
            cache_long=ADDON.getSettingInt('cache_details_days')):
        super(TraktAPI, self).__init__(
            cache_short=cache_short,
            cache_long=cache_long,
            req_api_url=API_URL,
            req_api_name='Trakt')
        self.authorization = ''
        self.attempted_login = False
        self.dialog_noapikey_header = u'{0} {1} {2}'.format(ADDON.getLocalizedString(32007), self.req_api_name, ADDON.getLocalizedString(32011))
        self.dialog_noapikey_text = ADDON.getLocalizedString(32012)
        self.client_id = CLIENT_ID
        self.client_secret = CLIENT_SECRET
        self.headers = {'trakt-api-version': '2', 'trakt-api-key': self.client_id, 'Content-Type': 'application/json'}
        self.last_activities = {}
        self.sync_activities = {}
        self.sync = {}
        self.authorize()

    def authorize(self, login=False):
        # Already got authorization so return credentials
        if self.authorization:
            return self.authorization

        # Get our saved credentials from previous login
        token = self.get_stored_token()
        if token.get('access_token'):
            self.authorization = token
            self.headers['Authorization'] = 'Bearer {0}'.format(self.authorization.get('access_token'))

        # No saved credentials and user trying to use a feature that requires authorization so ask them to login
        elif login:
            if not self.attempted_login and xbmcgui.Dialog().yesno(
                    self.dialog_noapikey_header,
                    self.dialog_noapikey_text,
                    nolabel=xbmc.getLocalizedString(222),
                    yeslabel=xbmc.getLocalizedString(186)):
                self.login()
            self.attempted_login = True

        # First time authorization in this session so let's confirm
        if self.authorization and xbmcgui.Window(10000).getProperty('TMDbHelper.TraktIsAuth') != 'True':
            # Check if we can get a response from user account
            utils.kodi_log('Checking Trakt authorization', 1)
            response = self.get_simple_api_request('https://api.trakt.tv/sync/last_activities', headers=self.headers)
            # 401 is unauthorized error code so let's try refreshing the token
            if response.status_code == 401:
                utils.kodi_log('Trakt unauthorized!', 1)
                self.authorization = self.refresh_token()
            # Authorization confirmed so let's set a window property for future reference in this session
            if self.authorization:
                utils.kodi_log('Trakt user account authorized', 1)
                xbmcgui.Window(10000).setProperty('TMDbHelper.TraktIsAuth', 'True')

        return self.authorization

    def get_stored_token(self):
        try:
            token = loads(ADDON.getSettingString('trakt_token')) or {}
        except Exception as exc:
            token = {}
            utils.kodi_log(exc, 1)
        return token

    def logout(self):
        token = self.get_stored_token()

        if not xbmcgui.Dialog().yesno(ADDON.getLocalizedString(32212), ADDON.getLocalizedString(32213)):
            return

        if token:
            response = self.get_api_request('https://api.trakt.tv/oauth/revoke', dictify=False, postdata={
                'token': token.get('access_token', ''),
                'client_id': self.client_id,
                'client_secret': self.client_secret})
            if response and response.status_code == 200:
                msg = ADDON.getLocalizedString(32216)
                ADDON.setSettingString('trakt_token', '')
            else:
                msg = ADDON.getLocalizedString(32215)
        else:
            msg = ADDON.getLocalizedString(32214)

        xbmcgui.Dialog().ok(ADDON.getLocalizedString(32212), msg)

    def login(self):
        self.code = self.get_api_request('https://api.trakt.tv/oauth/device/code', postdata={'client_id': self.client_id})
        if not self.code.get('user_code') or not self.code.get('device_code'):
            return  # TODO: DIALOG: Authentication Error
        self.progress = 0
        self.interval = self.code.get('interval', 5)
        self.expires_in = self.code.get('expires_in', 0)
        self.auth_dialog = xbmcgui.DialogProgress()
        self.auth_dialog.create(
            ADDON.getLocalizedString(32097),
            ADDON.getLocalizedString(32096),
            ADDON.getLocalizedString(32095) + ': [B]' + self.code.get('user_code') + '[/B]')
        self.poller()

    def refresh_token(self):
        utils.kodi_log('Attempting to refresh Trakt token', 1)
        if not self.authorization or not self.authorization.get('refresh_token'):
            utils.kodi_log('Trakt refresh token not found!', 1)
            return
        postdata = {
            'refresh_token': self.authorization.get('refresh_token'),
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
            'grant_type': 'refresh_token'}
        self.authorization = self.get_api_request('https://api.trakt.tv/oauth/token', postdata=postdata)
        if not self.authorization or not self.authorization.get('access_token'):
            utils.kodi_log('Failed to refresh Trakt token!', 1)
            return
        self.on_authenticated(auth_dialog=False)
        utils.kodi_log('Trakt token refreshed', 1)
        return self.authorization

    def poller(self):
        if not self.on_poll():
            self.on_aborted()
            return
        if self.expires_in <= self.progress:
            self.on_expired()
            return
        self.authorization = self.get_api_request('https://api.trakt.tv/oauth/device/token', postdata={'code': self.code.get('device_code'), 'client_id': self.client_id, 'client_secret': self.client_secret})
        if self.authorization:
            self.on_authenticated()
            return
        xbmc.Monitor().waitForAbort(self.interval)
        if xbmc.Monitor().abortRequested():
            return
        self.poller()

    def on_aborted(self):
        """Triggered when device authentication was aborted"""
        utils.kodi_log(u'Trakt authentication aborted!', 1)
        self.auth_dialog.close()

    def on_expired(self):
        """Triggered when the device authentication code has expired"""
        utils.kodi_log(u'Trakt authentication expired!', 1)
        self.auth_dialog.close()

    def on_authenticated(self, auth_dialog=True):
        """Triggered when device authentication has been completed"""
        utils.kodi_log(u'Trakt authenticated successfully!', 1)
        ADDON.setSettingString('trakt_token', dumps(self.authorization))
        self.headers['Authorization'] = 'Bearer {0}'.format(self.authorization.get('access_token'))
        if auth_dialog:
            self.auth_dialog.close()

    def on_poll(self):
        """Triggered before each poll"""
        if self.auth_dialog.iscanceled():
            self.auth_dialog.close()
            return False
        else:
            self.progress += self.interval
            progress = (self.progress * 100) / self.expires_in
            self.auth_dialog.update(int(progress))
            return True

    def get_response(self, *args, **kwargs):
        return self.get_api_request(self.get_request_url(*args, **kwargs), headers=self.headers)

    def get_response_json(self, *args, **kwargs):
        try:
            return self.get_api_request(self.get_request_url(*args, **kwargs), headers=self.headers).json()
        except ValueError:
            return {}
        except AttributeError:
            return {}
