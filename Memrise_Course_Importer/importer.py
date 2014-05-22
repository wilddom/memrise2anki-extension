# -*- coding: utf-8 -*-

import memrise, cookielib, os.path
from anki.media import MediaManager
from anki.stdmodels import addBasicModel
from aqt import mw
from aqt.qt import *
from functools import partial

class MemriseCourseLoader(QObject):
	levelCountChanged = pyqtSignal(int)
	levelLoaded = pyqtSignal(int)
	finished = pyqtSignal()
	
	class RunnableWrapper(QRunnable):
		def __init__(self, task):
			super(MemriseCourseLoader.RunnableWrapper, self).__init__()
			self.task = task
		def run(self):
			self.task.run()
	
	def __init__(self, memriseService):
		super(MemriseCourseLoader, self).__init__()
		self.memriseService = memriseService
		self.url = ""
		self.runnable = MemriseCourseLoader.RunnableWrapper(self)
		self.result = None
		self.error = False
	
	def load(self, url):
		self.url = url
		self.run()
		
	def start(self, url):
		self.url = url
		QThreadPool.globalInstance().start(self.runnable)
		
	
	def getResult(self):
		return self.result
	
	def getError(self):
		return self.error
	
	def isError(self):
		return isinstance(self.error, Exception)
	
	def run(self):
		try:
			course = self.memriseService.loadCourse(self.url)
			self.levelCountChanged.emit(course.levelCount)
			for level in course:
				self.levelLoaded.emit(level.number)
			self.result = course
		except Exception as e:
			self.error = e
		self.finished.emit()

class MemriseLoginDialog(QDialog):
	def __init__(self, memriseService):
		super(MemriseLoginDialog, self).__init__()
		self.memriseService = memriseService
		
		self.setWindowTitle("Memrise Login")
		
		layout = QVBoxLayout(self)
		
		innerLayout = QGridLayout()
		
		innerLayout.addWidget(QLabel("Username:"),0,0)
		self.usernameLineEdit = QLineEdit()
		innerLayout.addWidget(self.usernameLineEdit,0,1)
		
		innerLayout.addWidget(QLabel("Password:"),1,0)
		self.passwordLineEdit = QLineEdit()
		self.passwordLineEdit.setEchoMode(QLineEdit.Password)
		innerLayout.addWidget(self.passwordLineEdit,1,1)
		
		layout.addLayout(innerLayout)
		
		buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
	
	def accept(self):
		if self.memriseService.login(self.usernameLineEdit.text(),self.passwordLineEdit.text()):
			super(MemriseLoginDialog, self).accept()
		else:
			msgBox = QMessageBox()
			msgBox.setWindowTitle("Login")
			msgBox.setText("Invalid credentials")
			msgBox.exec_();
		
	def reject(self):
		super(MemriseLoginDialog, self).reject()

	
	@staticmethod
	def login(memriseService):
		dialog = MemriseLoginDialog(memriseService)
		return dialog.exec_() == QDialog.Accepted

