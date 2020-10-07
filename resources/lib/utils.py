import re
import os
import sys
import xbmc
import time
import json
import xbmcgui
import hashlib
import xbmcvfs
import datetime
import unicodedata
from copy import copy
from timeit import default_timer as timer
from resources.lib.plugin import ADDON, PLUGINPATH, ADDONDATA
from resources.lib.constants import VALID_FILECHARS
from contextlib import contextmanager
try:
    from urllib.parse import urlencode, unquote_plus  # Py3
except ImportError:
    from urllib import urlencode, unquote_plus
try:
    import cPickle as _pickle
except ImportError:
    import pickle as _pickle  # Newer versions of Py3 just use pickle
if sys.version_info[0] >= 3:
    unicode = str  # In Py3 str is now unicode

_addonlogname = '[plugin.video.themoviedb.helper]\n'
_debuglogging = ADDON.getSettingBool('debug_logging')


def format_name(cache_name, *args, **kwargs):
    # Define a type whitelist to avoiding adding non-basic types like classes to cache name
    permitted_types = [unicode, int, float, str, bool]
    for arg in args:
        if not arg or type(arg) not in permitted_types:
            continue
        cache_name = u'{0}/{1}'.format(cache_name, arg) if cache_name else u'{}'.format(arg)
    for key, value in kwargs.items():
        if not value or type(value) not in permitted_types:
            continue
        cache_name = u'{0}&{1}={2}'.format(cache_name, key, value) if cache_name else u'{0}={1}'.format(key, value)
    return cache_name


def timer_report(func_name):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            """ Syntactic sugar to time a class function """
            timer_a = timer()
            response = func(self, *args, **kwargs)
            timer_z = timer()
            total_time = timer_z - timer_a
            if total_time > 0.001:
                timer_name = '{}.{}.'.format(self.__class__.__name__, func_name)
                timer_name = format_name(timer_name, *args, **kwargs)
                kodi_log('{}\n{:.3f} sec'.format(timer_name, total_time), 1)
            return response
        return wrapper
    return decorator


def log_output(func_name):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            """ Syntactic sugar to log output of function """
            response = func(self, *args, **kwargs)
            log_text = '{}.{}.'.format(self.__class__.__name__, func_name)
            log_text = format_name(log_text, *args, **kwargs)
            kodi_log(log_text, 1)
            kodi_log(response, 1)
            return response
        return wrapper
    return decorator


def md5hash(value):
    if sys.version_info.major != 3:
        return hashlib.md5(str(value)).hexdigest()

    value = str(value).encode()
    return hashlib.md5(value).hexdigest()


@contextmanager
def busy_dialog(is_enabled=True):
    if is_enabled:
        xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
    try:
        yield
    finally:
        if is_enabled:
            xbmc.executebuiltin('Dialog.Close(busydialognocancel)')


def kodi_log(value, level=0):
    try:
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        logvalue = u'{0}{1}'.format(_addonlogname, value)
        if sys.version_info < (3, 0):
            logvalue = logvalue.encode('utf-8', 'ignore')
        if level == 2 and _debuglogging:
            xbmc.log(logvalue, level=xbmc.LOGNOTICE)
        elif level == 1:
            xbmc.log(logvalue, level=xbmc.LOGNOTICE)
        else:
            xbmc.log(logvalue, level=xbmc.LOGDEBUG)
    except Exception as exc:
        xbmc.log(u'Logging Error: {}'.format(exc), level=xbmc.LOGNOTICE)


def try_parse_int(string, base=None, fallback=0):
    '''helper to parse int from string without erroring on empty or misformed string'''
    try:
        return int(string, base) if base else int(string)
    except Exception:
        return fallback


def try_parse_float(string):
    '''helper to parse float from string without erroring on empty or misformed string'''
    try:
        return float(string or 0)
    except Exception:
        return 0


def try_decode_string(string, encoding='utf-8', errors=None):
    """helper to decode strings for PY 2 """
    if sys.version_info.major == 3:
        return string
    try:
        return string.decode(encoding, errors) if errors else string.decode(encoding)
    except Exception:
        return string


def try_encode_string(string, encoding='utf-8'):
    """helper to encode strings for PY 2 """
    if sys.version_info.major == 3:
        return string
    try:
        return string.encode(encoding)
    except Exception:
        return string


def parse_paramstring(paramstring):
    """ helper to assist with difference in urllib modules in PY2/3 """
    params = dict()
    paramstring = paramstring.replace('&amp;', '&')  # Just in case xml string
    for param in paramstring.split('&'):
        if '=' not in param:
            continue
        k, v = param.split('=')
        params[try_decode_string(unquote_plus(k))] = try_decode_string(unquote_plus(v))
    return params


def urlencode_params(*args, **kwargs):
    """ helper to assist with difference in urllib modules in PY2/3 """
    params = dict()
    for k, v in kwargs.items():
        params[try_encode_string(k)] = try_encode_string(v)
    return urlencode(params)


def get_timestamp(timestamp=None):
    if not timestamp:
        return
    if time.time() > timestamp:
        return
    return timestamp


def set_timestamp(wait_time=60):
    return time.time() + wait_time


