import urllib.request, urllib.error, urllib.parse, http.cookiejar, http.client
import re, time, os.path, json, collections, datetime, functools, uuid, errno, itertools
import bs4
import requests.sessions

def sanitizeName(name, default=""):
    name = re.sub(r"<.*?>", "", name)
    name = re.sub(r"\s\s+", "", name)
    name = re.sub(r"\ufeff", "", name)
    name = name.strip()
    if not name:
        return default
    return name

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

class Field(object):
    Text = 'text'
    Audio = 'audio'
    Image = 'image'
    Video = 'video'
    Mem = 'mem'

    def __init__(self, fieldType, name):
        self.type = fieldType
        self.name = name

class Column(Field):
    Types = [Field.Text, Field.Audio, Field.Image, Field.Video]

    def __init__(self, colType, name, direction):
        super(Column, self).__init__(colType, name)
        self.direction = direction

class Attribute(Field):
    Types = [Field.Text]

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

    def addColumn(self, colType, name, direction):
        if not colType in Column.Types:
            return None

        column = Column(colType, sanitizeName(name, "Column"), direction)
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

    def getColumnNames(self):
        return list(self.columns.keys())

    def getTextColumnNames(self):
        return list(self.columnsByType[Field.Text].keys())

    def getImageColumnNames(self):
        return list(self.columnsByType[Field.Image].keys())

    def getAudioColumnNames(self):
        return list(self.columnsByType[Field.Audio].keys())

    def getVideoColumnNames(self):
        return list(self.columnsByType[Field.Video].keys())

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

    def getVideoColumns(self):
        return list(self.columnsByType[Field.Video].values())

    def getAttributes(self):
        return list(self.attributes.values())

    def hasColumnName(self, name):
        return sanitizeName(name, "Column") in self.columns

    def hasTextColumnName(self, name):
        return sanitizeName(name, "Column") in self.getTextColumnNames()

    def hasImageColumnName(self, name):
        return sanitizeName(name, "Column") in self.getImageColumnNames()

    def hasAudioColumnName(self, name):
        return sanitizeName(name, "Column") in self.getAudioColumnNames()

    def hasVideoColumnName(self, name):
        return sanitizeName(name, "Column") in self.getVideoColumnNames()

    def hasAttributeName(self, name):
        return sanitizeName(name, "Column") in self.getAttributeNames()

    def countColumns(self):
        return len(self.columns)

    def countTextColumns(self):
        return len(self.columnsByType[Field.Text])

    def countImageColumns(self):
        return len(self.columnsByType[Field.Image])

    def countAudioColumns(self):
        return len(self.columnsByType[Field.Audio])

    def countVideoColumns(self):
        return len(self.columnsByType[Field.Video])

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

