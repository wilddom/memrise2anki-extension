import urllib.request, urllib.error, urllib.parse, http.cookiejar, urllib.request, urllib.parse, urllib.error, http.client, urllib.parse
import re, time, os.path, json, collections, datetime, calendar, functools, uuid
import bs4
from . import memrise_markdown

def utcToLocal(utcDt):
    offset = datetime.datetime.fromtimestamp(86400)-datetime.datetime.utcfromtimestamp(86400)
    return utcDt+offset

def sanitizeName(name, default=""):
    name = re.sub("<.*?>", "", name)
    name = re.sub("\s\s+", "", name)
    name = re.sub("\ufeff", "", name)
    name = name.strip()
    if not name:
        return default
    return name

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
        self.nextPosition = 1

    def __iter__(self):
        for level in self.levels:
            yield level
                
    def __len__(self):
        return len(self.levels)

    def getNextPosition(self):
        nextPosition = self.nextPosition
        self.nextPosition += 1
        return nextPosition

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
        return "{} -> {}".format(self.front, self.back)

class Schedule(object):
    def __init__(self):
        self.directionThing = {}
        self.thingDirection = {}
        
    def add(self, info):
        self.directionThing.setdefault(info.direction, {})[info.thingId] = info
        self.thingDirection.setdefault(info.thingId, {})[info.direction] = info
        
    def get(self, direction, thing):
        if not isinstance(thing, Thing):
            thing = Thing(thing)
        return self.directionThing.get(direction, {}).get(thing.id)
    
    def getScheduleInfos(self, thing):
        if not isinstance(thing, Thing):
            thing = Thing(thing)
        return self.thingDirection.get(thing.id, {})
    
    def getDirections(self):
        return list(self.directionThing.keys())

class ScheduleInfo(object):
    def __init__(self):
        self.thingId = None
        self.direction = Direction()
        self.position = 0
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
        
    def has(self, direction, thing):
        return thing.id in self.directionThing.get(direction, {})

    def get(self, direction, thing):
        return self.directionThing.get(direction, {}).get(thing.id, Mem())

    def getMems(self, thing):
        return self.thingDirection.get(thing.id, {})
    
    def getDirections(self):
        return list(self.directionThing.keys())
    
    def countDirections(self):
        return len(self.directionThing.keys())

class Mem(object):
    def __init__(self, memId=None):
        self.id = memId
        self.direction = Direction()
        self.thingId = None
        self.text = ""
        self.images = []
    
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
        return "{} {}".format(key, self.names[key])

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
        
        self.things = {}
        self.schedule = Schedule()
        self.mems = MemCollection()
        self.directions = set()

    def addThing(self, thing):
        self.things[thing.id] = thing
        
    def getThing(self, thingId):
        return self.things.get(thingId, None)

    def hasThing(self, thingId):
        return thingId in self.things

    def addColumn(self, colType, name, index):
        if not colType in Column.Types:
            return
        
        column = Column(colType, self.uniquifyName(sanitizeName(name, "Column")), int(index))
        self.columns[column.name] = column
        self.columnsByType[column.type][column.name] = column
        self.columnsByIndex[column.index] = column

    def addAttribute(self, attrType, name, index):
        if not attrType in Attribute.Types:
            return
        
        attribute = Attribute(attrType, self.uniquifyName(sanitizeName(name, "Attribute")), int(index))
        self.attributes[attribute.name] = attribute
    
    def getColumn(self, name):
        return self.columns.get(name)
    
    def getAttribute(self, name):
        return self.columns.get(name)
    
    def getColumnNames(self):
        return list(self.columns.keys())

    def getTextColumnNames(self):
        return list(self.columnsByType[Field.Text].keys())

    def getImageColumnNames(self):
        return list(self.columnsByType[Field.Image].keys())
    
    def getAudioColumnNames(self):
        return list(self.columnsByType[Field.Audio].keys())
    
    def getAttributeNames(self):
        return list(self.attributes.keys())
    
    def getColumns(self):
        return list(self.columns.values())
    
    def getTextColumns(self):
        return list(self.columnsByType[Field.Text].values())

    def getImageColumns(self):
        return list(self.columnsByType[Field.Image].values())
    
    def getAudioColumns(self):
        return list(self.columnsByType[Field.Audio].values())
    
    def getAttributes(self):
        return list(self.attributes.values())

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

