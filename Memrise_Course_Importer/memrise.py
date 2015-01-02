import urllib2, cookielib, urllib, httplib, urlparse, re, time, os.path, json, collections, itertools, datetime, calendar
import uuid
import BeautifulSoup

def utcToLocal(utcDt):
    # get integer timestamp to avoid precision lost
    timestamp = calendar.timegm(utcDt.timetuple())
    localDt = datetime.datetime.fromtimestamp(timestamp)
    assert utcDt.resolution >= datetime.timedelta(microseconds=1)
    return localDt.replace(microsecond=utcDt.microsecond)

class Course(object):
    def __init__(self, courseId):
        self.id = courseId
        self.title = ""
        self.description = ""
        self.source = ""
        self.target = ""
        self.levels = []
        self.pools = {}

    def __iter__(self):
        for level in self.levels:
            yield level
                
    def __len__(self):
        return len(self.levels)

class Direction(object):
    def __init__(self, front=None, back=None):
        self.front = front
        self.back = back
        
    def __hash__(self):
        return hash((self.front, self.back))
    
    def __eq__(self, other):
        return (self.front, self.back) == (other.front, other.back)

class Schedule(object):
    def __init__(self):
        self.data = {}
        
    def add(self, info):
        self.data.setdefault(info.direction, {})[info.thingId] = info
        
    def get(self, direction, thing):
        return self.data.get(direction, {}).get(thing.id)

class ScheduleInfo(object):
    def __init__(self):
        self.thingId = None
        self.direction = Direction()
        self.interval = None
        self.ignored = False
        self.total = 0
        self.correct = 0
        self.incorrect = 0
        self.streak = 0
        self.due = datetime.date.today()

class Level(object):
    def __init__(self, levelId):
        self.id = levelId
        self.index = 0
        self.title = ""
        self.things = []
        self.course = None
        self.pool = None
        self.direction = Direction()
        
    def __iter__(self):
        for thing in self.things:
            yield thing
                
    def __len__(self):
        return len(self.things)

class NameUniquifier(object):
    def __init__(self):
        self.names = {}

    def __call__(self, key):
        if key not in self.names:
            self.names[key] = 1
            return key

        self.names[key] += 1
        return u"{} {}".format(key, self.names[key])

class Pool(object):
    def __init__(self, poolId=None):
        self.id = poolId
        self.name = ''

        self.textColumns = collections.OrderedDict()
        self.audioColumns = collections.OrderedDict()
        self.imageColumns = collections.OrderedDict()
        self.attributes = collections.OrderedDict()

        self.columnNamesIndex = {}
        self.uniquifyName = NameUniquifier()
        
        self.schedule = Schedule()

    def addColumn(self, colType, name, index):
        key = self.uniquifyName(name)
        if colType == 'text':
            self.textColumns[key] = index
        elif colType == 'audio':
            self.audioColumns[key] = index
        elif colType == 'image':
            self.imageColumns[key] = index
        else:
            return
        self.columnNamesIndex[unicode(index)] = key

    def addAttribute(self, attrType, name, index):
        key = self.uniquifyName(name)
        if attrType == 'text':
            self.attributes[key] = index

    def getColumnName(self, index):
        return self.columnNamesIndex.get(unicode(index))

    def getTextColumnNames(self):
        return self.textColumns.keys()

    def getImageColumnNames(self):
        return self.imageColumns.keys()
    
    def getAudioColumnNames(self):
        return self.audioColumns.keys()

    def getAttributeNames(self):
        return self.attributes.keys()

    @staticmethod
    def __getKeyFromIndex(keys, index):
        if not isinstance(index, int):
            return index
        return keys[index]
    
    def getTextColumnName(self, index):
        return self.__getKeyFromIndex(self.getTextColumnNames(), index)

    def getImageColumnName(self, index):
        return self.__getKeyFromIndex(self.getImageColumnNames(), index)
    
    def getAudioColumnName(self, index):
        return self.__getKeyFromIndex(self.getAudioColumnNames(), index)

    def getAttributeName(self, index):
        return self.__getKeyFromIndex(self.getAttributeNames(), index)

    def hasTextColumnName(self, name):
        return name in self.getTextColumnNames()

    def hasImageColumnName(self, name):
        return name in self.getImageColumnNames()
    
    def hasAudioColumnName(self, name):
        return name in self.getAudioColumnNames()

    def hasAttributeName(self, name):
        return name in self.getAttributeNames()

    def countTextColumns(self):
        return len(self.textColumns)
    
    def countImageColumns(self):
        return len(self.imageColumns)
    
    def countAudioColumns(self):
        return len(self.audioColumns)
    
    def countAttributes(self):
        return len(self.attributes)

