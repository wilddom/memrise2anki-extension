import urllib2, cookielib, urllib, httplib, urlparse, re, time, os.path, json, collections, datetime, calendar
import BeautifulSoup
import uuid, markdown

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
        self.directions = set()

    def __iter__(self):
        for level in self.levels:
            yield level
                
    def __len__(self):
        return len(self.levels)

class Direction(object):
    def __init__(self, front=None, back=None):
        self.front = front
        self.back = back
        
    def isValid(self):
        return self.front != None and self.back != None
        
    def __hash__(self):
        return hash((self.front, self.back))
    
    def __eq__(self, other):
        return (self.front, self.back) == (other.front, other.back)
    
    def __ne__(self, other):
        return not self.__eq__(other)

    def __unicode__(self):
        return u"{} -> {}".format(self.front, self.back)

class Schedule(object):
    def __init__(self):
        self.directionThing = {}
        self.thingDirection = {}
        
    def add(self, info):
        self.directionThing.setdefault(info.direction, {})[info.thingId] = info
        self.thingDirection.setdefault(info.thingId, {})[info.direction] = info
        
    def get(self, direction, thing):
        return self.directionThing.get(direction, {}).get(thing.id)
    
    def getScheduleInfos(self, thing):
        return self.thingDirection.get(thing.id, {})
    
    def getDirections(self):
        return self.directionThing.keys()

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

class MemCollection(object):
    def __init__(self):
        self.directionThing = {}
        self.thingDirection = {}
        
    def add(self, mem):
        self.directionThing.setdefault(mem.direction, {})[mem.thingId] = mem
        self.thingDirection.setdefault(mem.thingId, {})[mem.direction] = mem
        
    def get(self, direction, thing):
        return self.directionThing.get(direction, {}).get(thing.id, Mem())

    def getMems(self, thing):
        return self.thingDirection.get(thing.id, {})
    
    def getDirections(self):
        return self.directionThing.keys()
    
    def countDirections(self):
        return len(self.directionThing.keys())

class Mem(object):
    def __init__(self, memId=None):
        self.id = memId
        self.direction = Direction()
        self.thingId = None
        self.text = ""
        self.remoteImageUrls = []
        self.localImageUrls = []
    
    def get(self):
        return self.text

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

class Field(object):
    Text = 'text'
    Audio = 'audio'
    Image = 'image'
    Mem = 'mem'
    
    def __init__(self, fieldType, name, index):
        self.type = fieldType
        self.name = name
        self.index = index

class Column(Field):
    Types = [Field.Text, Field.Audio, Field.Image]
    
    def __init__(self, colType, name, index):
        super(Column, self).__init__(colType, name, index)

class Attribute(Field):
    Types = [Field.Text]
    
    def __init__(self, attrType, name, index):
        super(Attribute, self).__init__(attrType, name, index)

