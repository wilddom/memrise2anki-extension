import json, urllib, urllib2

def loadEmbedCode(url):
    serviceUrl = "http://noembed.com/embed"
    response = urllib2.urlopen(serviceUrl, urllib.urlencode({'url': url}))
    data = json.load(response)
    if "error" in data:
        return None
    return data.get("html")