class Thing(object):
    def __init__(self, thingId):
        self.id = thingId
        self.level = None
        self.pool = None
        
        self.textData = collections.OrderedDict()
        self.audioUrls = collections.OrderedDict()
        self.imageUrls = collections.OrderedDict()
        self.attributes = collections.OrderedDict()
        
        self.localAudioUrls = collections.OrderedDict()
        self.localImageUrls = collections.OrderedDict()
    
    def getAudioUrls(self, nameOrIndex):
        name = self.pool.getAudioColumnName(nameOrIndex)
        return self.audioUrls[name]
        
    def getAllAudioUrls(self):
        return list(itertools.chain.from_iterable(self.audioUrls.values()))

    def getImageUrls(self, nameOrIndex):
        name = self.pool.getImageColumnName(nameOrIndex)
        return self.imageUrls[name]
            
    def getAllImageUrls(self):
        return list(itertools.chain.from_iterable(self.imageUrls.values()))

    def getDefinition(self, nameOrIndex):
        name = self.pool.getTextColumnName(nameOrIndex)
        return self.textData[name]['value']
    
    def __getTextData(self, attr, start=None, stop=None):
        return map(lambda x: x[attr], itertools.islice(self.textData.itervalues(), start, stop))
    
    def getDefinitions(self, startIndex=None, endIndex=None):
        return self.__getTextData('value', startIndex, endIndex)
    
    def getAlternatives(self, nameOrIndex):
        name = self.pool.getTextColumnName(nameOrIndex)
        return self.textData[name]['alternatives']
    
    def getHiddenAlternatives(self, nameOrIndex):
        name = self.pool.getTextColumnName(nameOrIndex)
        return self.textData[name]['hidden_alternatives']
    
    def getTypingCorrects(self, nameOrIndex):
        name = self.pool.getTextColumnName(nameOrIndex)
        return self.textData[name]['typing_corrects']

    def getAttribute(self, nameOrIndex):
        name = self.pool.getAttributeName(nameOrIndex)
        return self.attributes[name]
    
    def getAllAttributes(self):
        return filter(bool, self.attributes.values())
    
    def setLocalAudioUrls(self, nameOrIndex, urls):
        name = self.pool.getAudioColumnName(nameOrIndex)
        self.localAudioUrls[name] = urls
    
    def getLocalAudioUrls(self, nameOrIndex):
        name = self.pool.getAudioColumnName(nameOrIndex)
        return self.localAudioUrls[name]
        
    def getAllLocalAudioUrls(self):
        return list(itertools.chain.from_iterable(self.localAudioUrls.values()))

    def setLocalImageUrls(self, nameOrIndex, urls):
        name = self.pool.getImageColumnName(nameOrIndex)
        self.localImageUrls[name] = urls

    def getLocalImageUrls(self, nameOrIndex):
        name = self.pool.getImageColumnName(nameOrIndex)
        return self.localImageUrls[name]
            
    def getAllLocalImageUrls(self):
        return list(itertools.chain.from_iterable(self.localImageUrls.values()))

