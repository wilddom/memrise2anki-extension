# -*- coding: utf-8 -*-

import memrise, cookielib, os.path, uuid
from anki.media import MediaManager
from aqt import mw
from aqt.qt import *
from functools import partial

class MemriseCourseLoader(QObject):
	totalCountChanged = pyqtSignal(int)
	totalLoadedChanged = pyqtSignal(int)
	finished = pyqtSignal()
	
	class RunnableWrapper(QRunnable):
		def __init__(self, task):
			super(MemriseCourseLoader.RunnableWrapper, self).__init__()
			self.task = task
		def run(self):
			self.task.run()
			
	class Observer(object):
		def __init__(self, sender):
			self.sender = sender
			self.totalCount = 0
			self.totalLoaded = 0
		
		def levelLoaded(self, levelIndex, level=None):
			self.totalLoaded += 1
			self.sender.totalLoadedChanged.emit(self.totalLoaded)
			
		def downloadMedia(self, thing):
			thing.imageUrls = map(self.sender.memriseService.downloadMedia, thing.imageUrls)
			thing.audioUrls = map(self.sender.memriseService.downloadMedia, thing.audioUrls)
			
		def thingLoaded(self, thing):
			if thing and self.sender.downloadMedia:
				self.downloadMedia(thing)
			self.totalLoaded += 1
			self.sender.totalLoadedChanged.emit(self.totalLoaded)
		
		def levelCountChanged(self, levelCount):
			self.totalCount += levelCount
			self.sender.totalCountChanged.emit(self.totalCount)
			
		def thingCountChanged(self, thingCount):
			self.totalCount += thingCount
			self.sender.totalCountChanged.emit(self.totalCount)
		
		def __getattr__(self, attr):
			if hasattr(self.sender, attr):
				signal = getattr(self.sender, attr)
				if hasattr(signal, 'emit'):
					return getattr(signal, 'emit')
	
	def __init__(self, memriseService):
		super(MemriseCourseLoader, self).__init__()
		self.memriseService = memriseService
		self.url = ""
		self.runnable = MemriseCourseLoader.RunnableWrapper(self)
		self.result = None
		self.error = False
		self.downloadMedia = True
	
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
			course = self.memriseService.loadCourse(self.url, MemriseCourseLoader.Observer(self))
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
		
		layout.addWidget(QLabel("Minimal level tag width filled width zeros (e.g. 3 results in Level001):"))
		self.minimalLevelTagWidthSpinBox = QSpinBox()
		self.minimalLevelTagWidthSpinBox.setMinimum(1)
		self.minimalLevelTagWidthSpinBox.setMaximum(9)
		self.minimalLevelTagWidthSpinBox.setValue(2)
		layout.addWidget(self.minimalLevelTagWidthSpinBox)
		
		self.downloadMediaCheckBox = QCheckBox("Download media files")
		self.downloadMediaCheckBox.setChecked(True)
		layout.addWidget(self.downloadMediaCheckBox)
		
		self.deckSelection = QComboBox()
		self.deckSelection.addItem("")
		for name in sorted(mw.col.decks.allNames(dyn=False)):
			self.deckSelection.addItem(name)
		self.deckSelection.setCurrentIndex(0)
		layout.addWidget(QLabel("Update existing deck:"))
		layout.addWidget(self.deckSelection)
		
		layout.addWidget(QLabel("Keep in mind that it can take a substantial amount of time to download \nand import your course. Good things come to those who wait!"))
		
		self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
		self.buttons.accepted.connect(self.loadCourse)
		self.buttons.rejected.connect(self.reject)
		layout.addWidget(self.buttons)
		
		self.progressBar = QProgressBar()
		self.progressBar.hide()
		layout.addWidget(self.progressBar)
		
		self.loader = MemriseCourseLoader(memriseService)
		self.loader.totalCountChanged.connect(partial(self.progressBar.setRange,0))
		self.loader.totalLoadedChanged.connect(self.progressBar.setValue)
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
		tags = [self.prepareLevelTag(level.index, max(self.minimalLevelTagWidthSpinBox.value(), len(str(levelCount))))]
		titleTag = self.prepareTitleTag(level.title)
		if titleTag:
			tags.append(titleTag)
		return tags
		
	@staticmethod
	def prepareText(content):
		return u'{:s}'.format(content.strip())
	
	@staticmethod
	def prepareAudio(content):
		return u'[sound:{:s}]'.format(content)
	
	@staticmethod
	def prepareImage(content):
		return u'<img src="{:s}">'.format(content)
	
	@staticmethod
	def camelize(content):
		return ''.join(x for x in content.title() if x.isalpha())
	
	def createMemriseModel(self, col, course):
		mm = col.models
				
		name = "Memrise {}".format(self.camelize(course.title))
		m = mm.new(name)
		
		source = self.camelize(course.source) or _("Front")
		fm = mm.newField(source)
		mm.addField(m, fm)
		
		target = self.camelize(course.target) or _("Back")
		fm = mm.newField(target)
		mm.addField(m, fm)
		
		sourceAlternatives = "{} {}".format(source, _("Alternatives"))
		fm = mm.newField(sourceAlternatives)
		mm.addField(m, fm)
		
		targetAlternatives = "{} {}".format(target, _("Alternatives"))
		fm = mm.newField(targetAlternatives)
		mm.addField(m, fm)
		
		fm = mm.newField(_("Audio"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Image"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Level"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Thing"))
		mm.addField(m, fm)
		
		m['css'] += "\n.alts {\n font-style: italic;\n font-size: 14px;\n}"
		
		t = mm.newTemplate("{} -> {}".format(source, target))
		t['qfmt'] = "{{"+source+"}}\n{{#"+sourceAlternatives+"}}<br /><span class=\"alts\">{{"+sourceAlternatives+"}}</span>{{/"+sourceAlternatives+"}}\n{{#Image}}<br />{{Image}}{{/Image}}"
		t['afmt'] = "{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+"{{"+target+"}}\n{{#"+targetAlternatives+"}}<br /><span class=\"alts\">{{"+targetAlternatives+"}}</span>{{/"+targetAlternatives+"}}\n{{#Audio}}<div style=\"display:none;\">{{Audio}}</div>{{/Audio}}"
		mm.addTemplate(m, t)
		
		t = mm.newTemplate("{} -> {}".format(target, source))
		t['qfmt'] =  "{{"+target+"}}\n{{#"+targetAlternatives+"}}<br /><span class=\"alts\">{{"+targetAlternatives+"}}</span>{{/"+targetAlternatives+"}}\n{{#Audio}}<div style=\"display:none;\">{{Audio}}</div>{{/Audio}}"
		t['afmt'] = "{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+"{{"+source+"}}\n{{#"+sourceAlternatives+"}}<br /><span class=\"alts\">{{"+sourceAlternatives+"}}</span>{{/"+sourceAlternatives+"}}\n{{#Image}}<br />{{Image}}{{/Image}}"
		mm.addTemplate(m, t)
		
		return m
	
	def selectModel(self, course, deck=None):
		model = self.createMemriseModel(mw.col, course)
		
		modelStored = mw.col.models.byName(model['name'])
		if modelStored:
			if mw.col.models.scmhash(modelStored) == mw.col.models.scmhash(model):
				model = modelStored
			else:
				model['name'] += "-{}".format(uuid.uuid4())
			
		if deck and 'mid' in deck:
			deckModel = mw.col.models.get(deck['mid'])
			if deckModel and mw.col.models.scmhash(deckModel) == mw.col.models.scmhash(model):
				model = deckModel
				
		if model and not model['id']:
			mw.col.models.add(model)

		mw.col.models.setCurrent(model)
		return model
	
	def selectDeck(self, name, merge=False):
		did = mw.col.decks.id(name, create=False)
		if not merge:
			if did:
				did = mw.col.decks.id("{}-{}".format(name, uuid.uuid4()))
			else:
				did = mw.col.decks.id(name, create=True)
		
		mw.col.decks.select(did)
		return mw.col.decks.get(did)
		
	def saveDeckModelRelation(self, deck, model):
		deck['mid'] = model['id']
		mw.col.decks.save(deck)
		
		model["did"] = deck["id"]
		mw.col.models.save(model)
	
	@staticmethod
	def findField(note, names):
		for name in names:
			if name in note.keys():
				return name
		return None
	
	def getNote(self, deckName, course, thing):
		notes = mw.col.findNotes(u'deck:"{}" {}:"{}"'.format(deckName, _('Thing'), thing.id))
		if notes:
			return mw.col.getNote(notes[0])

		fields = [(self.camelize(course.source), self.camelize(course.target)), (_('Front'), _('Back')), ('Front', 'Back')]

		for pair in fields:
			notes = mw.col.findNotes(u'deck:"{}" "{}:{}"'.format(deckName, pair[0], u"<br/>".join(thing.sourceDefinitions)))
			if len(notes) == 1:
				return mw.col.getNote(notes[0])

		for pair in fields:
			notes = mw.col.findNotes(u'deck:"{}" "{}:{}" "{}:{}"'.format(deckName, pair[0], u"<br/>".join(thing.sourceDefinitions), pair[1], u"<br/>".join(thing.targetDefinitions)))
			if notes:
				return mw.col.getNote(notes[0])
			
		return None
	
	def importCourse(self):
		if self.loader.isError():
			self.buttons.show()
			self.progressBar.hide()
			raise self.loader.getError()
		
		course = self.loader.getResult()
		
		noteCache = {}
		
		deck = None
		if self.deckSelection.currentIndex() != 0:
			deck = self.selectDeck(self.deckSelection.currentText(), merge=True)
		else:
			deck = self.selectDeck(course.title, merge=False)
		model = self.selectModel(course, deck)
		self.saveDeckModelRelation(deck, model)
				
		for level in course:
			tags = self.getLevelTags(len(course), level)
			for thing in level:
				if thing.id in noteCache:
					ankiNote = noteCache[thing.id]
				else:
					ankiNote = self.getNote(deck['name'], course, thing)
					if not ankiNote:
						ankiNote = mw.col.newNote()
					
				front = self.findField(ankiNote, [self.camelize(course.source), _('Front'), 'Front'])
				if not front:
					front = mw.col.models.fieldNames(ankiNote.model())[0]
				ankiNote[front] = u"<br/>".join(map(self.prepareText, thing.sourceDefinitions))
				
				frontAlternatives = u"{} {}".format(front, "Alternatives")
				if frontAlternatives in ankiNote:
					ankiNote[frontAlternatives] = u", ".join(map(self.prepareText, thing.sourceAlternatives))
					
				content = map(self.prepareText, thing.targetDefinitions)
				if self.downloadMediaCheckBox.isChecked():
					audio = map(self.prepareAudio, thing.audioUrls)
					if _('Audio') in ankiNote:
						ankiNote[_('Audio')] = u'\n'.join(audio)
					else:
						content += audio
					
					image = map(self.prepareImage, thing.imageUrls)
					if _('Image') in ankiNote:
						ankiNote[_('Image')] = u'\n'.join(image)
					else:
						content += image
						
				back = self.findField(ankiNote, [self.camelize(course.target), _('Back'), 'Back'])
				if not back:
					back = mw.col.models.fieldNames(ankiNote.model())[1]
				ankiNote[back] = u"<br/>".join(content)
				
				backAlternatives = u"{} {}".format(back, "Alternatives")
				if backAlternatives in ankiNote:
					ankiNote[backAlternatives] = u", ".join(map(self.prepareText, thing.targetAlternatives))

				if _('Level') in ankiNote:
					levels = set(filter(bool, map(unicode.strip, ankiNote[_('Level')].split(u','))))
					levels.add(str(level.index))
					ankiNote[_('Level')] = u', '.join(levels)
				
				if _('Thing') in ankiNote:
					ankiNote[_('Thing')] = thing.id
					
				for tag in tags:
					ankiNote.addTag(tag)
					
				if not ankiNote.cards():
					mw.col.addNote(ankiNote)
				ankiNote.flush()
				noteCache[thing.id] = ankiNote
		
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
		self.loader.downloadMedia = self.downloadMediaCheckBox.isChecked()
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