def validify_filename(filename):
    try:
        filename = unicode(filename, 'utf-8')
    except NameError:  # unicode is a default on python 3
        pass
    except TypeError:  # already unicode
        pass
    filename = str(unicodedata.normalize('NFD', filename).encode('ascii', 'ignore').decode("utf-8"))
    filename = ''.join(c for c in filename if c in VALID_FILECHARS)
    filename = filename[:-1] if filename.endswith('.') else filename
    return filename


def dictify(r, root=True):
    if root:
        return {r.tag: dictify(r, False)}
    d = copy(r.attrib)
    if r.text:
        d["_text"] = r.text
    for x in r.findall("./*"):
        if x.tag not in d:
            d[x.tag] = []
        d[x.tag].append(dictify(x, False))
    return d


def dict_to_list(items, key):
    return [i.get(key) for i in items if i.get(key)]


def merge_two_dicts(x, y, reverse=False):
    xx = y or {} if reverse else x or {}
    yy = x or {} if reverse else y or {}
    z = xx.copy()   # start with x's keys and values
    z.update(yy)    # modifies z with y's keys and values & returns None
    return z


def merge_two_dicts_deep(x, y, reverse=False):
    """ Deep merge y keys into copy of x """
    xx = y or {} if reverse else x or {}
    yy = x or {} if reverse else y or {}
    z = xx.copy()
    for k, v in yy.items():
        if isinstance(v, dict):
            merge_two_dicts_deep(z.setdefault(k, {}), v, reverse=reverse)
        elif v:
            z[k] = v
    return z


def merge_two_items(base_item, item):
    item = item or {}
    base_item = base_item or {}
    item['stream_details'] = merge_two_dicts(base_item.get('stream_details', {}), item.get('stream_details', {}))
    item['params'] = merge_two_dicts(base_item.get('params', {}), item.get('params', {}))
    item['infolabels'] = merge_two_dicts(base_item.get('infolabels', {}), item.get('infolabels', {}))
    item['infoproperties'] = merge_two_dicts(base_item.get('infoproperties', {}), item.get('infoproperties', {}))
    item['art'] = merge_two_dicts(base_item.get('art', {}), item.get('art', {}))
    item['unique_ids'] = merge_two_dicts(base_item.get('unique_ids', {}), item.get('unique_ids', {}))
    item['cast'] = item.get('cast') or base_item.get('cast') or []
    return item


def del_empty_keys(d, values=[]):
    values += [None, '']
    return {k: v for k, v in d.items() if v not in values}


def find_dict_in_list(list_of_dicts, key, value):
    return [list_index for list_index, dic in enumerate(list_of_dicts) if dic.get(key) == value]


def iter_props(items, property_name, infoproperties=None, func=None, **kwargs):
    infoproperties = infoproperties or {}
    if not items or not isinstance(items, list):
        return infoproperties
    for x, i in enumerate(items, start=1):
        for k, v in kwargs.items():
            infoproperties['{}.{}.{}'.format(property_name, x, k)] = func(i.get(v)) if func else i.get(v)
        if x >= 10:
            break
    return infoproperties


def date_to_format(time_str, str_fmt="%A", time_fmt="%Y-%m-%d", time_lim=10, utc_convert=False):
    if not time_str:
        return
    time_obj = convert_timestamp(time_str, time_fmt, time_lim, utc_convert=utc_convert)
    if not time_obj:
        return
    return time_obj.strftime(str_fmt)


def date_in_range(date_str, days=1, start_date=0, date_fmt="%Y-%m-%dT%H:%M:%S", date_lim=19, utc_convert=False):
    date_a = datetime.date.today() + datetime.timedelta(days=start_date)
    date_z = date_a + datetime.timedelta(days=days)
    mydate = convert_timestamp(date_str, date_fmt, date_lim, utc_convert=utc_convert).date()
    if not mydate or not date_a or not date_z:
        return
    if mydate >= date_a and mydate < date_z:
        return date_str


def get_region_date(date_obj, region='dateshort', del_fmt=':%S'):
    date_fmt = xbmc.getRegion(region).replace(del_fmt, '')
    return date_obj.strftime(date_fmt)


def is_future_timestamp(time_str, time_fmt="%Y-%m-%dT%H:%M:%S", time_lim=19, utc_convert=False):
    time_obj = convert_timestamp(time_str, time_fmt, time_lim, utc_convert)
    if not isinstance(time_obj, datetime.datetime):
        return
    if time_obj > datetime.datetime.now():
        return time_str


def convert_timestamp(time_str, time_fmt="%Y-%m-%dT%H:%M:%S", time_lim=19, utc_convert=False):
    if not time_str:
        return
    time_str = time_str[:time_lim] if time_lim else time_str
    utc_offset = 0
    if utc_convert:
        utc_offset = -time.timezone // 3600
        utc_offset += 1 if time.localtime().tm_isdst > 0 else 0
    try:
        time_obj = datetime.datetime.strptime(time_str, time_fmt)
        time_obj = time_obj + datetime.timedelta(hours=utc_offset)
        return time_obj
    except TypeError:
        try:
            time_obj = datetime.datetime(*(time.strptime(time_str, time_fmt)[0:6]))
            time_obj = time_obj + datetime.timedelta(hours=utc_offset)
            return time_obj
        except Exception as exc:
            kodi_log(exc, 1)
            return
    except Exception as exc:
        kodi_log(exc, 1)
        return


