import xbmc
import resources.lib.helpers.window as window
from resources.lib.helper.parser import try_int


PREFIX_PATH = 'Path.'
PREFIX_LOCK = 'Locked'
PREFIX_QUERY = 'Query'
PREFIX_CURRENT = 'Path.Current'
PREFIX_POSITION = 'Position'
PREFIX_INSTANCE = 'Instance'
ID_VIDEOINFO = 12003


def _unlock_path():
    return window.get_property(PREFIX_LOCK, clear_property=True)


def _lock_path(condition):
    if not condition:
        return _unlock_path()
    return window.get_property(PREFIX_LOCK, set_property='True')


def _get_position():
    return try_int(window.get_property(PREFIX_POSITION))


def _set_properties(position=1, path=None):
    path = path or ''
    window.get_property(PREFIX_CURRENT, set_property=path)
    window.get_property('{}{}'.format(PREFIX_PATH, position), set_property=path)
    window.get_property(PREFIX_POSITION, set_property=str(position))
    return path


class WindowManager():
    def __init__(
            self, prevent_del=False, call_auto=None, call_id=None, call_path=None,
            call_update=None, **kwargs):
        self.prevent_del = prevent_del
        self.call_auto = try_int(call_auto)
        self.call_id = call_id
        self.call_path = call_path
        self.call_update = call_update

    def reset_props(self):
        self.position = 0
        self.added_path = None
        _unlock_path()
        window.get_property(PREFIX_CURRENT, clear_property=True)
        window.get_property(PREFIX_POSITION, clear_property=True)
        window.get_property('{}0'.format(PREFIX_PATH), clear_property=True)
        window.get_property('{}1'.format(PREFIX_PATH), clear_property=True)

    def call_window(self):
        xbmc.executebuiltin('Dialog.Close({})'.format(ID_VIDEOINFO))
        if self.call_id:
            xbmc.executebuiltin('ActivateWindow({})'.format(self.call_id))
        elif self.call_path:
            xbmc.executebuiltin('ActivateWindow(videos, {}, return)'.format(self.call_path))
        elif self.call_update:
            xbmc.executebuiltin('Container.Update({})'.format(self.call_update))

    def call_auto(self):
        # If call_auto not set then use old method
        if not self.call_auto:
            return self.call_window()

        # Check if already running
        # Window already open so must already be running let's exit since we added our paths
        if xbmc.getCondVisibility("Window.IsVisible({})".format(self.call_auto)):
            return

        # Window not open but instance set so let's reset everything
        # TODO: Kill old instances
        if window.get_property(PREFIX_INSTANCE):
            self.reset_props()
            window.get_property(PREFIX_INSTANCE, clear_property=True)
            return self.router()

        # Window not open and instance not set so let's start our service
        window.get_property(PREFIX_INSTANCE, set_property='True')
        self.call_service()

    def add_path(self, add_path, **kwargs):
        url = add_path or ''
        url = url.replace('info=play', 'info=details')
        url = url.replace('info=seasons', 'info=details')
        if 'extended=True' not in url:
            url = '{}&{}'.format(url, 'extended=True')
        if url == window.get_property(PREFIX_CURRENT):
            return  # Already added so let's quit as user probably clicked twice
        self.position = _get_position() + 1
        self.added_path = _set_properties(self.position, url)
        _lock_path(self.prevent_del)
        self.call_auto()