class MemriseImportDialog(QDialog):
	def __init__(self, memriseService):
		super(MemriseImportDialog, self).__init__()

		# set up the UI, basically
		self.setWindowTitle("Import Memrise Course")
		layout = QVBoxLayout(self)
		
		layout.addWidget(QLabel("Enter the home URL of the Memrise course to import\n(e.g. http://www.memrise.com/course/77958/memrise-intro-french/):"))
		
		self.courseUrlLineEdit = QLineEdit()
		layout.addWidget(self.courseUrlLineEdit)
		
		self.createSubdecksCheckBox = QCheckBox("Create a subdeck per level")
		layout.addWidget(self.createSubdecksCheckBox)
		layout.addWidget(QLabel("Minimal level tag width filled width zeros (e.g. 3 results in Level001)"))
		self.minimalLevelTagWidthSpinBox = QSpinBox()
		self.minimalLevelTagWidthSpinBox.setMinimum(1)
		self.minimalLevelTagWidthSpinBox.setMaximum(9)
		self.minimalLevelTagWidthSpinBox.setValue(3)
		layout.addWidget(self.minimalLevelTagWidthSpinBox)
		
		layout.addWidget(QLabel("Keep in mind that it can take a substantial amount of time to download \nand import your course. Good things come to those who wait!"))
		
		self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
		self.buttons.accepted.connect(self.loadCourse)
		self.buttons.rejected.connect(self.reject)
		layout.addWidget(self.buttons)
		
		self.progressBar = QProgressBar()
		self.progressBar.hide()
		layout.addWidget(self.progressBar)
		
		self.loader = MemriseCourseLoader(memriseService)
		self.loader.levelCountChanged.connect(partial(self.progressBar.setRange,0))
		self.loader.levelLoaded.connect(self.progressBar.setValue)
		self.loader.finished.connect(self.importCourse)

	def prepareTitleTag(self, tag):
		value = ''.join(x for x in tag.title() if x.isalnum())
		if value.isdigit():
			return ''
		return value
	
	def prepareLevelTag(self, levelNum, width):
		formatstr = u"Level{:0"+str(width)+"d}"
		return formatstr.format(levelNum)
	
	def getLevelTags(self, levelCount, level):
		tags = [self.prepareLevelTag(level.number, max(self.minimalLevelTagWidthSpinBox.value(), len(str(levelCount))))]
		titleTag = self.prepareTitleTag(level.title)
		if titleTag:
			tags.append(titleTag)
		return tags
	
	def selectLevelDeck(self, levelCount, levelNum, courseTitle, levelTitle):
		zeroCount = len(str(levelCount))
		deckTitle = u"{:s}::Level {:s}: {:s}".format(courseTitle, str(levelNum).zfill(zeroCount), levelTitle) 
		self.selectDeck(deckTitle)
	
	def selectDeck(self, deckTitle):
		# load or create Basic Note Type
		model = mw.col.models.byName(_("Basic"))
		if model is None:
			model = mw.col.models.byName("Basic")
		if model is None:
			model = addBasicModel(mw.col)
		
		# create deck and set note type
		did = mw.col.decks.id(deckTitle)
		deck = mw.col.decks.get(did)
		deck['mid'] = model['id']
		mw.col.decks.save(deck)
		
		# assign new deck to custom model
		model["did"] = deck["id"]
		mw.col.models.save(model)
		
		# select deck and model
		mw.col.decks.select(did)
		mw.col.models.setCurrent(model)
		
	def importCourse(self):
		if self.loader.isError():
			self.buttons.show()
			self.progressBar.hide()
			raise self.loader.getError()
		
		course = self.loader.getResult()
		if not self.createSubdecksCheckBox.checkState():
			self.selectDeck(course.title)
		for level in course:
			if self.createSubdecksCheckBox.checkState():
				self.selectLevelDeck(course.levelCount, level.number, course.title, level.title)
			tags = self.getLevelTags(course.levelCount, level)
			for note in level.notes:
				ankiNote = mw.col.newNote()
				front = "Front"
				if not front in ankiNote.keys():
					front = _(front)
				ankiNote[front] = note.front
				back = "Back"
				if not back in ankiNote.keys():
					back = _(back)
				ankiNote[back] = note.back
				for tag in tags:
					ankiNote.addTag(tag)
				mw.col.addNote(ankiNote)
		
		mw.col.reset()
		mw.reset()
		
		# refresh deck browser so user can see the newly imported deck
		mw.deckBrowser.refresh()
		
		self.accept()
		
	def loadCourse(self):
		self.buttons.hide()
		self.progressBar.show()
		self.progressBar.setValue(0)
		
		courseUrl = self.courseUrlLineEdit.text()
		self.loader.start(courseUrl)

def startCourseImporter():
	downloadDirectory = MediaManager(mw.col, None).dir()
	cookiefilename = os.path.join(mw.pm.profileFolder(), 'memrise.cookies')
	cookiejar = cookielib.MozillaCookieJar(cookiefilename)
	if os.path.isfile(cookiefilename):
		cookiejar.load()
	memriseService = memrise.Service(downloadDirectory, cookiejar)
	if memriseService.isLoggedIn() or MemriseLoginDialog.login(memriseService):
		cookiejar.save()
		memriseCourseImporter = MemriseImportDialog(memriseService)
		memriseCourseImporter.exec_()

action = QAction("Import Memrise Course...", mw)
mw.connect(action, SIGNAL("triggered()"), startCourseImporter)
mw.form.menuTools.addAction(action)
