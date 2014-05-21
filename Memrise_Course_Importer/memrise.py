import urllib2, cookielib, urllib, httplib, urlparse, re, time, os.path
import uuid
import BeautifulSoup

class Note(object):
    def __init__(self, front="", back=""):
        self.front = front
        self.back = back

class Level(object):
    def __init__(self):
        self.url = ""
        self.number = 0
        self.title = ""
        self.notes = []

class Course(object):
    def __init__(self, service):
        self.service = service
        self.url = ""
        self.title = ""
        self.levelCount = 0
        self.levelTitles = []
        self.levels = []

    def __iter__(self):
        if len(self.levels) == self.levelCount:
            for level in self.levels:
                yield level
        else:
            for levelNumber, levelTitle in enumerate(self.levelTitles, start=1):
                level = Level()
                level.url = self.service.getLevelUrl(self.url, levelNumber)
                level.number = levelNumber
                level.title = levelTitle
                level.notes = self.service.loadLevelNotes(level.url)
                self.levels.append(level)
                yield level
                
    def __len__(self):
        return self.levelCount

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
    
    def loadCourse(self, url):
        url = self.checkCourseUrl(url)
        
        response = self.downloadWithRetry(url, 3)
        soup = BeautifulSoup.BeautifulSoup(response.read())
        
        course = Course(self)
        course.url = url
        course.title = soup.find("h1", "course-name").string.strip()
        course.levelTitles = map(lambda x: x.string.strip(), soup.findAll("div", "level-title"))
        course.levelCount = len(course.levelTitles)
        
        return course

    def checkCourseUrl(self, url):
        # make sure the url given actually looks like a course home url
        if re.match('http://www.memrise.com/course/\d+/.+/', url) == None:
            raise Exception("Import failed. Does your URL look like the sample URL above?")
        return url

    def getLevelUrl(self, courseUrl, levelNum):
        courseUrl = self.checkCourseUrl(courseUrl)
        return u"{:s}{:d}".format(courseUrl, levelNum)
    
    def downloadMedia(self, url):
        if not self.downloadDirectory:
            return url
        
        # Replace links to images and audio on the Memrise servers
        # by downloading the content to the user's media dir
        memrisePath = urlparse.urlparse(url).path
        contentExtension = os.path.splitext(memrisePath)[1]
        localName = "{:s}{:s}".format(uuid.uuid4(), contentExtension)
        fullMediaPath = os.path.join(self.downloadDirectory, localName)
        mediaFile = open(fullMediaPath, "wb")
        mediaFile.write(self.downloadWithRetry(url, 3).read())
        mediaFile.close()
        return localName
    
    def prepareText(self, content):
        return u'{:s}'.format(content.strip())
    
    def prepareAudio(self, content):
        return u'[sound:{:s}]'.format(self.downloadMedia(content))
    
    def prepareImage(self, content):
        return u'<img src="{:s}">'.format(self.downloadMedia(content))

    def loadLevelNotes(self, url):
        soup = BeautifulSoup.BeautifulSoup(self.downloadWithRetry(url, 3).read())
    
        # this looked a lot nicer when I thought I could use BS4 (w/ css selectors)
        # unfortunately Anki is still packaging BS3 so it's a little rougher
        # find the words in column a, whether they be text, image or audio
        colAParents = map(lambda x: x.find("div"), soup.findAll("div", "col_a"))
        colA = map(lambda x: self.prepareText(x.string), filter(lambda p: p["class"] == "text", colAParents))
        colA.extend(map(lambda x: self.prepareImage(x.find("img")["src"]), filter(lambda p: p["class"] == "image", colAParents)))
        colA.extend(map(lambda x: self.prepareAudio(x.find("a")["href"]), filter(lambda p: p["class"] == "audio", colAParents)))
        
        # same deal for column b
        colBParents = map(lambda x: x.find("div"), soup.findAll("div", "col_b"))
        colB = map(lambda x: self.prepareText(x.string), filter(lambda p: p["class"] == "text", colBParents))
        colB.extend(map(lambda x: self.prepareImage(x.find("img")["src"]), filter(lambda p: p["class"] == "image", colBParents)))
        colB.extend(map(lambda x: self.prepareAudio(x.find("a")["href"]), filter(lambda p: p["class"] == "audio", colBParents)))
        
        # pair the "fronts" and "backs" of the notes up
        # this is actually the reverse of what you might expect
        # the content in column A on memrise is typically what you're
        # expected to *produce*, so it goes on the back of the note
        notes = []
        for a, b in zip(colA, colB):
            notes.append(Note(front=b, back=a))
        return notes

