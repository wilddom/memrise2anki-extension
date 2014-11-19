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
			thing.imageUrls = filter(None, map(self.sender.memriseService.downloadMedia, thing.imageUrls))
			thing.audioUrls = filter(None, map(self.sender.memriseService.downloadMedia, thing.audioUrls))
			
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

class FieldMappingDialog(QDialog):
	def __init__(self):
		super(FieldMappingDialog, self).__init__()
		self.modelFields = {}
		
		self.setWindowTitle("Assign Memrise Field")
		layout = QVBoxLayout(self)
		
		self.label = QLabel("Assign the memrise field to:")
		layout.addWidget(self.label)
		
		self.fieldSelection = QComboBox()
		layout.addWidget(self.fieldSelection)
		
		buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)

	def __setLabel(self, fieldname):
		self.label.setText(u"Assign the memrise field <b>{}</b> to:".format(fieldname))
	
	def __setFields(self, fieldnames):
		self.fieldSelection.clear()
		self.fieldSelection.addItem("-- ignore --")
		self.fieldSelection.insertSeparator(1)
		for fieldname in fieldnames:
			self.fieldSelection.addItem(fieldname)
		
	def getFieldname(self, note, fieldname, allow=[]):
		if not note.mid in self.modelFields:
			self.modelFields[note.mid] = {}
		
		if fieldname in self.modelFields[note.mid]:
			return self.modelFields[note.mid][fieldname]
		
		if fieldname in note.keys():
			self.modelFields[note.mid][fieldname] = fieldname
			return self.modelFields[note.mid][fieldname]
		
		awailableFields = set(note.keys()) - (set(self.modelFields[note.mid].values()) - set(allow))
		
		self.__setLabel(fieldname)
		self.__setFields(sorted(awailableFields))
		self.exec_()
		
		if self.fieldSelection.currentIndex() == 0:
			self.modelFields[note.mid][fieldname] = None
		else:
			self.modelFields[note.mid][fieldname] = self.fieldSelection.currentText()
		
		return self.modelFields[note.mid][fieldname]
		

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
		deckSelectionTooltip = "<b>Updates a previously downloaded course.</b><br />In order for this to work the field <i>Thing</i> must not be removed or renamed, it is needed to identify existing notes."
		self.deckSelection.setToolTip(deckSelectionTooltip)
		label = QLabel("Update existing deck:")
		label.setToolTip(deckSelectionTooltip)
		layout.addWidget(label)
		layout.addWidget(self.deckSelection)
		self.deckSelection.currentIndexChanged.connect(self.loadDeckUrl)
		
		layout.addWidget(QLabel("Keep in mind that it can take a substantial amount of time to download \nand import your course. Good things come to those who wait!"))
		
		self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
		self.buttons.accepted.connect(self.loadCourse)
		self.buttons.rejected.connect(self.reject)
		okButton = self.buttons.button(QDialogButtonBox.Ok)
		okButton.setEnabled(False)
		layout.addWidget(self.buttons)
		
		def checkUrl(button, predicate, url):
			button.setEnabled(predicate(url))
		self.courseUrlLineEdit.textChanged.connect(partial(checkUrl,okButton,memriseService.checkCourseUrl))
		
		self.progressBar = QProgressBar()
		self.progressBar.hide()
		layout.addWidget(self.progressBar)
		
		def setTotalCount(progressBar, totalCount):
			progressBar.setRange(0, totalCount)
			progressBar.setFormat("%p% (%v/%m)")
		
		self.loader = MemriseCourseLoader(memriseService)
		self.loader.totalCountChanged.connect(partial(setTotalCount, self.progressBar))
		self.loader.totalLoadedChanged.connect(self.progressBar.setValue)
		self.loader.finished.connect(self.importCourse)
		
		self.fieldMapper = FieldMappingDialog()
	
	def prepareTitleTag(self, tag):
		value = u''.join(x for x in tag.title() if x.isalnum())
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
		return u''.join(x for x in content.title() if x.isalpha())
	
	def createMemriseModel(self, col, course):
		mm = col.models
				
		name = u"Memrise {}".format(self.camelize(course.title))
		m = mm.new(name)
		
		source = self.camelize(course.source) or _("Front")
		fm = mm.newField(source)
		mm.addField(m, fm)
		
		target = self.camelize(course.target) or _("Back")
		fm = mm.newField(target)
		mm.addField(m, fm)
		
		sourceAlternatives = u"{} {}".format(source, _("Alternatives"))
		fm = mm.newField(sourceAlternatives)
		mm.addField(m, fm)
		
		targetAlternatives = u"{} {}".format(target, _("Alternatives"))
		fm = mm.newField(targetAlternatives)
		mm.addField(m, fm)
		
		fm = mm.newField(_("Attributes"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Audio"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Image"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Level"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Thing"))
		mm.addField(m, fm)
		
		m['css'] += "\n.alts {\n font-size: 14px;\n}"
		m['css'] += "\n.attrs {\n font-style: italic;\n font-size: 14px;\n}"
		
		t = mm.newTemplate(u"{} -> {}".format(source, target))
		t['qfmt'] = u"{{"+source+u"}}\n"+u"{{#"+sourceAlternatives+u"}}<br /><span class=\"alts\">{{"+sourceAlternatives+u"}}</span>{{/"+sourceAlternatives+u"}}\n"+u"{{#Attributes}}<br /><span class=\"attrs\">({{Attributes}})</span>{{/Attributes}}\n"+u"{{#Image}}<br />{{Image}}{{/Image}}"
		t['afmt'] = u"{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+u"{{"+target+u"}}\n{{#"+targetAlternatives+u"}}<br /><span class=\"alts\">{{"+targetAlternatives+u"}}</span>{{/"+targetAlternatives+u"}}\n{{#Audio}}<div style=\"display:none;\">{{Audio}}</div>{{/Audio}}"
		mm.addTemplate(m, t)
		
		t = mm.newTemplate(u"{} -> {}".format(target, source))
		t['qfmt'] =  u"{{"+target+u"}}\n"+u"{{#"+targetAlternatives+u"}}<br /><span class=\"alts\">{{"+targetAlternatives+u"}}</span>{{/"+targetAlternatives+u"}}\n"+u"{{#Attributes}}<br /><span class=\"attrs\">({{Attributes}})</span>{{/Attributes}}\n"+u"{{#Audio}}<div style=\"display:none;\">{{Audio}}</div>{{/Audio}}"
		t['afmt'] = u"{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+u"{{"+source+u"}}\n{{#"+sourceAlternatives+u"}}<br /><span class=\"alts\">{{"+sourceAlternatives+u"}}</span>{{/"+sourceAlternatives+u"}}\n{{#Image}}<br />{{Image}}{{/Image}}"
		mm.addTemplate(m, t)
		
		return m
	
	def selectModel(self, course, deck=None):
		model = self.createMemriseModel(mw.col, course)
		
		modelStored = mw.col.models.byName(model['name'])
		if modelStored:
			if mw.col.models.scmhash(modelStored) == mw.col.models.scmhash(model):
				model = modelStored
			else:
				model['name'] += u"-{}".format(uuid.uuid4())
			
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
				did = mw.col.decks.id(u"{}-{}".format(name, uuid.uuid4()))
			else:
				did = mw.col.decks.id(name, create=True)
		
		mw.col.decks.select(did)
		return mw.col.decks.get(did)
	
	def loadDeckUrl(self, index):
		did = mw.col.decks.id(self.deckSelection.currentText(), create=False)
		if did:
			deck = mw.col.decks.get(did, default=False)
			url = deck.get("addons", {}).get("memrise", {}).get("url", "")
			if url:
				self.courseUrlLineEdit.setText(url)
	
	def saveDeckUrl(self, deck, url):
		deck.setdefault('addons', {}).setdefault('memrise', {})["url"] = url
		mw.col.decks.save(deck)
		
	def saveDeckModelRelation(self, deck, model):
		deck['mid'] = model['id']
		mw.col.decks.save(deck)
		
		model["did"] = deck["id"]
		mw.col.models.save(model)
	
	def findExistingNote(self, deckName, course, thing):
		notes = mw.col.findNotes(u'deck:"{}" {}:"{}"'.format(deckName, 'Thing', thing.id))
		if notes:
			return mw.col.getNote(notes[0])
		
		fields = [(self.camelize(course.source), self.camelize(course.target)), (_('Front'), _('Back')), ('Front', 'Back')]
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
		self.saveDeckUrl(deck, self.courseUrlLineEdit.text())
		self.saveDeckModelRelation(deck, model)
				
		for level in course:
			tags = self.getLevelTags(len(course), level)
			for thing in level:
				if thing.id in noteCache:
					ankiNote = noteCache[thing.id]
				else:
					ankiNote = self.findExistingNote(deck['name'], course, thing)
					if not ankiNote:
						ankiNote = mw.col.newNote()
					
				frontField = self.fieldMapper.getFieldname(ankiNote, self.camelize(course.source))
				if frontField:
					ankiNote[frontField] = u"<br/>".join(map(self.prepareText, thing.sourceDefinitions))
				
				frontAlternativesField = self.fieldMapper.getFieldname(ankiNote, u"{} {}".format(self.camelize(course.source), _("Alternatives")))
				if frontAlternativesField:
					ankiNote[frontAlternativesField] = u", ".join(map(self.prepareText, thing.sourceAlternatives))
						
				backField = self.fieldMapper.getFieldname(ankiNote, self.camelize(course.target))
				if backField:
					ankiNote[backField] = u"<br/>".join(map(self.prepareText, thing.targetDefinitions))
				
				backAlternativesField = self.fieldMapper.getFieldname(ankiNote, u"{} {}".format(self.camelize(course.target), _("Alternatives")))
				if backAlternativesField:
					ankiNote[backAlternativesField] = u", ".join(map(self.prepareText, thing.targetAlternatives))

				attributesField = self.fieldMapper.getFieldname(ankiNote, _('Attributes'))
				if attributesField:
					ankiNote[attributesField] = u", ".join(map(self.prepareText, thing.attributes))

				if self.downloadMediaCheckBox.isChecked():
					audios = map(self.prepareAudio, thing.audioUrls)
					audioField = self.fieldMapper.getFieldname(ankiNote, _('Audio'), [frontField, backField])
					if audioField:
						if audioField in [frontField, backField]:
							ankiNote[audioField] = u"<br/>".join([ankiNote[audioField]]+audios)
						else:
							ankiNote[audioField] = u'\n'.join(audios)
					
					images = map(self.prepareImage, thing.imageUrls)
					imageField = self.fieldMapper.getFieldname(ankiNote, _('Image'), [frontField, backField])
					if imageField:
						if imageField in [frontField, backField]:
							ankiNote[imageField] = u"<br/>".join([ankiNote[imageField]]+images)
						else:
							ankiNote[imageField] = u'\n'.join(images)

				levelField = self.fieldMapper.getFieldname(ankiNote, _('Level'))
				if levelField:
					levels = set(filter(bool, map(unicode.strip, ankiNote[levelField].split(u','))))
					levels.add(str(level.index))
					ankiNote[levelField] = u', '.join(levels)
				
				if 'Thing' in ankiNote.keys():
					ankiNote['Thing'] = thing.id
				
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
