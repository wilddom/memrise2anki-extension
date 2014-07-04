import urllib2, cookielib, urllib, httplib, urlparse, re, time, os.path, json
import uuid
import BeautifulSoup

class Thing(object):
    def __init__(self, thingId):
        self.id = thingId
        self.targetDefinitions = []
        self.targetAlternatives = []
        self.targetAlternativesHidden = []
        self.sourceDefinitions = []
        self.sourceAlternatives = []
        self.sourceAlternativesHidden = []
        self.audioUrls = []
        self.imageUrls = []

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

class ColumnHelper(object):
    def __init__(self, columnData):
        self.textColumnIndices = []
        self.textColumnLabels = []
        self.audioColumnIndices = []
        self.audioColumnLabels = []
        self.imageColumnIndices = []
        self.imageColumnLabels = []
        
        for index, column in columnData.items():
            if (column["kind"] == "text"):
                self.textColumnIndices.append(index)
                self.textColumnLabels.append(column["label"])
            elif (column["kind"] == "audio"):
                self.audioColumnIndices.append(index)
                self.audioColumnLabels.append(column["label"])
            elif (column["kind"] == "image"):
                self.imageColumnIndices.append(index)
                self.imageColumnLabels.append(column["label"])

    @staticmethod
    def getDefinitions(indices, thingData):
        data = []
        for index in indices:
            value = thingData["columns"][index]["val"]
            if value:
                data.append(value)
        return data
    
    @staticmethod
    def getAlternatives(indices, thingData):
        alternatives = []
        for index in indices:
            for alt in thingData["columns"][index]["alts"]:
                value = alt['val']
                if value:
                    alternatives.append(value)
            for _, typing_corrects in thingData["columns"][index]["typing_corrects"].items():
                for value in typing_corrects:
                    if value:
                        alternatives.append(value)
        return alternatives
    
    @staticmethod
    def getUrls(indices, thingData):
        data = []
        for index in indices:
            values = thingData["columns"][index]["val"]
            for value in values:
                url = value["url"]
                if url:
                    data.append(url)
        return data
    
    def getTargetDefinitions(self, thingData):
        return self.getDefinitions(self.textColumnIndices[0:1], thingData)

    def getTargetAlternatives(self, thingData):
        return self.getAlternatives(self.textColumnIndices[0:1], thingData)

    def getSourceDefinitions(self, thingData):
        return self.getDefinitions(self.textColumnIndices[1:], thingData)

    def getSourceAlternatives(self, thingData):
        return self.getAlternatives(self.textColumnIndices[1:], thingData)

    def getAudioUrls(self, thingData):
        return self.getUrls(self.audioColumnIndices, thingData)

    def getImageUrls(self, thingData):
        return self.getUrls(self.imageColumnIndices, thingData)

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
        columnHelper = ColumnHelper(columnData)
        
        for thingId, thingData in levelData["things"].items():
            thing = Thing(thingId)
            thing.targetDefinitions = columnHelper.getTargetDefinitions(thingData)
            thing.sourceDefinitions = columnHelper.getSourceDefinitions(thingData)
            for alt in columnHelper.getTargetAlternatives(thingData):
                if not alt.startswith(u"_"):
                    thing.targetAlternatives.append(alt)
                else:
                    thing.targetAlternativesHidden.append(alt)
            for alt in columnHelper.getSourceAlternatives(thingData):
                if not alt.startswith(u"_"):
                    thing.sourceAlternatives.append(alt)
                else:
                    thing.sourceAlternativesHidden.append(alt)
            thing.audioUrls = map(self.service.toAbsoluteMediaUrl, columnHelper.getAudioUrls(thingData))
            thing.imageUrls = map(self.service.toAbsoluteMediaUrl, columnHelper.getImageUrls(thingData))
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

