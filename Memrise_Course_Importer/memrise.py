import urllib2, cookielib, urllib, httplib, urlparse, re, time, os.path, json, collections, itertools
import uuid
import BeautifulSoup

class Thing(object):
    def __init__(self, thingId, thingData):
        self.id = thingId
        self.data = thingData
        self.localAudioUrls = []
        self.localImageUrls = []
        
    @property
    def targetDefinitions(self):
        return self.data.getTargetDefinitions()
    
    @property
    def targetAlternatives(self):
        return self.data.getTargetAlternatives()
    
    @property
    def targetAlternativesHidden(self):
        return self.data.getTargetAlternativesHidden()
    
    @property
    def sourceDefinitions(self):
        return self.data.getSourceDefinitions()
    
    @property
    def sourceAlternatives(self):
        return self.data.getSourceAlternatives()
    
    @property
    def sourceAlternativesHidden(self):
        return self.data.getSourceAlternativesHidden()
    
    @property
    def audioUrls(self):
        if self.localAudioUrls:
            return self.localAudioUrls
        return self.data.getAudioUrls()
    
    @audioUrls.setter
    def audioUrls(self, urls):
        self.localAudioUrls = urls
    
    @property
    def imageUrls(self):
        if self.localImageUrls:
            return self.localImageUrls
        return self.data.getImageUrls()
    
    @imageUrls.setter
    def imageUrls(self, urls):
        self.localImageUrls = urls

class Level(object):
    def __init__(self, levelId):
        self.id = levelId
        self.index = 0
        self.title = ""
        self.things = []
        
    def __iter__(self):
        for thing in self.things:
            yield thing
                
    def __len__(self):
        return len(self.things)

class Course(object):
    def __init__(self, courseId):
        self.id = courseId
        self.title = ""
        self.description = ""
        self.source = ""
        self.target = ""
        self.levels = []

    def __iter__(self):
        for level in self.levels:
            yield level
                
    def __len__(self):
        return len(self.levels)

class ColumnDefinition(object):
    def __init__(self, columnData):
        self.text = []
        self.audio = []
        self.image = []
        
        for index, column in columnData.items():
            col = {'index': index, 'label': column['label']}
            if (column['kind'] == 'text'):
                self.text.append(col)
            elif (column['kind'] == 'audio'):
                self.audio.append(col)
            elif (column['kind'] == 'image'):
                self.image.append(col)

