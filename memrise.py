import urllib.request, urllib.error, urllib.parse, http.cookiejar, http.client
import re, os.path, json, collections, datetime, uuid, itertools, hashlib, enum
import bs4
import requests.adapters, requests.sessions
from urllib3.util.retry import Retry

def sanitizeName(name, default=""):
    name = re.sub(r"<.*?>", "", name)
    name = re.sub(r"\s\s+", "", name)
    name = re.sub(r"\ufeff", "", name)
    name = name.strip()
    if not name:
        return default
    return name

def parse_date(iso_str):
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
    except ValueError:
        dt = datetime.datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt.replace(tzinfo=datetime.timezone.utc)
    return dt

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

    def __str__(self):
        return "{} -> {}".format(self.front, self.back)

try:
    class FieldType(enum.StrEnum):
        Text = 'text'
        Audio = 'audio'
        Image = 'image'
        Video = 'video'
except AttributeError:
    class FieldType(str, enum.Enum):
        Text = 'text'
        Audio = 'audio'
        Image = 'image'
        Video = 'video'

class Field(object):
    def __init__(self, fieldType, name):
        self.type = fieldType
        self.name = name

class Column(Field):
    Types = [FieldType.Text, FieldType.Audio, FieldType.Image, FieldType.Video]

    def __init__(self, colType, name, side):
        super(Column, self).__init__(colType, name)
        self.side = side

class Attribute(Field):
    Types = [FieldType.Text]

    def __init__(self, attrType, name):
        super(Attribute, self).__init__(attrType, name)

class Course(object):
    def __init__(self, courseId):
        self.id = courseId
        self.title = ""
        self.description = ""
        
        self.nextPosition = 1
        
        self.levels = []
        
        self.columns = collections.OrderedDict()
        self.attributes = collections.OrderedDict()

        self.columnsByType = collections.OrderedDict()
        for colType in Column.Types:
            self.columnsByType[colType] = collections.OrderedDict()

    def __iter__(self):
        for level in self.levels:
            yield level

    def __len__(self):
        return len(self.levels)

    def all_learnables(self):
        for level in self.levels:
            for learnable in level:
                yield learnable

    def len_learnables(self):
        return sum(map(len, self.levels))

    def similar_learnables(self):
        learnables = {}
        for learnable in self.all_learnables():
            learnables.setdefault(learnable.checksum(), []).append(learnable)
        return learnables

    def getNextPosition(self):
        nextPosition = self.nextPosition
        self.nextPosition += 1
        return nextPosition

    def hasLearnable(self, learnableId):
        for level in self.levels:
            if level.hasLearnable(learnableId):
                return True
        return False

    def getLearnable(self, learnableId):
        for level in self.levels:
            if level.hasLearnable(learnableId):
                return level.getLearnable(learnableId)
        return None
    
    def getDirections(self):
        return list(set(itertools.chain(*map(lambda x: x.getDirections(), self.levels))))

    def addColumn(self, colType, name, side):
        if not colType in Column.Types:
            return None

        column = Column(colType, sanitizeName(name, "Column"), side)
        self.columns[column.name] = column
        self.columnsByType[column.type][column.name] = column
        return column

    def addAttribute(self, attrType, name):
        if not attrType in Attribute.Types:
            return None

        attribute = Attribute(attrType, sanitizeName(name, "Attribute"))
        self.attributes[attribute.name] = attribute
        return attribute

    def getColumn(self, name):
        return self.columns.get(sanitizeName(name, "Column"))

    def getAttribute(self, name):
        return self.attributes.get(sanitizeName(name, "Attribute"))

    def getColumnNames(self, fieldType=None):
        if fieldType is None:
            return list(self.columns.keys())
        return self.getColumnNamesByType(fieldType)

    def getColumnNamesByType(self, fieldType):
        return list(self.columnsByType.get(fieldType, {}).keys())

    def getAttributeNames(self):
        return list(self.attributes.keys())

    def getColumns(self, fieldType=None):
        if fieldType is None:
            return list(self.columns.values())
        return self.getColumnsByType(fieldType)

    def getColumnsByType(self, fieldType):
        return list(self.columnsByType.get(fieldType, {}).values())

    def getAttributes(self):
        return list(self.attributes.values())

    def hasColumn(self, name, fieldType=None):
        if fieldType is None:
            return sanitizeName(name, "Column") in self.columns
        return self.hasColumnOfType(name, fieldType)

    def hasColumnWithType(self, name, fieldType):
        return sanitizeName(name, "Column") in self.getColumnNamesByType(fieldType)

    def hasAttribute(self, name):
        return sanitizeName(name, "Column") in self.getAttributeNames()

    def countColumns(self, fieldType=None):
        if fieldType is None:
            return len(self.columns)
        return self.countColumnsWithType(fieldType)
    
    def countColumnsWithType(self, fieldType):
        return len(self.columnsByType.get(fieldType, {}))

    def countAttributes(self):
        return len(self.attributes)

