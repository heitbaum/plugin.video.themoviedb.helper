import xbmcgui
import requests
import xml.etree.ElementTree as ET
import resources.lib.helpers.cache as cache
from resources.lib.helpers.window import get_property
from resources.lib.helpers.plugin import kodi_log, ADDON
from resources.lib.helpers.parser import try_int
from resources.lib.helpers.timedate import get_timestamp, set_timestamp
from copy import copy


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


def translate_xml(request):
    if request:
        request = ET.fromstring(request.content)
        request = dictify(request)
    return request


class RequestAPI(object):
    def __init__(self, req_api_url=None, req_api_key=None, req_api_name=None, timeout=None):
        self.req_api_url = req_api_url or ''
        self.req_api_key = req_api_key or ''
        self.req_api_name = req_api_name or ''
        self.req_connect_err_prop = 'ConnectionError.{}'.format(self.req_api_name)
        self.req_connect_err = get_property(self.req_connect_err_prop, is_type=float) or 0
        self.headers = None
        self.timeout = timeout or 10

    def get_api_request_json(self, request=None, postdata=None, headers=None, is_xml=False):
        request = self.get_api_request(request=request, postdata=postdata, headers=headers)
        if is_xml:
            return translate_xml(request)
        if request:
            return request.json()
        return {}

    def get_simple_api_request(self, request=None, postdata=None, headers=None):
        try:
            if not postdata:
                return requests.get(request, headers=headers, timeout=self.timeout)
            return requests.post(request, data=postdata, headers=headers)
        except Exception as err:
            self.req_connect_err = set_timestamp()
            get_property(self.req_connect_err_prop, self.req_connect_err)
            kodi_log(u'ConnectionError: {}\nSuppressing retries for 1 minute'.format(err), 1)
            xbmcgui.Dialog().notification(
                ADDON.getLocalizedString(32308).format(self.req_api_name),
                ADDON.getLocalizedString(32307))

    def get_api_request(self, request=None, postdata=None, headers=None):
        """
        Make the request to the API by passing a url request string
        """
        # Connection error in last minute for this api so don't keep trying
        if get_timestamp(self.req_connect_err):
            return

        # Get response
        response = self.get_simple_api_request(request, postdata, headers)
        if not response:
            return

        # Some error checking
        if not response.status_code == requests.codes.ok and try_int(response.status_code) >= 400:  # Error Checking
            if response.status_code == 401:  # Invalid API Key
                kodi_log(u'HTTP Error Code: {0}\nRequest: {1}\nPostdata: {2}\nHeaders: {3}\nResponse: {4}'.format(response.status_code, request, postdata, headers, response), 1)
            elif response.status_code == 500:
                self.req_connect_err = set_timestamp()
                get_property(self.req_connect_err_prop, self.req_connect_err)
                kodi_log(u'HTTP Error Code: {0}\nRequest: {1}\nSuppressing retries for 1 minute'.format(response.status_code, request), 1)
                xbmcgui.Dialog().notification(
                    ADDON.getLocalizedString(32308).format(self.req_api_name),
                    ADDON.getLocalizedString(32307))
            elif try_int(response.status_code) > 400:  # Don't write 400 error to log
                kodi_log(u'HTTP Error Code: {0}\nRequest: {1}'.format(response.status_code, request), 1)
            return

        # Return our response
        return response

    def get_request_url(self, *args, **kwargs):
        """
        Creates a url request string:
        https://api.themoviedb.org/3/arg1/arg2?api_key=foo&kwparamkey=kwparamvalue
        """
        request = self.req_api_url
        for arg in args:
            if arg is not None:
                request = u'{}/{}'.format(request, arg)
        sep = '?' if '?' not in request else '&'
        request = u'{}{}{}'.format(request, sep, self.req_api_key) if self.req_api_key else request
        for key, value in sorted(kwargs.items()):
            if value is not None:  # Don't add nonetype kwargs
                sep = '?' if '?' not in request else ''
                request = u'{}{}&{}={}'.format(request, sep, key, value)
        return request

    def get_request_sc(self, *args, **kwargs):
        """ Get API request using the short cache """
        kwargs['cache_days'] = cache.CACHE_SHORT
        return self.get_request(*args, **kwargs)

    def get_request_lc(self, *args, **kwargs):
        """ Get API request using the long cache """
        kwargs['cache_days'] = cache.CACHE_LONG
        return self.get_request(*args, **kwargs)

    def get_request(self, *args, **kwargs):
        """ Get API request from cache (or online if no cached version) """
        cache_days = kwargs.pop('cache_days', 0)  # Number of days to cache retrieved object if not already in cache.
        cache_name = kwargs.pop('cache_name', '')  # Affix to standard cache name.
        cache_only = kwargs.pop('cache_only', False)  # Only retrieve object from cache.
        cache_force = kwargs.pop('cache_force', False)  # Force retrieved object to be saved in cache. Use int to specify cache_days for fallback object.
        cache_fallback = kwargs.pop('cache_fallback', False)  # Object to force cache if no object retrieved.
        cache_refresh = kwargs.pop('cache_refresh', False)  # Ignore cached timestamps and retrieve new object.
        cache_combine_name = kwargs.pop('cache_combine_name', False)  # Combine given cache_name with auto naming via args/kwargs
        headers = kwargs.pop('headers', None) or self.headers  # Optional override to default headers.
        postdata = kwargs.pop('postdata', None)  # Postdata if need to POST to a RESTful API.
        is_xml = kwargs.pop('is_xml', False)  # Response needs translating from XML to dict
        request_url = self.get_request_url(*args, **kwargs)
        return cache.use_cache(
            self.get_api_request_json, request_url,
            headers=headers,
            postdata=postdata,
            is_xml=is_xml,
            cache_refresh=cache_refresh,
            cache_days=cache_days,
            cache_name=cache_name,
            cache_only=cache_only,
            cache_force=cache_force,
            cache_fallback=cache_fallback,
            cache_combine_name=cache_combine_name)
