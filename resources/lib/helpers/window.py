import xbmc
import xbmcgui
from resources.lib.helpers.parser import try_int, try_float


def get_property(name, set_property=None, clear_property=False, window_id=None, prefix=None, is_type=None):
    prefix = prefix or 'TMDbHelper'
    name = '{}.{}'.format(prefix, name)
    if window_id == 'current':
        window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    elif window_id:
        window = xbmcgui.Window(window_id)
    else:
        window = xbmcgui.Window(10000)
    if clear_property:
        window.clearProperty(name)
        return
    elif set_property:
        window.setProperty(name, u'{}'.format(set_property))
        return set_property
    if is_type == int:
        return try_int(window.getProperty(name))
    if is_type == float:
        return try_float(window.getProperty(name))
    return window.getProperty(name)


def _property_is_value(name, value):
    if not value and not get_property(name):
        return True
    if value and get_property(name) == value:
        return True
    return False


def wait_for_property(name, value=None, set_property=False, poll=1, timeout=10):
    """
    Waits until property matches value. None value waits for property to be cleared.
    Will set property to value if set_property flag is set. None value clears property.
    Returns True when successful.
    """
    if set_property:
        get_property(name, value) if value else get_property(name, clear_property=True)
    is_property = _property_is_value(name, value)
    while not xbmc.Monitor().abortRequested() and timeout > 0 and not is_property:
        xbmc.Monitor().waitForAbort(poll)
        is_property = _property_is_value(name, value)
        timeout -= poll
    return is_property