class DownloadableFile(object):
    def __init__(self, remoteUrl=None):
        self.remoteUrl = remoteUrl
        self.localUrl = None
        
    def isDownloaded(self):
        return bool(self.localUrl)

class MediaColumnData(object):
    def __init__(self, files=[]):
        self.files = files
    
    def getFiles(self):
        return self.files
    
    def setFile(self, files):
        self.files = files
    
    def getRemoteUrls(self):
        return [f.remoteUrl for f in self.files]
    
    def getLocalUrls(self):
        return [f.localUrl for f in self.files]
    
    def setRemoteUrls(self, urls):
        self.files = list(map(DownloadableFile, urls))

    def setLocalUrls(self, urls):
        for url, f in zip(urls, self.files):
            f.localUrl = url

    def allDownloaded(self):
        return all([f.isDownloaded() for f in self.files])

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

    def getAudioFiles(self, nameOrIndex):
        return self.getAudioColumnData(nameOrIndex).getFiles()

    def setAudioFiles(self, nameOrIndex, files):
        return self.getAudioColumnData(nameOrIndex).setFiles(files)

    def getImageFiles(self, nameOrIndex):
        return self.getImageColumnData(nameOrIndex).getFiles()

    def setImageFiles(self, nameOrIndex, files):
        return self.getImageColumnData(nameOrIndex).setFiles(files)

    def getAudioUrls(self, nameOrIndex):
        return self.getAudioColumnData(nameOrIndex).getRemoteUrls()

    def getImageUrls(self, nameOrIndex):
        return self.getImageColumnData(nameOrIndex).getRemoteUrls()

    def setLocalAudioUrls(self, nameOrIndex, urls):
        self.getAudioColumnData(nameOrIndex).setLocalUrls(urls)
    
    def getLocalAudioUrls(self, nameOrIndex):
        return self.getAudioColumnData(nameOrIndex).getLocalUrls()

    def setLocalImageUrls(self, nameOrIndex, urls):
        self.getImageColumnData(nameOrIndex).setLocalUrls(urls)

    def getLocalImageUrls(self, nameOrIndex):
        return self.getImageColumnData(nameOrIndex).getLocalUrls()

class ThingLoader(object):
    def __init__(self, pool):
        self.pool = pool
    
    def loadThing(self, row, fixUrl=lambda url: url):        
        thing = Thing(row['id'])
        thing.pool = self.pool
        
        for column in self.pool.getTextColumns():
            cell = row['columns'].get(str(column.index), {})
            data = TextColumnData()
            data.values = self.__getDefinitions(cell)
            data.alternatives = self.__getAlternatives(cell)
            data.hiddenAlternatives = self.__getHiddenAlternatives(cell)
            data.typingCorrects = self.__getTypingCorrects(cell)
            thing.setTextColumnData(column.name, data)
        
        for column in self.pool.getAudioColumns():
            cell = row['columns'].get(str(column.index), {})
            data = MediaColumnData()
            data.setRemoteUrls(list(map(fixUrl, self.__getUrls(cell))))
            thing.setAudioColumnData(column.name, data)
            
        for column in self.pool.getImageColumns():
            cell = row['columns'].get(str(column.index), {})
            data = MediaColumnData()
            data.setRemoteUrls(list(map(fixUrl, self.__getUrls(cell))))
            thing.setImageColumnData(column.name, data)

        for attribute in self.pool.getAttributes():
            cell = row['attributes'].get(str(attribute.index), {})
            data = AttributeData()
            data.values = self.__getAttributes(cell)
            thing.setAttributeData(attribute.name, data)

        return thing

    @staticmethod
    def __getDefinitions(cell):
        return list(map(str.strip, cell.get("val", "").split(",")))
    
    @staticmethod
    def __getAlternatives(cell):
        data = []
        for alt in cell.get("alts", []):
            value = alt.get('val', "")
            if value and not value.startswith("_"):
                data.append(value)
        return data
    
    @staticmethod
    def __getHiddenAlternatives(cell):
        data = []
        for alt in cell.get("alts", []):
            value = alt.get('val', "")
            if value and value.startswith("_"):
                data.append(value.lstrip("_"))
        return data
    
    @staticmethod
    def __getTypingCorrects(cell):
        data = []
        for _, typing_corrects in list(cell.get("typing_corrects", {}).items()):
            for value in typing_corrects:
                if value:
                    data.append(value)
        return data
    
    @staticmethod
    def __getUrls(cell):
        data = []
        for value in cell.get("val", ""):
            url = value.get("url", "")
            if url:
                data.append(url)
        return data

    @staticmethod
    def __getAttributes(cell):
        return list(map(str.strip, cell.get("val", "").split(",")))

