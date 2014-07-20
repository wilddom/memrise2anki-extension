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
    def sourceDefinitions(self):
        return self.data.getSourceDefinitions()
    
    @property
    def sourceAlternatives(self):
        return self.data.getSourceAlternatives()

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

    @property
    def attributes(self):
        return self.data.getAttributes()

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

class ThingDataLoader(object):
    def __init__(self, poolData):
        self.textColumns = []
        self.audioColumns = []
        self.imageColumns = []
        self.attributes = []
        
        for index, column in sorted(poolData["columns"].items()):
            col = {'index': index, 'label': column['label']}
            if (column['kind'] == 'text'):
                self.textColumns.append(col)
            elif (column['kind'] == 'audio'):
                self.audioColumns.append(col)
            elif (column['kind'] == 'image'):
                self.imageColumns.append(col)

        for index, attribute in sorted(poolData["attributes"].items()):
            attr = {'index': index, 'label': attribute['label']}
            if (attribute['kind'] == 'text'):
                self.attributes.append(attr)

    def load(self, row, fixUrl=lambda url: url):
        thingData = ThingData()
        
        for column in self.textColumns:
            cell = row['columns'][column['index']]
            data = {'value': self.__getDefinition(cell),
                    'alternatives': self.__getAlternatives(cell),
                    'typing_corrects': self.__getTypingCorrects(cell)}
            thingData.textData[column['label']] = data
        
        for column in self.audioColumns:
            cell = row['columns'][column['index']]
            thingData.audioUrls[column['label']] = map(fixUrl, self.__getUrls(cell))
            
        for column in self.imageColumns:
            cell = row['columns'][column['index']]
            thingData.imageUrls[column['label']] = map(fixUrl, self.__getUrls(cell))

        for attribute in self.attributes:
            cell = row['attributes'][attribute['index']]
            thingData.attributes[attribute['label']] = self.__getAttribute(cell)

        return thingData

    @staticmethod
    def __getDefinition(cell):
        return cell["val"]
    
    @staticmethod
    def __getAlternatives(cell):
        data = []
        for alt in cell["alts"]:
            value = alt['val']
            if value:
                data.append(value)
        return data
    
    @staticmethod
    def __getTypingCorrects(cell):
        data = []
        for _, typing_corrects in cell["typing_corrects"].items():
            for value in typing_corrects:
                if value:
                    data.append(value)
        return data
    
    @staticmethod
    def __getUrls(cell):
        data = []
        for value in cell["val"]:
            url = value["url"]
            if url:
                data.append(url)
        return data

    @staticmethod
    def __getAttribute(cell):
        return cell["val"]

class ThingData(object):
    def __init__(self):
        self.textData = collections.OrderedDict()
        self.audioUrls = collections.OrderedDict()
        self.imageUrls = collections.OrderedDict()
        self.attributes = collections.OrderedDict()
    
    def __getTextData(self, attr, start=None, stop=None):
        return map(lambda x: x[attr], itertools.islice(self.textData.itervalues(), start, stop))
    
    def __getAlternatives(self, filterfunc, start=None, stop=None):
        alternatives = filter(filterfunc, itertools.chain.from_iterable(self.__getTextData('alternatives', start, stop)))
        typing_corrects = itertools.chain.from_iterable(self.__getTextData('typing_corrects', start, stop))
        alternatives.extend(typing_corrects)
        return alternatives

    def getTargetDefinitions(self):
        return self.__getTextData('value', 0, 1)

    def getTargetAlternatives(self):
        return self.__getAlternatives(lambda x: not x.startswith(u"_"), 0, 1)
    
    def getSourceDefinitions(self):
        return self.__getTextData('value', 1)

    def getSourceAlternatives(self):
        return self.__getAlternatives(lambda x: not x.startswith(u"_"), 1)
    
    def getAttributes(self):
        return filter(bool, self.attributes.values())

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

    def getAttributeNames(self):
        return self.attributes.keys()

    def getDefinition(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return self.textData[name]['value']
    
    def getAlternatives(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return filter(lambda x: not x.startswith(u"_"), self.textData[name]['alternatives'])
    
    def getAlternativesHidden(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return map(lambda x: x.lstrip(u'_'), filter(lambda x: x.startswith(u"_"), self.textData[name]['alternatives']))
    
    def getTypingCorrects(self, name):
        name = self.__getKeyFromIndex(self.getTextColumnNames(), name)
        return self.textData[name]['typing_corrects']

    def getAttribute(self, name):
        name = self.__getKeyFromIndex(self.getAttributeNames(), name)
        return self.attributes[name]

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
        course = Course(courseId)
        
        levelData = self.service.loadLevelData(course.id, 1)
        
        course.title = levelData["session"]["course"]["name"]
        course.description = levelData["session"]["course"]["description"]
        course.source = levelData["session"]["course"]["source"]["name"]
        course.target = levelData["session"]["course"]["target"]["name"]
        self.levelCount = levelData["session"]["course"]["num_levels"]
        self.thingCount = levelData["session"]["course"]["num_things"]
        
        self.notify('levelCountChanged', self.levelCount)
        self.notify('thingCountChanged', self.thingCount)
        
        for levelIndex in range(1,self.levelCount+1):
            level = self.loadLevel(course, levelIndex)
            if level:
                course.levels.append(level)
            self.notify('levelLoaded', levelIndex, level)
        
        return course
    
    def loadLevel(self, course, levelIndex):
        levelData = self.service.loadLevelData(course.id, levelIndex)
        
        if levelData["success"] == False:
            return None
        
        level = Level(levelData["session"]["level"]["id"])
        level.index = levelData["session"]["level"]["index"]
        level.title = levelData["session"]["level"]["title"]
        poolId = levelData["session"]["level"]["pool_id"]
        
        poolData = levelData["pools"][unicode(poolId)]
        thingDataLoader = ThingDataLoader(poolData)
        
        for thingId, thingRowData in levelData["things"].items():
            thingData = thingDataLoader.load(thingRowData, self.service.toAbsoluteMediaUrl)
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
    
    def loadLevelData(self, courseId, levelIndex):
        levelUrl = self.getJsonLevelUrl(courseId, levelIndex)
        response = self.downloadWithRetry(levelUrl, 3)
        return json.load(response)
    
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