class Pool(object):
    def __init__(self, poolId=None):
        self.id = poolId
        self.name = ''
        self.course = None
        
        self.columns = collections.OrderedDict()
        self.attributes = collections.OrderedDict()

        self.columnsByType = collections.OrderedDict()
        for colType in Column.Types:
            self.columnsByType[colType] = collections.OrderedDict()
        self.columnsByIndex = collections.OrderedDict()
        
        self.uniquifyName = NameUniquifier()
        
        self.schedule = Schedule()
        self.mems = MemCollection()

    def addColumn(self, colType, name, index):
        if not colType in Column.Types:
            return
        
        column = Column(colType, self.uniquifyName(name), int(index))
        self.columns[column.name] = column
        self.columnsByType[column.type][column.name] = column
        self.columnsByIndex[column.index] = column

    def addAttribute(self, attrType, name, index):
        if not attrType in Attribute.Types:
            return
        
        attribute = Attribute(attrType, self.uniquifyName(name), int(index))
        self.attributes[attribute.name] = attribute
    
    def getColumn(self, name):
        return self.columns.get(name)
    
    def getAttribute(self, name):
        return self.columns.get(name)
    
    def getColumnNames(self):
        return self.columns.keys()

    def getTextColumnNames(self):
        return self.columnsByType[Field.Text].keys()

    def getImageColumnNames(self):
        return self.columnsByType[Field.Image].keys()
    
    def getAudioColumnNames(self):
        return self.columnsByType[Field.Audio].keys()
    
    def getAttributeNames(self):
        return self.attributes.keys()
    
    def getColumns(self):
        return self.columns.values()
    
    def getTextColumns(self):
        return self.columnsByType[Field.Text].values()

    def getImageColumns(self):
        return self.columnsByType[Field.Image].values()
    
    def getAudioColumns(self):
        return self.columnsByType[Field.Audio].values()
    
    def getAttributes(self):
        return self.attributes.values()

    @staticmethod
    def __getKeyFromIndex(keys, index):
        if not isinstance(index, int):
            return index
        return keys[index]
    
    def getColumnName(self, memriseIndex):
        column = self.columnsByIndex.get(int(memriseIndex))
        if column:
            return column.name
        return None
    
    def getTextColumnName(self, nameOrIndex):
        return self.__getKeyFromIndex(self.getTextColumnNames(), nameOrIndex)

    def getImageColumnName(self, nameOrIndex):
        return self.__getKeyFromIndex(self.getImageColumnNames(), nameOrIndex)
    
    def getAudioColumnName(self, nameOrIndex):
        return self.__getKeyFromIndex(self.getAudioColumnNames(), nameOrIndex)

    def getAttributeName(self, nameOrIndex):
        return self.__getKeyFromIndex(self.getAttributeNames(), nameOrIndex)

    def hasColumnName(self, name):
        return name in self.columns
    
    def hasTextColumnName(self, name):
        return name in self.getTextColumnNames()

    def hasImageColumnName(self, name):
        return name in self.getImageColumnNames()
    
    def hasAudioColumnName(self, name):
        return name in self.getAudioColumnNames()

    def hasAttributeName(self, name):
        return name in self.getAttributeNames()

    def countColumns(self):
        return len(self.columns)
    
    def countTextColumns(self):
        return len(self.columnsByType[Field.Text])
    
    def countImageColumns(self):
        return len(self.columnsByType[Field.Image])
    
    def countAudioColumns(self):
        return len(self.columnsByType[Field.Audio])
    
    def countAttributes(self):
        return len(self.attributes)

class TextColumnData(object):
    def __init__(self):
        self.values = []
        self.alternatives = []
        self.hiddenAlternatives = []
        self.typingCorrects = []

class MediaColumnData(object):
    def __init__(self):
        self.remoteUrls = []
        self.localUrls = []

class AttributeData(object):
    def __init__(self):
        self.values = []

class Thing(object):
    def __init__(self, thingId):
        self.id = thingId
        self.pool = None
        
        self.columnData = collections.OrderedDict()
        self.columnDataByType = collections.OrderedDict()
        for colType in Column.Types:
            self.columnDataByType[colType] = collections.OrderedDict()
        
        self.attributeData = collections.OrderedDict()
    
    def getColumnData(self, name):
        return self.columnData[name]
    
    def getTextColumnData(self, nameOrIndex):
        name = self.pool.getTextColumnName(nameOrIndex)
        return self.columnDataByType[Field.Text][name]
    
    def getAudioColumnData(self, nameOrIndex):
        name = self.pool.getAudioColumnName(nameOrIndex)
        return self.columnDataByType[Field.Audio][name]
    
    def getImageColumnData(self, nameOrIndex):
        name = self.pool.getImageColumnName(nameOrIndex)
        return self.columnDataByType[Field.Image][name]
    
    def getAttributeData(self, nameOrIndex):
        name = self.pool.getAttributeName(nameOrIndex)
        return self.attributeData[name]
    
    def setTextColumnData(self, nameOrIndex, data):
        name = self.pool.getTextColumnName(nameOrIndex)
        self.columnDataByType[Field.Text][name] = data
        self.columnData[name] = data
    
    def setAudioColumnData(self, nameOrIndex, data):
        name = self.pool.getTextColumnName(nameOrIndex)
        self.columnDataByType[Field.Audio][name] = data
        self.columnData[name] = data
        
    def setImageColumnData(self, nameOrIndex, data):
        name = self.pool.getTextColumnName(nameOrIndex)
        self.columnDataByType[Field.Image][name] = data
        self.columnData[name] = data
    
    def setAttributeData(self, nameOrIndex, data):
        name = self.pool.getAttributeName(nameOrIndex)
        self.attributeData[name] = data
    
    def getDefinitions(self, nameOrIndex):
        return self.getTextColumnData(nameOrIndex).values
    
    def getAlternatives(self, nameOrIndex):
        return self.getTextColumnData(nameOrIndex).alternatives
    
    def getHiddenAlternatives(self, nameOrIndex):
        return self.getTextColumnData(nameOrIndex).hiddenAlternatives
    
    def getTypingCorrects(self, nameOrIndex):
        return self.getTextColumnData(nameOrIndex).typingCorrects

    def getAttributes(self, nameOrIndex):
        return self.getAttributeData(nameOrIndex).values

    def getAudioUrls(self, nameOrIndex):
        return self.getAudioColumnData(nameOrIndex).remoteUrls

    def getImageUrls(self, nameOrIndex):
        return self.getImageColumnData(nameOrIndex).remoteUrls

    def setLocalAudioUrls(self, nameOrIndex, urls):
        self.getAudioColumnData(nameOrIndex).localUrls = urls
    
    def getLocalAudioUrls(self, nameOrIndex):
        return self.getAudioColumnData(nameOrIndex).localUrls

    def setLocalImageUrls(self, nameOrIndex, urls):
        self.getImageColumnData(nameOrIndex).localUrls = urls

    def getLocalImageUrls(self, nameOrIndex):
        return self.getImageColumnData(nameOrIndex).localUrls