class CourseLoader(object):
    def __init__(self, service):
        self.service = service
        self.observers = []
        self.levelCount = 0
        self.thingCount = 0
        self.directionThing = {}
        self.uniquifyPoolName = NameUniquifier()
    
    def registerObserver(self, observer):
        self.observers.append(observer)
        
    def notify(self, signal, *attrs, **kwargs):
        for observer in self.observers:
            if hasattr(observer, signal):
                getattr(observer, signal)(*attrs, **kwargs)
    
    def loadCourse(self, courseId):
        course = Course(courseId)
        
        courseData = self.service.loadCourseData(course.id)

        course.title = sanitizeName(courseData["session"]["course"]["name"], "Course")
        course.description = courseData["session"]["course"]["description"]
        course.source = courseData["session"]["course"]["source"]["name"]
        course.target = courseData["session"]["course"]["target"]["name"]
        self.levelCount = courseData["session"]["course"]["num_levels"]
        self.thingCount = courseData["session"]["course"]["num_things"]
        
        self.notify('levelCountChanged', self.levelCount)
        self.notify('thingCountChanged', self.thingCount)
        
        for levelIndex in range(1,self.levelCount+1):
            try:
                level = self.loadLevel(course, levelIndex)
                if level:
                    course.levels.append(level)
            except LevelNotFoundError:
                level = {}
            self.notify('levelLoaded', levelIndex, level)
        
        return course
    
    def loadPool(self, data):
        pool = Pool(data["id"])
        pool.name = self.uniquifyPoolName(sanitizeName(data["name"], "Pool"))
        
        for index, column in sorted(data["columns"].items()):
            pool.addColumn(column['kind'], column['label'], index)

        for index, attribute in sorted(data["attributes"].items()):
            pool.addAttribute(attribute['kind'], attribute['label'], index)
        
        return pool
    
    @staticmethod
    def loadScheduleInfo(data, pool):
        direction = Direction()
        direction.front = pool.getColumnName(data["column_b"])
        direction.back = pool.getColumnName(data["column_a"])

        scheduleInfo = pool.schedule.get(direction, data['thing_id'])
        if not scheduleInfo:
            scheduleInfo = ScheduleInfo()

        scheduleInfo.thingId = data['thing_id']
        scheduleInfo.direction = direction
        scheduleInfo.ignored = data['ignored']
        scheduleInfo.interval = data['interval']
        scheduleInfo.correct = data.get('correct', 0)
        scheduleInfo.incorrect = data.get('attempts', 0) - data.get('correct', 0)
        scheduleInfo.total = data.get('attempts', 0)
        scheduleInfo.streak = data['current_streak']
        scheduleInfo.due = utcToLocal(datetime.datetime.strptime(data['next_date'], "%Y-%m-%dT%H:%M:%SZ"))
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
        mem.text, remoteImageUrls = memrise_markdown.convertAndReturnImages(text)
        mem.images.extend(list(map(DownloadableFile, list(map(fixUrl, remoteImageUrls)))))
        for before, after in zip(remoteImageUrls, [im.remoteUrl for im in mem.images]):
            if after != before:
                mem.text = mem.text.replace(before, after)
        return mem
    
    def loadLevel(self, course, levelIndex):
        levelData = self.service.loadLevelData(course.id, levelIndex)
        
        level = Level(levelData["session"]["level"]["id"])
        level.index = levelData["session"]["level"]["index"]
        level.title = sanitizeName(levelData["session"]["level"]["title"])
        level.course = course

        poolId = levelData["session"]["level"]["pool_id"]
        if not poolId in course.pools:
            poolData = self.service.loadPoolData(poolId)
            pool = self.loadPool(poolData)
            pool.course = course
            course.pools[poolId] = pool
        level.pool = course.pools[poolId]

        level.direction.front = level.pool.getColumnName(levelData["session"]["level"]["column_b"])
        level.direction.back = level.pool.getColumnName(levelData["session"]["level"]["column_a"])
        level.pool.directions.add(level.direction)
        course.directions.add(level.direction)

        for learnable in levelData["learnables"]:
            scheduleInfo = ScheduleInfo()
            scheduleInfo.thingId = learnable["thing_id"]
            scheduleInfo.direction = level.direction
            scheduleInfo.position = course.getNextPosition()
            level.pool.schedule.add(scheduleInfo)

        thingusers = {userData["thing_id"]: userData for userData in levelData["thingusers"]}

        thingLoader = ThingLoader(level.pool)
        for learnable in levelData["learnables"]:
            thingId = learnable['thing_id']
            if level.pool.hasThing(thingId):
                thing = level.pool.getThing(thingId)
            else:
                thingData = self.service.loadThingData(thingId)
                thing = thingLoader.loadThing(thingData, self.service.toAbsoluteMediaUrl)
                level.pool.addThing(thing)
            level.things.append(thing)

            if thing.id in thingusers:
                userData = thingusers[thing.id]
                level.pool.schedule.add(self.loadScheduleInfo(userData, level.pool))
                if userData["mem_id"] and not level.pool.mems.has(level.direction, thing):
                    try:
                        memData = self.service.loadMemData(userData["mem_id"], userData["thing_id"], int(userData["learnable_id"]), userData["column_a"], userData["column_b"])
                        level.pool.mems.add(self.loadMem(userData, memData, level.pool, self.service.toAbsoluteMediaUrl))
                    except MemNotFoundError:
                        pass

            if thing.id in self.directionThing.get(level.direction, {}):
                self.thingCount += 1
                self.notify('thingCountChanged', self.thingCount)
            self.directionThing.setdefault(level.direction, {})[thing.id] = thing
            
            self.notify('thingLoaded', thing)
        
        return level