class Learnable(object):
    def __init__(self, learnableId):
        self.id = learnableId
        
        self.course = None
        self.direction = None

        self.columnData = collections.OrderedDict()
        self.columnDataByType = collections.OrderedDict()
        for colType in Column.Types:
            self.columnDataByType[colType] = collections.OrderedDict()

        self.attributeData = collections.OrderedDict()
        self.progress = Progress()

    def getColumnData(self, nameOrColumn):
        if isinstance(nameOrColumn, Column):
            name = nameOrColumn.name
        else:
            name = nameOrColumn
        return self.columnData[name]

    def getTextColumnData(self, name):
        return self.columnDataByType[Field.Text].get(name, TextColumnData())

    def getAudioColumnData(self, name):
        return self.columnDataByType[Field.Audio].get(name, MediaColumnData())

    def getVideoColumnData(self, name):
        return self.columnDataByType[Field.Video].get(name, MediaColumnData())

    def getImageColumnData(self, name):
        return self.columnDataByType[Field.Image].get(name, MediaColumnData())

    def getAttributeData(self, name):
        return self.attributeData.get(name, AttributeData())

    def setColumnData(self, column, data):
        self.columnDataByType[column.type][column.name] = data
        self.columnData[column.name] = data

    def setTextColumnData(self, name, data):
        self.columnDataByType[Field.Text][name] = data
        self.columnData[name] = data

    def setAudioColumnData(self, name, data):
        self.columnDataByType[Field.Audio][name] = data
        self.columnData[name] = data

    def setVideoColumnData(self, name, data):
        self.columnDataByType[Field.Video][name] = data
        self.columnData[name] = data

    def setImageColumnData(self, name, data):
        self.columnDataByType[Field.Image][name] = data
        self.columnData[name] = data

    def setAttributeData(self, nameOrAttribute, data):
        if isinstance(nameOrAttribute, Attribute):
            name = nameOrAttribute.name
        else:
            name = nameOrAttribute
        self.attributeData[name] = data

    def getDefinitions(self, name):
        return self.getTextColumnData(name).values

    def getAlternatives(self, name):
        return self.getTextColumnData(name).alternatives

    def getHiddenAlternatives(self, name):
        return self.getTextColumnData(name).hiddenAlternatives

    def getTypingCorrects(self, name):
        return self.getTextColumnData(name).typingCorrects

    def getAttributes(self, name):
        return self.getAttributeData(name).values

    def getAudioFiles(self, name):
        return self.getAudioColumnData(name).getFiles()

    def setAudioFiles(self, name, files):
        return self.getAudioColumnData(name).setFiles(files)

    def getVideoFiles(self, name):
        return self.getVideoColumnData(name).getFiles()

    def setVideoFiles(self, name, files):
        return self.getVideoColumnData(name).setFiles(files)

    def getImageFiles(self, name):
        return self.getImageColumnData(name).getFiles()

    def setImageFiles(self, name, files):
        return self.getImageColumnData(name).setFiles(files)

    def getAudioUrls(self, name):
        return self.getAudioColumnData(name).getRemoteUrls()

    def getVideoUrls(self, name):
        return self.getVideoColumnData(name).getRemoteUrls()

    def getImageUrls(self, name):
        return self.getImageColumnData(name).getRemoteUrls()

    def setLocalAudioUrls(self, name, urls):
        self.getAudioColumnData(name).setLocalUrls(urls)

    def getLocalAudioUrls(self, name):
        return self.getAudioColumnData(name).getLocalUrls()

    def setLocalVideoUrls(self, name, urls):
        self.getVideoColumnData(name).setLocalUrls(urls)

    def getLocalVideoUrls(self, name):
        return self.getVideoColumnData(name).getLocalUrls()

    def setLocalImageUrls(self, name, urls):
        self.getImageColumnData(name).setLocalUrls(urls)

    def getLocalImageUrls(self, name):
        return self.getImageColumnData(name).getLocalUrls()

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

        return course

    @staticmethod
    def loadProgress(learnable, data):
        learnable.progress.ignored = data['ignored']
        learnable.progress.last_date = datetime.datetime.fromisoformat(data['last_date']).replace(tzinfo=datetime.UTC)
        learnable.progress.created_date = datetime.datetime.fromisoformat(data['created_date']).replace(tzinfo=datetime.UTC)
        learnable.progress.next_date = datetime.datetime.fromisoformat(data['next_date']).replace(tzinfo=datetime.UTC)
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
                for screen in learnableData["screens"].values():
                    if screen['template'] == 'presentation':
                        learnable.direction = Direction(screen['item']['label'], screen['definition']['label'])
                        for col in itertools.chain([screen['item'], screen['definition'], screen['audio'], screen['video']], screen['visible_info'], screen['hidden_info']):
                            if not col:
                                continue
                            column = course.getColumn(col['label'])
                            if not column:
                                column = course.addColumn(col['kind'], col['label'], col['direction'])
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
                                attribute = course.addAttribute(Field.Text, attr['label'])
                            data = AttributeData()
                            data.values = list(map(str.strip, attr['value'].split(",")))
                            learnable.setAttributeData(attribute, data)
                    elif screen['template'] == 'typing':
                        column = course.getColumn(screen['answer']['label'])
                        if column:
                            learnable.getColumnData(column).typingCorrects = list(filter(lambda x: x != '', screen['correct']))
                
                level.addLearnable(learnable)

            for progressData in levelData["progress"]:
                learnable = level.getLearnable(int(progressData['learnable_id']))
                if learnable:
                    self.loadProgress(learnable, progressData)

            self.notify('thingLoaded', learnable)

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
        return self.do_open_wrapped(http.client.HTTPSConnection, req, context=self._context)

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
        self.session = requests.Session()
        self.session.cookies = cookiejar

    def openWithRetry(self, url, maxAttempts=5, attempt=1):
        try:
            return self.opener.open(url)
        except urllib.error.URLError as e:
            if e.errno == errno.ECONNRESET and maxAttempts > attempt:
                time.sleep(1.0*attempt)
                return self.openWithRetry(url, maxAttempts, attempt+1)
            else:
                raise
        except http.client.BadStatusLine:
            # not clear why this error occurs (seemingly randomly),
            # so I regret that all we can do is wait and retry.
            if maxAttempts > attempt:
                time.sleep(0.1)
                return self.openWithRetry(url, maxAttempts, attempt+1)
            else:
                raise

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

        data = self.openWithRetry(url).read()
        with open(fullMediaPath, "wb") as mediaFile:
            mediaFile.write(data)

        return localName