class ThingLoader(object):
    def __init__(self, pool):
        self.pool = pool
    
    def createThing(self, thingId):
        thing = Thing(thingId)
        thing.pool = self.pool
        
        for colName in self.pool.getTextColumnNames():
            thing.textData[colName] = {
                'value': "",
                'alternatives': [],
                'hidden_alternatives': [],
                'typing_corrects': []
            }
        
        for colName in self.pool.getAudioColumnNames():
            thing.audioUrls[colName] = []
            thing.localAudioUrls[colName] = []
            
        for colName in self.pool.getImageColumnNames():
            thing.imageUrls[colName] = []
            thing.localImageUrls[colName] = []
            
        for attrName in self.pool.getAttributeNames():
            thing.attributes[attrName] = ""
            
        return thing
    
    def loadThing(self, row, fixUrl=lambda url: url):
        thing = self.createThing(row['id'])
        
        for colName, colIndex in self.pool.textColumns.items():
            cell = row['columns'][colIndex]
            thing.textData[colName]["value"] = self.__getDefinition(cell)
            thing.textData[colName]["alternatives"] = self.__getAlternatives(cell)
            thing.textData[colName]["hidden_alternatives"] = self.__getHiddenAlternatives(cell)
            thing.textData[colName]["typing_corrects"] = self.__getTypingCorrects(cell)
        
        for colName, colIndex in self.pool.audioColumns.items():
            cell = row['columns'][colIndex]
            thing.audioUrls[colName] = map(fixUrl, self.__getUrls(cell))
            
        for colName, colIndex in self.pool.imageColumns.items():
            cell = row['columns'][colIndex]
            thing.imageUrls[colName] = map(fixUrl, self.__getUrls(cell))

        for attrName, attrIndex in self.pool.attributes.items():
            cell = row['attributes'][attrIndex]
            thing.attributes[attrName] = self.__getAttribute(cell)

        return thing

    @staticmethod
    def __getDefinition(cell):
        return cell["val"]
    
    @staticmethod
    def __getAlternatives(cell):
        data = []
        for alt in cell["alts"]:
            value = alt['val']
            if value and not value.startswith(u"_"):
                data.append(value)
        return data
    
    @staticmethod
    def __getHiddenAlternatives(cell):
        data = []
        for alt in cell["alts"]:
            value = alt['val']
            if value and value.startswith(u"_"):
                data.append(value.lstrip(u'_'))
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
    
    @staticmethod
    def loadPool(data):
        pool = Pool(data["id"])
        pool.name = data["name"]
        
        for index, column in sorted(data["columns"].items()):
            pool.addColumn(column['kind'], column['label'], index)

        for index, attribute in sorted(data["attributes"].items()):
            pool.addAttribute(attribute['kind'], attribute['label'], index)
        
        return pool
    
    @staticmethod
    def loadScheduleInfo(data, pool):
        scheduleInfo = ScheduleInfo()
        scheduleInfo.thingId = data['thing_id']
        scheduleInfo.direction.front = pool.getColumnName(data["column_b"])
        scheduleInfo.direction.back = pool.getColumnName(data["column_a"])
        scheduleInfo.ignored = data['ignored']
        scheduleInfo.interval = data['interval']
        scheduleInfo.correct = data['total_correct']
        scheduleInfo.incorrect = data['total_incorrect']
        scheduleInfo.total = data['total_correct']+data['total_incorrect']
        scheduleInfo.streak = data['current_streak']
        scheduleInfo.due = utcToLocal(datetime.datetime.strptime(data['next_date'], "%Y-%m-%dT%H:%M:%S"))
        return scheduleInfo
    
    def loadLevel(self, course, levelIndex):
        levelData = self.service.loadLevelData(course.id, levelIndex)
        
        if levelData["success"] == False:
            return None
        
        level = Level(levelData["session"]["level"]["id"])
        level.index = levelData["session"]["level"]["index"]
        level.title = levelData["session"]["level"]["title"]
        level.course = course

        poolId = levelData["session"]["level"]["pool_id"]
        if not poolId in course.pools:
            course.pools[poolId] = self.loadPool(levelData["pools"][unicode(poolId)])
        level.pool = course.pools[poolId]

        level.direction.front = level.pool.getColumnName(levelData["session"]["level"]["column_b"])
        level.direction.back = level.pool.getColumnName(levelData["session"]["level"]["column_a"])

        for userData in levelData["thingusers"]:
            level.pool.schedule.add(self.loadScheduleInfo(userData, level.pool))

        thingLoader = ThingLoader(level.pool)
        for _, thingRowData in levelData["things"].items():
            thing = thingLoader.loadThing(thingRowData, self.service.toAbsoluteMediaUrl)
            thing.level = level
            level.things.append(thing)
            self.notify('thingLoaded', thing)
        
        return level

class Service(object):
    def __init__(self, downloadDirectory=None, cookiejar=None):
        self.downloadDirectory = downloadDirectory
        if cookiejar is None:
            cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar))
        self.opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
    
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
        request = urllib2.Request('http://www.memrise.com/login/', None, {'Referer': 'http://www.memrise.com/'})
        response = self.opener.open(request)
        return response.geturl() == 'http://www.memrise.com/home/'
        
    def login(self, username, password):
        request1 = urllib2.Request('http://www.memrise.com/login/', None, {'Referer': 'http://www.memrise.com/'})
        response1 = self.opener.open(request1)
        soup = BeautifulSoup.BeautifulSoup(response1.read())
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
        request2 = urllib2.Request(response1.geturl(), urllib.urlencode(fields), {'Referer': response1.geturl()})
        response2 = self.opener.open(request2)
        return response2.geturl() == 'http://www.memrise.com/home/'
    
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
    def checkCourseUrl(url):
        match = re.match('http://www.memrise.com/course/\d+/.+/', url)
        return bool(match)

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
    
    def downloadMedia(self, url, skipExisting=False):
        if not self.downloadDirectory:
            return url
        
        # Replace links to images and audio on the Memrise servers
        # by downloading the content to the user's media dir
        memrisePath = urlparse.urlparse(url).path
        contentExtension = os.path.splitext(memrisePath)[1]
        localName = "{:s}{:s}".format(uuid.uuid5(uuid.NAMESPACE_URL, url.encode('utf-8')), contentExtension)
        fullMediaPath = os.path.join(self.downloadDirectory, localName)
        
        if skipExisting and os.path.isfile(fullMediaPath):
            return localName
        
        try:
            with open(fullMediaPath, "wb") as mediaFile:
                mediaFile.write(self.downloadWithRetry(url, 3).read())
        except urllib2.HTTPError as e:
            if e.code == 403:
                return False
            else:
                raise e

        return localName