class IncompleteReadHttpAndHttpsHandler(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
    def __init__(self, debuglevel=0):
        urllib.request.HTTPHandler.__init__(self, debuglevel)
        urllib.request.HTTPSHandler.__init__(self, debuglevel)
    
    @staticmethod
    def makeHttp10(http_class, *args, **kwargs):
        h = http_class(*args, **kwargs)
        h._http_vsn = 10
        h._http_vsn_str = "HTTP/1.0"
        return h
    
    @staticmethod
    def read(response, reopen10, amt=None):
        if hasattr(response, "response10"):
            return response.response10.read(amt)
        else:
            try:
                return response.read_savedoriginal(amt)
            except http.client.IncompleteRead:
                response.response10 = reopen10()
                return response.response10.read(amt)
    
    def do_open_wrapped(self, http_class, req, **http_conn_args):
        response = self.do_open(http_class, req, **http_conn_args)
        response.read_savedoriginal = response.read
        reopen10 = functools.partial(self.do_open, functools.partial(self.makeHttp10, http_class, **http_conn_args), req)
        response.read = functools.partial(self.read, response, reopen10)
        return response
    
    def http_open(self, req):
        return self.do_open_wrapped(http.client.HTTPConnection, req)
    
    def https_open(self, req):
        return self.do_open_wrapped(http.client.HTTPSConnection, req, context=self._context, check_hostname=self._check_hostname)

class MemriseError(RuntimeError):
    pass

class LevelNotFoundError(MemriseError):
    pass

class MemNotFoundError(MemriseError):
    pass

class Service(object):
    def __init__(self, downloadDirectory=None, cookiejar=None):
        self.downloadDirectory = downloadDirectory
        if cookiejar is None:
            cookiejar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(IncompleteReadHttpAndHttpsHandler, urllib.request.HTTPCookieProcessor(cookiejar))
        self.opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
    
    def openWithRetry(self, url, tryCount=3):
        try:
            return self.opener.open(url)
        except http.client.BadStatusLine:
            # not clear why this error occurs (seemingly randomly),
            # so I regret that all we can do is wait and retry.
            if tryCount > 0:
                time.sleep(0.1)
                return self.openWithRetry(url, tryCount-1)
            else:
                raise
    
    def isLoggedIn(self):
        request = urllib.request.Request('https://www.memrise.com/login/', None, {'Referer': 'https://www.memrise.com/'})
        response = self.openWithRetry(request)
        return bool(re.match('https?://www.memrise.com/home/', response.geturl()))
        
    def login(self, username, password):
        request1 = urllib.request.Request('https://www.memrise.com/login/', None, {'Referer': 'https://www.memrise.com/'})
        response1 = self.openWithRetry(request1)
        soup = bs4.BeautifulSoup(response1.read(), 'html.parser')
        form = soup.find("form", attrs={"action": '/login/'})
        fields = {}
        for field in form.find_all("input"):
            if 'name' in field.attrs:
                if 'value' in field.attrs:
                    fields[field['name']] = field['value']
                else:
                    fields[field['name']] = ""
        fields['username'] = username
        fields['password'] = password
        request2 = urllib.request.Request(response1.geturl(), urllib.parse.urlencode(fields).encode("utf-8"), {'Referer': response1.geturl()})
        try:
            response2 = self.openWithRetry(request2)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return False
            else:
                raise
        return bool(re.match('https?://www.memrise.com/home/', response2.geturl()))
    
    def loadCourse(self, url, observer=None):
        courseLoader = CourseLoader(self)
        if not observer is None:
            courseLoader.registerObserver(observer)
        return courseLoader.loadCourse(self.getCourseIdFromUrl(url))
    
    def loadCourseData(self, courseId):
        courseUrl = self.getHtmlCourseUrl(courseId)
        response = self.openWithRetry(courseUrl)
        soup = bs4.BeautifulSoup(response.read(), 'html.parser')

        levelCount = 0
        if soup.find_all('div', {'class': lambda x: x and 'levels' in x.split()}):
            levelNums = [int(tag.string) for tag in soup.find_all('div', {'class': 'level-index'})]
            if len(levelNums) > 0:
                levelCount = max(levelNums)
        elif soup.find_all('div', {'class': lambda x: x and 'things' in x.split()}):
            levelCount = 1

        if levelCount == 0:
            raise MemriseError("Can't get level count")

        for levelIndex in range(1,levelCount+1):
            try:
                return self.loadLevelData(courseId, levelIndex)
            except LevelNotFoundError:
                pass

    def loadLevelData(self, courseId, levelIndex):
        try:
            levelUrl = self.getJsonLevelUrl(courseId, levelIndex)
            response = self.openWithRetry(levelUrl)
            return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code == 404 or e.code == 400:
                raise LevelNotFoundError("Level not found: {}".format(levelIndex))
            else:
                raise
    
    def loadPoolData(self, poolId):
        poolUrl = self.getJsonPoolUrl(poolId)
        response = self.openWithRetry(poolUrl)
        result = json.load(response)
        return result.get("pool", result)

    def loadThingData(self, thingId):
        thingUrl = self.getJsonThingUrl(thingId)
        response = self.openWithRetry(thingUrl)
        result = json.load(response)
        return result.get("thing", result)

    def loadMemData(self, memId, thingId, learnableId, colA, colB):
        try:
            memUrl = self.getJsonMemUrl(memId, thingId, colA, colB)
            response = self.openWithRetry(memUrl)
            result = json.load(response)
            return result.get("mem", result)
        except urllib.error.HTTPError as e:
            if e.code == 404 or e.code == 400:
                memsUrl = self.getJsonManyMemUrl(thingId, learnableId)
                response = self.openWithRetry(memsUrl)
                result = json.load(response)
                for memData in result.get("mems", {}):
                    if memData.get('id') == memId:
                        return memData
            else:
                raise
        raise MemNotFoundError("Mem not found (memId={}, thingId={}, learnableId={}, colA={}, colB={})".format(memId, thingId, learnableId, colA, colB))

    @staticmethod
    def getCourseIdFromUrl(url):
        match = re.match('https?://www.memrise.com/course/(\d+)/.+/', url)
        if not match:
            raise MemriseError("Import failed. Does your URL look like the sample URL above?")
        return int(match.group(1))

    @staticmethod
    def checkCourseUrl(url):
        match = re.match('https?://www.memrise.com/course/\d+/.+/', url)
        return bool(match)

    @staticmethod
    def getHtmlCourseUrl(courseId):
        return 'https://www.memrise.com/course/{:d}/'.format(courseId)
    
    @staticmethod
    def getJsonLevelUrl(courseId, levelIndex):
        return "https://www.memrise.com/ajax/session/?course_id={:d}&level_index={:d}&session_slug=preview".format(courseId, levelIndex)
    
    @staticmethod
    def getJsonPoolUrl(poolId):
        return "https://www.memrise.com/api/pool/get/?pool_id={:d}".format(poolId)

    @staticmethod
    def getJsonThingUrl(thingId):
        return "https://www.memrise.com/api/thing/get/?thing_id={:d}".format(thingId)

    @staticmethod
    def getJsonMemUrl(memId, thingId, colA, colB):
        return "https://www.memrise.com/api/mem/get/?mem_id={:d}&thing_id={:d}&column_a={:d}&column_b={:d}".format(memId, thingId, colA, colB)

    @staticmethod
    def getJsonManyMemUrl(thingId, learnableId):
        return "https://www.memrise.com/api/mem/get_many_for_thing/?thing_id={:d}&learnable_id={:d}".format(thingId, learnableId)

    @staticmethod
    def toAbsoluteMediaUrl(url):
        if not url:
            return url
        # fix wrong urls: /static/xyz should map to https://static.memrise.com/xyz
        url = re.sub("^\/static\/", "/", url)
        return urllib.parse.urljoin("http://static.memrise.com/", url)
    
    def downloadMedia(self, url, skipExisting=False):
        if not self.downloadDirectory:
            return url
        
        # Replace links to images and audio on the Memrise servers
        # by downloading the content to the user's media dir
        memrisePath = urllib.parse.urlparse(url).path
        contentExtension = os.path.splitext(memrisePath)[1]
        localName = "{:s}{:s}".format(str(uuid.uuid5(uuid.NAMESPACE_URL, url)), contentExtension)
        fullMediaPath = os.path.join(self.downloadDirectory, localName)
        
        if skipExisting and os.path.isfile(fullMediaPath) and os.path.getsize(fullMediaPath) > 0:
            return localName
        
        data = self.openWithRetry(url).read()
        with open(fullMediaPath, "wb") as mediaFile:
            mediaFile.write(data)

        return localName