class Progress(object):
    def __init__(self):
        self.ignored = False
        self.last_date = None
        self.created_date = None
        self.next_date = None
        self.interval = None
        self.growth_level = 0
        self.attempts = 0
        self.correct = 0
        self.incorrect = 0
        self.total_streak = 0
        self.current_streak = 0
        self.position = 0

class Level(object):
    def __init__(self, levelId):
        self.id = levelId
        self.index = 0
        self.title = ""
        self.learnables = collections.OrderedDict()
        self.course = None

    def __iter__(self):
        for learnable in self.learnables.values():
            yield learnable

    def __len__(self):
        return len(self.learnables)
    
    def hasLearnable(self, learnableId):
        return learnableId in self.learnables

    def getLearnable(self, learnableId):
        return self.learnables.get(learnableId)

    def addLearnable(self, learnable):
        self.learnables[learnable.id] = learnable
        learnable.level = self

    def getDirections(self):
        return list(set(map(lambda x: x.direction, self.learnables.values())))

class ColumnData(object):
    def checksum(self):
        return None

class TextColumnData(ColumnData):
    def __init__(self):
        self.values = []
        self.alternatives = []
        self.hiddenAlternatives = []
        self.typingCorrects = []

    def checksum(self):
        hasher = hashlib.blake2b()
        hasher.update(json.dumps([self.values, self.alternatives, self.hiddenAlternatives], sort_keys=True).encode())
        return hasher.hexdigest()

class DownloadableFile(object):
    def __init__(self, remoteUrl=None):
        self.remoteUrl = remoteUrl
        self.localUrl = None

    def isDownloaded(self):
        return bool(self.localUrl)

class MediaColumnData(ColumnData):
    files = []

    def __init__(self, files=[]):
        self.setFiles(files)

    def getFiles(self):
        return self.files

    def setFiles(self, files):
        self.files = list(map(lambda f: f if isinstance(DownloadableFile) else DownloadableFile(f), files))

    def getRemoteUrls(self):
        return [f.remoteUrl for f in self.files]

    def getLocalUrls(self):
        return [f.localUrl for f in self.files]

    def addRemoteUrl(self, url):
        self.files.append(DownloadableFile(url))

    def setRemoteUrls(self, urls):
        self.files = list(map(DownloadableFile, urls))

    def setLocalUrls(self, urls):
        for url, f in zip(urls, self.files):
            f.localUrl = url

    def setLocalUrl(self, remoteUrl, localUrl):
        for f in self.files:
            if f.remoteUrl == remoteUrl:
                f.localUrl = localUrl

    def allDownloaded(self):
        return all([f.isDownloaded() for f in self.files])

    def checksum(self):
        hasher = hashlib.blake2b()
        hasher.update(json.dumps([[f.remoteUrl, f.localUrl] for f in self.files], sort_keys=True).encode())
        return hasher.hexdigest()

def instanceColumnData(fieldType):
    if fieldType == FieldType.Text:
        return TextColumnData()
    else:
        return MediaColumnData()

