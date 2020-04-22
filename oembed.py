import json, urllib.request, urllib.parse
from urllib.error import URLError, HTTPError
import sys

def loadEmbedCode(url):
    serviceUrl = "http://noembed.com/embed"
    getdata = urllib.parse.urlencode({'url': url})
    fullUrl = serviceUrl + "?" + getdata
    try:
        response = urllib.request.urlopen(fullUrl)
    except URLError as e:
        print("oembed URLError", fullUrl, file=sys.stderr)
        return None
    except HTTPError as e:
        print("oembed HTTPError", fullUrl, file=sys.stderr)
        return None
    data = json.load(response)
    if "error" in data:
        return None
    return data.get("html")