def age_difference(birthday, deathday=''):
    try:  # Added Error Checking as strptime doesn't work correctly on LibreElec
        deathday = convert_timestamp(deathday, '%Y-%m-%d', 10) if deathday else datetime.datetime.now()
        birthday = convert_timestamp(birthday, '%Y-%m-%d', 10)
        age = deathday.year - birthday.year
        if birthday.month * 100 + birthday.day > deathday.month * 100 + deathday.day:
            age = age - 1
        return age
    except Exception:
        return


def get_url(path, **kwargs):
    path = path or PLUGINPATH
    paramstring = '?{}'.format(urlencode_params(**kwargs)) if kwargs else ''
    return '{}{}'.format(path, paramstring)


def get_files_in_folder(folder, regex):
    return [x for x in xbmcvfs.listdir(folder)[1] if re.match(regex, x)]


def read_file(filepath):
    vfs_file = xbmcvfs.File(filepath)
    content = ''
    try:
        content = vfs_file.read()
    finally:
        vfs_file.close()
    return content


def dumps_to_file(data, folder, filename, indent=2):
    with open(os.path.join(_get_write_path(folder), filename), 'w') as file:
        json.dump(data, file, indent=indent)


def _get_write_path(folder):
    main_dir = os.path.join(xbmc.translatePath(ADDONDATA), folder)
    if not os.path.exists(main_dir):
        os.makedirs(main_dir)
    return main_dir


def makepath(path):
    if xbmcvfs.exists(path):
        return xbmc.translatePath(path)
    if xbmcvfs.mkdirs(path):
        return xbmc.translatePath(path)
    if ADDON.getSettingBool('ignore_folderchecking'):
        kodi_log(u'Ignored xbmcvfs folder check error\n{}'.format(path), 2)
        return xbmc.translatePath(path)


def _get_pickle_name(cache_name):
    cache_name = cache_name or ''
    cache_name = cache_name.replace('\\', '_').replace('/', '_').replace('.', '_').replace('?', '_').replace('&', '_').replace('=', '_').replace('__', '_')
    return validify_filename(cache_name)


def set_pickle(my_object, cache_name, cache_days=14):
    if not my_object:
        return
    cache_name = _get_pickle_name(cache_name)
    if not cache_name:
        return
    timestamp = datetime.datetime.now() + datetime.timedelta(days=cache_days)
    cache_obj = {'my_object': my_object, 'expires': timestamp.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(_get_write_path('pickle'), cache_name), 'wb') as file:
        _pickle.dump(cache_obj, file)
    return my_object


def get_pickle(cache_name):
    cache_name = _get_pickle_name(cache_name)
    if not cache_name:
        return
    try:
        with open(os.path.join(_get_write_path('pickle'), cache_name), 'rb') as file:
            cache_obj = _pickle.load(file)
    except IOError:
        cache_obj = None
    if cache_obj and is_future_timestamp(cache_obj.get('expires', '')):
        return cache_obj.get('my_object')


def use_pickle(func, *args, **kwargs):
    """
    Simplecache takes func with args and kwargs
    Returns the cached item if it exists otherwise does the function
    """
    cache_name = kwargs.pop('cache_name', '')
    cache_only = kwargs.pop('cache_only', False)
    cache_refresh = kwargs.pop('cache_refresh', False)
    my_object = get_pickle(cache_name) if not cache_refresh else None
    if my_object:
        return my_object
    elif not cache_only:
        my_object = func(*args, **kwargs)
        return set_pickle(my_object, cache_name)


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
        return try_parse_int(window.getProperty(name))
    if is_type == float:
        return try_parse_float(window.getProperty(name))
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


def split_items(items, separator='/'):
    separator = ' {} '.format(separator)
    if items and separator in items:
        items = items.split(separator)
    items = [items] if not isinstance(items, list) else items  # Make sure we return a list to prevent a string being iterated over characters
    return items


def filtered_item(item, key, value, exclude=False):
    boolean = False if exclude else True  # Flip values if we want to exclude instead of include
    if key and value and item.get(key) == value:
        boolean = exclude
    return boolean


def get_params(item, tmdb_type, tmdb_id=None, params=None, definition=None, base_tmdb_type=None):
    params = params or {}
    tmdb_id = tmdb_id or item.get('id')
    definition = definition or {'info': 'details', 'tmdb_type': '{tmdb_type}', 'tmdb_id': '{tmdb_id}'}
    for k, v in definition.items():
        params[k] = v.format(tmdb_type=tmdb_type, tmdb_id=tmdb_id, base_tmdb_type=base_tmdb_type, **item)
    return del_empty_keys(params)


def get_between_strings(string, startswith='', endswith=''):
    exp = startswith + '(.+?)' + endswith
    try:
        return re.search(exp, string).group(1)
    except AttributeError:
        return ''