class AttributeData(ColumnData):
    def __init__(self):
        self.values = []

    def checksum(self):
        hasher = hashlib.blake2b()
        hasher.update(json.dumps(self.values, sort_keys=True).encode())
        return hasher.hexdigest()

class Learnable(object):
    def __init__(self, learnableId):
        self.id = learnableId
        self.identifiers = set([learnableId])

        self.course = None
        self.level = None
        self.direction = None
        self.progress = Progress()

        self.columnData = {}
        self.columnDataByType = {}
        for colType in Column.Types:
            self.columnDataByType[colType] = {}
        self.attributeData = {}

    def checksum(self):
        hasher = hashlib.blake2b()
        hasher.update(json.dumps({k: v.checksum() for k, v in self.columnData.items()}, sort_keys=True).encode())
        hasher.update(json.dumps({k: v.checksum() for k, v in self.attributeData.items()}, sort_keys=True).encode())
        return hasher.hexdigest()

    def getColumnData(self, nameOrColumn, fieldType=None):
        if isinstance(nameOrColumn, Column):
            name = nameOrColumn.name
            fieldType = nameOrColumn.type
        else:
            name = nameOrColumn
        if fieldType:
            return self.columnDataByType.get(fieldType, {}).get(name, instanceColumnData(fieldType))
        return self.columnData.get(name)

    def getAttributeData(self, name):
        return self.attributeData.get(name, AttributeData())

    def setColumnData(self, column, data):
        self.columnDataByType[column.type][column.name] = data
        self.columnData[column.name] = data

    def setAttributeData(self, nameOrAttribute, data):
        if isinstance(nameOrAttribute, Attribute):
            name = nameOrAttribute.name
        else:
            name = nameOrAttribute
        self.attributeData[name] = data

