# -*- coding: utf-8 -*-

import memrise
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
	
	def __init__(self, downloadDirectory):
		super(MemriseCourseLoader, self).__init__()
		self.url = ""
		self.downloadDirectory = downloadDirectory
		self.runnable = MemriseCourseLoader.RunnableWrapper(self)
		self.result = None
		self.error = False
	
	def load(self, url):
		self.url = url
		self.run()
		
	def start(self, url):
		self.url = url
		QThreadPool.globalInstance().start(self.runnable)
		
	def run(self):
		try:
			course = memrise.loadCourse(self.url, self.downloadDirectory)
			self.levelCountChanged.emit(course.levelCount)
			for level in course:
				self.levelLoaded.emit(level.number)
			self.result = course
		except Exception as e:
			self.error = e
		self.finished.emit()

class MemriseImportWidget(QWidget):
	def __init__(self):
		super(MemriseImportWidget, self).__init__()

		# set up the UI, basically
		self.setWindowTitle("Import Memrise Course")
		self.layout = QVBoxLayout(self)
		
		label = QLabel("Enter the home URL of the Memrise course to import\n(e.g. http://www.memrise.com/course/77958/memrise-intro-french/):")
		self.layout.addWidget(label)
		
		self.courseUrlLineEdit = QLineEdit()
		self.layout.addWidget(self.courseUrlLineEdit)
		
		self.createSubdecksCheckBox = QCheckBox("Create a subdeck per level")
		self.layout.addWidget(self.createSubdecksCheckBox)
		
		patienceLabel = QLabel("Keep in mind that it can take a substantial amount of time to download \nand import your course. Good things come to those who wait!")
		self.layout.addWidget(patienceLabel)
		self.importCourseButton = QPushButton("Import course")
		self.importCourseButton.clicked.connect(self.loadCourse)
		self.layout.addWidget(self.importCourseButton)
		
		self.progressBar = QProgressBar()
		self.progressBar.hide()
		self.layout.addWidget(self.progressBar)
		
		self.loader = MemriseCourseLoader(self.getDownloadDirectory())
		self.loader.levelCountChanged.connect(partial(self.progressBar.setRange,0))
		self.loader.levelLoaded.connect(self.progressBar.setValue)
		self.loader.finished.connect(self.importCourse)
		
	def getDownloadDirectory(self):
		return MediaManager(mw.col, None).dir()

	def prepareTitleTag(self, tag):
		value = ''.join(x for x in tag.title() if x.isalnum())
		if value.isdigit():
			return ''
		return value
	
	def prepareLevelTag(self, levelNum, width):
		formatstr = u"Level{:0"+str(width)+"d}"
		return formatstr.format(levelNum)
	
	def getLevelTags(self, levelCount, level):
		tags = [self.prepareLevelTag(level.number, max(3, len(str(levelCount))))]
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
		if self.loader.error:
			raise self.loader.error
		course = self.loader.result
		if not self.createSubdecksCheckBox.checkState():
			self.selectDeck(course.title)
		for level in course:
			if self.createSubdecksCheckBox.checkState():
				self.selectLevelDeck(course.levelCount, level.number, course.title, level.title)
			tags = self.getLevelTags(course.levelCount, level)
			for note in level.notes:
				ankiNote = mw.col.newNote()
				ankiNote[_("Front")] = note.front
				ankiNote[_("Back")] = note.back
				for tag in tags:
					ankiNote.addTag(tag)
				mw.col.addNote(ankiNote)
		
		mw.col.reset()
		mw.reset()
		
		# refresh deck browser so user can see the newly imported deck
		mw.deckBrowser.refresh()
		
		# bye!
		self.hide()
		
	def loadCourse(self):
		self.importCourseButton.hide()
		self.progressBar.show()
		self.progressBar.setValue(0)
		
		courseUrl = self.courseUrlLineEdit.text()
		self.loader.start(courseUrl)

def startCourseImporter():
	mw.memriseCourseImporter = MemriseImportWidget()
	mw.memriseCourseImporter.show()

action = QAction("Import Memrise Course...", mw)
mw.connect(action, SIGNAL("triggered()"), startCourseImporter)
mw.form.menuTools.addAction(action)