class ThingLoader(object):
    def __init__(self, pool):
        self.pool = pool
    
    def loadThing(self, row, fixUrl=lambda url: url):
        thing = Thing(row['id'])
        thing.pool = self.pool
        
        for column in self.pool.getTextColumns():
            cell = row['columns'][unicode(column.index)]
            data = TextColumnData()
            data.values = self.__getDefinitions(cell)
            data.alternatives = self.__getAlternatives(cell)
            data.hiddenAlternatives = self.__getHiddenAlternatives(cell)
            data.typingCorrects = self.__getTypingCorrects(cell)
            thing.setTextColumnData(column.name, data)
        
        for column in self.pool.getAudioColumns():
            cell = row['columns'][unicode(column.index)]
            data = MediaColumnData()
            data.remoteUrls = map(fixUrl, self.__getUrls(cell))
            thing.setAudioColumnData(column.name, data)
            
        for column in self.pool.getImageColumns():
            cell = row['columns'][unicode(column.index)]
            data = MediaColumnData()
            data.remoteUrls = map(fixUrl, self.__getUrls(cell))
            thing.setImageColumnData(column.name, data)

        for attribute in self.pool.getAttributes():
            cell = row['attributes'][unicode(attribute.index)]
            data = AttributeData()
            data.values = self.__getAttributes(cell)
            thing.setAttributeData(attribute.name, data)

        return thing

    @staticmethod
    def __getDefinitions(cell):
        return map(unicode.strip, cell["val"].split(","))
    
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
    def __getAttributes(cell):
        return map(unicode.strip, cell["val"].split(","))

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
    
    @staticmethod
    def loadMem(data, memData, pool, fixUrl=lambda url: url):
        mem = Mem(memData['id'])
        mem.thingId = data['thing_id']
        mem.direction.front = pool.getColumnName(data["column_b"])
        mem.direction.back = pool.getColumnName(data["column_a"])
        text = memData['text']
        if memData['image_output_url']:
            text = "img:{}".format(memData['image_output_url'])
        mem.text, remoteImageUrls = markdown.convertAndReturnImages(text)
        mem.remoteImageUrls.extend(map(fixUrl, remoteImageUrls))
        return mem
    
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
            pool = self.loadPool(levelData["pools"][unicode(poolId)])
            pool.course = course
            course.pools[poolId] = pool
        level.pool = course.pools[poolId]

        level.direction.front = level.pool.getColumnName(levelData["session"]["level"]["column_b"])
        level.direction.back = level.pool.getColumnName(levelData["session"]["level"]["column_a"])
        course.directions.add(level.direction)

        for userData in levelData["thingusers"]:
            level.pool.schedule.add(self.loadScheduleInfo(userData, level.pool))
            memData = levelData["mems"].get(unicode(userData["thing_id"]),{}).get(unicode(userData["mem_id"]))
            if memData:
                level.pool.mems.add(self.loadMem(userData, memData, level.pool, self.service.toAbsoluteMediaUrl))

        thingLoader = ThingLoader(level.pool)
        for _, thingRowData in levelData["things"].items():
            thing = thingLoader.loadThing(thingRowData, self.service.toAbsoluteMediaUrl)
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
        if not url:
            return url
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