class ColumnData(object):
    def __init__(self, columnDefinition, thingData, fixUrl=lambda url: url):
        self.columns = columnDefinition
        self.textData = collections.OrderedDict()
        self.audioUrls = collections.OrderedDict()
        self.imageUrls = collections.OrderedDict()
        
        for column in self.columns.text:
            row = thingData['columns'][column['index']]
            data = {'value': self.__getDefinitionFromRow(row),
                    'alternatives': self.__getAlternativesFromRow(row),
                    'typing_corrects': self.__getTypingCorrectsFromRow(row)}
            self.textData[column['label']] = data
        
        for column in self.columns.audio:
            row = thingData['columns'][column['index']]
            self.audioUrls[column['label']] = map(fixUrl, self.__getUrlsFromRow(row))
            
        for column in self.columns.image:
            row = thingData['columns'][column['index']]
            self.imageUrls[column['label']] = map(fixUrl, self.__getUrlsFromRow(row))
            
    @staticmethod
    def __getDefinitionFromRow(row):
        return row["val"]
    
    @staticmethod
    def __getAlternativesFromRow(row):
        data = []
        for alt in row["alts"]:
            value = alt['val']
            if value:
                data.append(value)
        return data
    
    @staticmethod
    def __getTypingCorrectsFromRow(row):
        data = []
        for _, typing_corrects in row["typing_corrects"].items():
            for value in typing_corrects:
                if value:
                    data.append(value)
        return data
    
    @staticmethod
    def __getUrlsFromRow(row):
        data = []
        for value in row["val"]:
            url = value["url"]
            if url:
                data.append(url)
        return data
    
    def __getTextAttribute(self, attr, start=None, stop=None):
        return map(lambda x: x[attr], itertools.islice(self.textData.itervalues(), start, stop))
    
    def __getAlternatives(self, filterfunc, start=None, stop=None):
        alternatives = filter(filterfunc, itertools.chain.from_iterable(self.__getTextAttribute('alternatives', start, stop)))
        typing_corrects = itertools.chain.from_iterable(self.__getTextAttribute('typing_corrects', start, stop))
        alternatives.extend(typing_corrects)
        return alternatives

    def getTargetDefinitions(self):
        return self.__getTextAttribute('value', 0, 1)

    def getTargetAlternatives(self):
        return self.__getAlternatives(lambda x: not x.startswith(u"_"), 0, 1)
    
    def getTargetAlternativesHidden(self):
        return self.__getAlternatives(lambda x: x.startswith(u"_"), 0, 1)

    def getSourceDefinitions(self):
        return self.__getTextAttribute('value', 1)

    def getSourceAlternatives(self):
        return self.__getAlternatives(lambda x: not x.startswith(u"_"), 1)
    
    def getSourceAlternativesHidden(self):
        return self.__getAlternatives(lambda x: x.startswith(u"_"), 1)
    
    @staticmethod
    def __getKeyFromIndex(keys, index):
        if not isinstance(index, int):
            return index
        return keys[index]
    
    def getAudioUrls(self, name=None):
        name = self.__getKeyFromIndex(self.getAudioColumnNames(), name)
        if name:
            return self.audioUrls[name]
        return list(itertools.chain.from_iterable(self.audioUrls.values()))

    def getImageUrls(self, name=None):
        name = self.__getKeyFromIndex(self.getImageColumnNames(), name)
        if name:
            return self.imageUrls[name]
        return list(itertools.chain.from_iterable(self.imageUrls.values()))
    
    def getImageColumnNames(self):
        return self.imageUrls.keys()
    
    def getAudioColumnNames(self):
        return self.audioUrls.keys()
    
    def getTextColumnNames(self):
        return self.textData.keys()
    
    def getDefinition(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return self.textData[name]['value']
    
    def getAlternatives(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return filter(lambda x: not x.startswith(u"_"), self.textData[name]['alternatives'])
    
    def getAlternativesHidden(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return filter(lambda x: x.startswith(u"_"), self.textData[name]['alternatives'])
    
    def getTypingCorrects(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return self.textData[name]['typing_corrects']

class CourseLoader(object):
    def __init__(self, service):
        self.service = service
        self.observers = []
        self.levelCount = 0
        self.thingCount = 0
    
    def registerObserver(self, observer):
        self.observers.append(observer)
        
    def notify(self, signal, *attrs, **kwargs):
        for observer in self.observers:
            if hasattr(observer, signal):
                getattr(observer, signal)(*attrs, **kwargs)
        
    def loadCourse(self, courseId):
        self.course = Course(courseId)
        
        levelUrl = self.service.getJsonLevelUrl(self.course.id, 1)
        response = self.service.downloadWithRetry(levelUrl, 3)
        levelData = json.load(response)
        
        self.course.title = levelData["session"]["course"]["name"]
        self.course.description = levelData["session"]["course"]["description"]
        self.course.source = levelData["session"]["course"]["source"]["name"]
        self.course.target = levelData["session"]["course"]["target"]["name"]
        self.levelCount = levelData["session"]["course"]["num_levels"]
        self.thingCount = levelData["session"]["course"]["num_things"]
        
        self.notify('levelCountChanged', self.levelCount)
        self.notify('thingCountChanged', self.thingCount)
        
        for levelIndex in range(1,self.levelCount+1):
            level = self.loadLevel(levelIndex)
            if level:
                self.course.levels.append(level)
            self.notify('levelLoaded', levelIndex, level)
        
        return self.course
    
    def loadLevel(self, levelIndex):
        levelUrl = self.service.getJsonLevelUrl(self.course.id, levelIndex)
        response = self.service.downloadWithRetry(levelUrl, 3)
        levelData = json.load(response)
        
        if levelData["success"] == False:
            return None
        
        level = Level(levelData["session"]["level"]["id"])
        level.index = levelData["session"]["level"]["index"]
        level.title = levelData["session"]["level"]["title"]
        poolId = levelData["session"]["level"]["pool_id"]
        
        columnData = levelData["pools"][unicode(poolId)]["columns"]
        columnDefinitions = ColumnDefinition(columnData)
        
        for thingId, thingData in levelData["things"].items():
            thingData = ColumnData(columnDefinitions, thingData, self.service.toAbsoluteMediaUrl)
            thing = Thing(thingId, thingData)
            level.things.append(thing)
            self.notify('thingLoaded', thing)
        
        return level

class Service(object):
    def __init__(self, downloadDirectory=None, cookiejar=None):
        self.downloadDirectory = downloadDirectory
        if cookiejar is None:
            cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar))
    
    def downloadWithRetry(self, url, tryCount):
        try:
            return self.opener.open(url)
        except httplib.BadStatusLine:
            # not clear why this error occurs (seemingly randomly),
            # so I regret that all we can do is wait and retry.
            if tryCount > 0:
                time.sleep(0.1)
                return self.downloadWithRetry(url, tryCount-1)
            else:
                raise
    
    def isLoggedIn(self):
        response = self.opener.open('http://www.memrise.com/login/')
        return response.geturl() == 'http://www.memrise.com/home/'
        
    def login(self, username, password):
        response = self.opener.open('http://www.memrise.com/login/')
        soup = BeautifulSoup.BeautifulSoup(response.read())
        form = soup.find("form", attrs={"action": '/login/'})
        fields = {}
        for field in form.findAll("input"):
            if field.has_key('name'):
                if field.has_key('value'):
                    fields[field['name']] = field['value']
                else:
                    fields[field['name']] = ""
        fields['username'] = username
        fields['password'] = password
        response = self.opener.open('http://www.memrise.com/login/', urllib.urlencode(fields))
        return response.geturl() == 'http://www.memrise.com/home/'
    
    def loadCourse(self, url, observer=None):
        courseLoader = CourseLoader(self)
        if not observer is None:
            courseLoader.registerObserver(observer)
        return courseLoader.loadCourse(self.getCourseIdFromUrl(url))
    
    @staticmethod
    def getCourseIdFromUrl(url):
        match = re.match('http://www.memrise.com/course/(\d+)/.+/', url)
        if not match:
            raise Exception("Import failed. Does your URL look like the sample URL above?")
        return int(match.group(1))

    @staticmethod
    def getHtmlLevelUrl(courseUrl, levelNum):
        if not re.match('http://www.memrise.com/course/\d+/.+/', courseUrl):
            raise Exception("Import failed. Does your URL look like the sample URL above?")
        return u"{:s}{:d}".format(courseUrl, levelNum)
    
    @staticmethod
    def getJsonLevelUrl(courseId, levelIndex):
        return u"http://www.memrise.com/ajax/session/?course_id={:d}&level_index={:d}&session_slug=preview".format(courseId, levelIndex)
    
    @staticmethod
    def toAbsoluteMediaUrl(url):
        return urlparse.urljoin(u"http://static.memrise.com/", url)
    
    def downloadMedia(self, url):
        if not self.downloadDirectory:
            return url
        
        # Replace links to images and audio on the Memrise servers
        # by downloading the content to the user's media dir
        memrisePath = urlparse.urlparse(url).path
        contentExtension = os.path.splitext(memrisePath)[1]
        localName = "{:s}{:s}".format(uuid.uuid5(uuid.NAMESPACE_URL, url.encode('utf-8')), contentExtension)
        fullMediaPath = os.path.join(self.downloadDirectory, localName)
        mediaFile = open(fullMediaPath, "wb")
        mediaFile.write(self.downloadWithRetry(url, 3).read())
        mediaFile.close()
        return localName