class CourseLoader(object):
    def __init__(self, service):
        self.service = service
        self.observers = []
        self.levelCount = 0
        self.learnableCount = 0

    def registerObserver(self, observer):
        self.observers.append(observer)

    def notify(self, signal, *attrs, **kwargs):
        for observer in self.observers:
            if hasattr(observer, signal):
                getattr(observer, signal)(*attrs, **kwargs)

    def merge_similar_learnables(self, learnables):
        identifiers = set()
        typingCorrects = {}
        for l in learnables:
            identifiers.update(l.identifiers)
            for k, v in l.columnData.items():
                if isinstance(v, TextColumnData) and v.typingCorrects:
                    typingCorrects[k] = v.typingCorrects
        for l in learnables:
            l.identifiers.update(identifiers)
            for k, v in typingCorrects.items():
                l.columnData[k].typingCorrects = v

    def loadCourse(self, courseId):
        course = Course(courseId)

        courseData = self.service.loadCourseData(course.id)

        course.title = sanitizeName(courseData["title"], "Course")
        course.description = courseData["description"]
        self.levelCount = courseData["num_levels"]
        self.learnableCount = courseData["num_learnables"]

        self.notify('levelCountChanged', self.levelCount)
        self.notify('thingCountChanged', self.learnableCount)

        for levelIndex in range(1,self.levelCount+1):
            try:
                level = self.loadLevel(course, levelIndex)
                if level:
                    course.levels.append(level)
            except LevelNotFoundError:
                level = {}
            self.notify('levelLoaded', levelIndex, level)

        for learnables in course.similar_learnables().values():
            if len(learnables) > 1:
                self.merge_similar_learnables(learnables)

        return course

    @staticmethod
    def loadProgress(learnable, data):
        learnable.progress.ignored = data['ignored']
        learnable.progress.last_date = parse_date(data['last_date'])
        learnable.progress.created_date = parse_date(data['created_date'])
        learnable.progress.next_date = parse_date(data['next_date'])
        learnable.progress.interval = data['interval']
        learnable.progress.growth_level = data['growth_level']
        learnable.progress.attempts = data.get('attempts', 0)
        learnable.progress.correct = data.get('correct', 0)
        learnable.progress.incorrect = data.get('attempts', 0) - data.get('correct', 0)
        learnable.progress.total_streak = data['total_streak']
        learnable.progress.current_streak = data['current_streak']
        return learnable.progress

    def loadLevel(self, course, levelIndex):
        levelData = self.service.loadLevelData(course.id, levelIndex)
        
        if levelData.get('code') is not None:
            return None

        level = Level(levelData["session_source_info"]["level_id"])
        level.index = levelData["session_source_info"]["source_sub_index"]
        level.title = sanitizeName(levelData["session_source_info"]["level_name"])
        level.course = course

        for learnableData in levelData["learnables"]:
            learnableId = learnableData['id']
            if course.hasLearnable(learnableId):
                learnable = course.getLearnable(learnableId)
            else:
                learnable = Learnable(learnableId)
                learnable.progress.position = course.getNextPosition()
                learnable.course = course
                learnable.level = level
                for screen in learnableData["screens"].values():
                    if screen['template'] == 'presentation':
                        learnable.direction = Direction(screen['item']['label'], screen['definition']['label'])
                        sides = {
                            'source': screen['item']['label'] if screen['item']['direction'] == 'source' else screen['definition']['label'],
                            'target': screen['item']['label'] if screen['item']['direction'] == 'target' else screen['definition']['label']
                        }
                        for col in itertools.chain([screen['item'], screen['definition'], screen['audio'], screen['video']], screen['visible_info'], screen['hidden_info']):
                            if not col:
                                continue
                            column = course.getColumn(col['label'])
                            if not column:
                                column = course.addColumn(col['kind'], col['label'], sides[col['direction']])
                            if col['kind'] in ['audio', 'image', 'video']:   
                                data = MediaColumnData()
                                data.setRemoteUrls(list(map(lambda x: self.service.toAbsoluteMediaUrl(x['normal']), col['value'])))
                            elif col["kind"] == 'text':
                                data = TextColumnData()
                                data.values = list(map(str.strip, col['value'].split(",")))
                                data.alternatives = list(filter(lambda x: x and not x.startswith("_"), col['alternatives']))
                                data.hiddenAlternatives = list(filter(lambda x: x and x.startswith("_"), col['alternatives']))
                                data.typingCorrects = []
                            learnable.setColumnData(column, data)
                        for attr in screen['attributes']:
                            if not attr:
                                continue
                            attribute = course.getAttribute(attr['label'])
                            if not attribute:
                                attribute = course.addAttribute(FieldType.Text, attr['label'])
                            data = AttributeData()
                            data.values = list(map(str.strip, attr['value'].split(",")))
                            learnable.setAttributeData(attribute, data)
                    elif screen['template'] == 'typing':
                        column = course.getColumn(screen['answer']['label'])
                        if column:
                            learnable.getColumnData(column, FieldType.Text).typingCorrects = list(filter(lambda x: x != '', screen['correct']))
                
                level.addLearnable(learnable)

            for progressData in levelData["progress"]:
                learnable = level.getLearnable(int(progressData['learnable_id']))
                if learnable:
                    self.loadProgress(learnable, progressData)

            self.notify('thingLoaded', learnable)

        return level

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
        self.session = requests.Session()
        self.session.cookies = cookiejar
        retry_strategy = Retry(total=5, backoff_factor=1.0)
        adapter =  requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def getCookie(self, name):
        cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
        return cookies.get(name)

    def isLoggedIn(self):
        response = self.session.get('https://community-courses.memrise.com/v1.23/me/', headers={'Referer': 'https://www.memrise.com/app'})
        return response.status_code == 200

    def login(self, username, password):
        signin_page = self.session.get("https://community-courses.memrise.com/signin")
        signin_soup = bs4.BeautifulSoup(signin_page.content, "html.parser")
        info_json = json.loads(signin_soup.select_one("#__NEXT_DATA__").string)
        client_id = info_json["runtimeConfig"]["OAUTH_CLIENT_ID"]
        signin_data = {
            'username': username,
            'password': password,
            'client_id': client_id,
            'grant_type': 'password'
        }

        obtain_login_token_res = self.session.post('https://community-courses.memrise.com/v1.23/auth/access_token/', json=signin_data)
        if not obtain_login_token_res.ok:
            return False
        token = obtain_login_token_res.json()["access_token"]["access_token"]

        actual_login_res = self.session.get('https://community-courses.memrise.com/v1.23/auth/web/', params={'invalidate_token_after': 'true', 'token': token})

        if not actual_login_res.json()["success"]:
            return False

        return True

    def loadCourse(self, url, observer=None):
        courseLoader = CourseLoader(self)
        if not observer is None:
            courseLoader.registerObserver(observer)
        return courseLoader.loadCourse(self.getCourseIdFromUrl(url))

    def loadCourseData(self, courseId):
        courseUrl = self.getHtmlCourseUrl(courseId)
        response = self.session.get(courseUrl)
        soup = bs4.BeautifulSoup(response.text, 'html.parser')

        data = {
            'title': '',
            'description': '',
            'num_levels': 0,
            'num_learnables': 0,
        }

        found = soup.find('h1', {'class': 'course-name'})
        if found:
            data['title'] = found.string

        found = soup.find('span', {'class': 'course-description'})
        if found:
            data['description'] = found.string

        found = soup.find('div', {'class': 'progress-box-title'})
        if found:
            match = re.search(r'([0-9]+)\s*/\s*([0-9]+)', found.contents[0])
            if match:
                data['num_learnables'] = int(match.group(2))

        levelCount = 0
        if soup.find_all('div', {'class': lambda x: x and 'levels' in x.split()}):
            levelNums = [int(tag.string) for tag in soup.find_all('div', {'class': 'level-index'})]
            if len(levelNums) > 0:
                levelCount = max(levelNums)
        elif soup.find_all('div', {'class': lambda x: x and 'things' in x.split()}):
            levelCount = 1

        if levelCount == 0:
            raise MemriseError("Can't get level count")
        
        data['num_levels'] = levelCount

        return data

    def loadLevelData(self, courseId, levelIndex):
        try:
            level_data = {
                'session_source_id': courseId,
                'session_source_sub_index': levelIndex,
                'session_source_type': 'course_id_and_level_index'
            }
            headers = {
                'X-CSRFToken': self.getCookie('csrftoken'),
                'Referer': self.getHtmlLevelUrl(courseId, levelIndex)
            }
            response = self.session.post(self.getJsonLevelUrl(), json=level_data, headers=headers)
            return response.json()
        except urllib.error.HTTPError as e:
            if e.code == 404 or e.code == 400:
                raise LevelNotFoundError("Level not found: {}".format(levelIndex))
            else:
                raise

    @staticmethod
    def getCourseIdFromUrl(url):
        match = re.match(r'https://community-courses.memrise.com/community/course/(\d+)/.+/', url)
        if not match:
            raise MemriseError("Import failed. Does your URL look like the sample URL above?")
        return int(match.group(1))

    @staticmethod
    def checkCourseUrl(url):
        match = re.match(r'https://community-courses.memrise.com/community/course/\d+/.+/', url)
        return bool(match)

    @staticmethod
    def getHtmlCourseUrl(courseId):
        return 'https://community-courses.memrise.com/community/course/{:d}/'.format(courseId)

    @staticmethod
    def getHtmlLevelUrl(courseId, levelIndex):
        return 'https://community-courses.memrise.com/aprender/preview?course_id={:d}&level_index={:d}'.format(courseId, levelIndex)

    @staticmethod
    def getJsonLevelUrl():
        return "https://community-courses.memrise.com/v1.23/learning_sessions/preview/"

    @staticmethod
    def toAbsoluteMediaUrl(url):
        if not url:
            return url
        # fix wrong urls: /static/xyz should map to https://static.memrise.com/xyz
        url = re.sub(r"^\/static\/", "/", url)
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

        response = self.session.get(url, stream=True)
        with open(fullMediaPath, "wb") as mediaFile:
            for chunk in response.iter_content(chunk_size=1024):
                mediaFile.write(chunk)

        return localName
