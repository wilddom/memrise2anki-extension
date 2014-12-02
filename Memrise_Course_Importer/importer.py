# -*- coding: utf-8 -*-

import memrise, cookielib, os.path, uuid, sys
from anki.media import MediaManager
from aqt import mw
from aqt.qt import *
from functools import partial

def camelize(content):
	return u''.join(x for x in content.title() if x.isalpha())

class MemriseCourseLoader(QObject):
	totalCountChanged = pyqtSignal(int)
	totalLoadedChanged = pyqtSignal(int)
	levelCountChanged = pyqtSignal(int)
	levelsLoadedChanged = pyqtSignal(int)
	thingCountChanged = pyqtSignal(int)
	thingsLoadedChanged = pyqtSignal(int)
	
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
			self.thingsLoaded = 0
			self.levelsLoaded = 0
		
		def levelLoaded(self, levelIndex, level=None):
			self.levelsLoaded += 1
			self.sender.levelsLoadedChanged.emit(self.levelsLoaded)
			self.totalLoaded += 1
			self.sender.totalLoadedChanged.emit(self.totalLoaded)
			
		def downloadMedia(self, thing):
			download = partial(self.sender.memriseService.downloadMedia, skipExisting=self.sender.skipExistingMedia)
			for colName in thing.pool.getImageColumnNames():
				thing.setLocalImageUrls(colName, filter(bool, map(download, thing.getImageUrls(colName))))
			for colName in thing.pool.getAudioColumnNames():
				thing.setLocalAudioUrls(colName, filter(bool, map(download, thing.getAudioUrls(colName))))
			
		def thingLoaded(self, thing):
			if thing and self.sender.downloadMedia:
				self.downloadMedia(thing)
			self.thingsLoaded += 1
			self.sender.thingsLoadedChanged.emit(self.thingsLoaded)
			self.totalLoaded += 1
			self.sender.totalLoadedChanged.emit(self.totalLoaded)
		
		def levelCountChanged(self, levelCount):
			self.sender.levelCountChanged.emit(levelCount)
			self.totalCount += levelCount
			self.sender.totalCountChanged.emit(self.totalCount)
			
		def thingCountChanged(self, thingCount):
			self.sender.thingCountChanged.emit(thingCount)
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
		self.exc_info = (None,None,None)
		self.downloadMedia = True
		self.skipExistingMedia = True
	
	def load(self, url):
		self.url = url
		self.run()
		
	def start(self, url):
		self.url = url
		QThreadPool.globalInstance().start(self.runnable)
	
	def getResult(self):
		return self.result
	
	def getException(self):
		return self.self.exc_info[1]
	
	def getExceptionInfo(self):
		return self.exc_info
	
	def isException(self):
		return isinstance(self.exc_info[1], Exception)
	
	def run(self):
		try:
			course = self.memriseService.loadCourse(self.url, MemriseCourseLoader.Observer(self))
			self.result = course
		except Exception:
			self.exc_info = sys.exc_info()
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

class ModelMappingDialog(QDialog):
	def __init__(self, col):
		super(ModelMappingDialog, self).__init__()
		self.col = col
		self.models = {}
		
		self.setWindowTitle("Note Type")
		layout = QVBoxLayout(self)
		
		layout.addWidget(QLabel("Select note type for newly imported notes:"))
		
		self.modelSelection = QComboBox()
		layout.addWidget(self.modelSelection)
		self.modelSelection.setToolTip("Either a new note type will be created or an existing one can be reused.")
		
		buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)
	
	def __fillModelSelection(self):
		self.modelSelection.clear()
		self.modelSelection.addItem("--- create new ---")
		self.modelSelection.insertSeparator(1)
		for name in sorted(self.col.models.allNames()):
			self.modelSelection.addItem(name)
	
	def __createMemriseModel(self, course, pool):
		mm = self.col.models
				
		name = u"Memrise {}".format(course.title)
		m = mm.new(name)
		
		for colName in pool.getTextColumnNames():
			dfm = mm.newField(colName)
			mm.addField(m, dfm)
			afm = mm.newField(u"{} {}".format(colName, _("Alternatives")))
			mm.addField(m, afm)
			hafm = mm.newField(u"{} {}".format(colName, _("Hidden Alternatives")))
			mm.addField(m, hafm)
			tcfm = mm.newField(u"{} {}".format(colName, _("Typing Corrects")))
			mm.addField(m, tcfm)
		
		for attrName in pool.getAttributeNames():
			fm = mm.newField(attrName)
			mm.addField(m, fm)
			
		for colName in pool.getImageColumnNames():
			fm = mm.newField(colName)
			mm.addField(m, fm)
		
		for colName in pool.getAudioColumnNames():
			fm = mm.newField(colName)
			mm.addField(m, fm)
		
		fm = mm.newField(_("Level"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Thing"))
		mm.addField(m, fm)
		
		front = pool.getTextColumnName(0)
		if pool.hasTextColumnName(camelize(course.source)):
			front = camelize(course.source)
		elif pool.hasTextColumnName(course.source):
			front = course.source
		frontAlternatives = u"{} {}".format(front, _("Alternatives"))
		
		back = pool.getTextColumnName(1)
		if pool.hasTextColumnName(camelize(course.target)):
			back = camelize(course.target)
		elif pool.hasTextColumnName(course.target):
			back = course.target
		backAlternatives = u"{} {}".format(back, _("Alternatives"))
		
		m['css'] += "\n.alts {\n font-size: 14px;\n}"
		m['css'] += "\n.attrs {\n font-style: italic;\n font-size: 14px;\n}"
		
		t = mm.newTemplate(u"{} -> {}".format(camelize(course.source), camelize(course.target)))
		t['qfmt'] = u"{{"+front+u"}}\n{{#"+frontAlternatives+u"}}<br /><span class=\"alts\">{{"+frontAlternatives+u"}}</span>{{/"+frontAlternatives+u"}}\n"
		for colName in pool.getTextColumnNames():
			if not colName in [front, back]:
				t['qfmt'] += u"{{"+colName+u"}}\n"
				altColName = u"{} {}".format(colName, _("Alternatives"))
				t['qfmt'] += u"{{#"+altColName+u"}}<br /><span class=\"alts\">{{"+altColName+u"}}</span>{{/"+altColName+u"}}\n"
		for attrName in pool.getAttributeNames():
			t['qfmt'] += u"{{#"+attrName+u"}}<br /><span class=\"attrs\">({{"+attrName+u"}})</span>{{/"+attrName+"}}\n"
		for colName in pool.getImageColumnNames():
			t['qfmt'] += u"{{#"+colName+u"}}<br />{{"+colName+u"}}{{/"+colName+"}}\n"
		t['afmt'] = u"{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+u"{{"+back+u"}}\n{{#"+backAlternatives+u"}}<br /><span class=\"alts\">{{"+backAlternatives+u"}}</span>{{/"+backAlternatives+u"}}\n"
		for colName in pool.getAudioColumnNames():
			t['afmt'] += u"{{#"+colName+u"}}<div style=\"display:none;\">{{"+colName+u"}}</div>{{/"+colName+"}}\n"
		mm.addTemplate(m, t)
		
		t = mm.newTemplate(u"{} -> {}".format(camelize(course.target), camelize(course.source)))
		t['qfmt'] = u"{{"+back+u"}}\n{{#"+backAlternatives+u"}}<br /><span class=\"alts\">{{"+backAlternatives+u"}}</span>{{/"+backAlternatives+u"}}\n"
		for colName in pool.getTextColumnNames():
			if not colName in [front, back]:
				t['qfmt'] += u"{{"+colName+u"}}\n"
				altColName = u"{} {}".format(colName, _("Alternatives"))
				t['qfmt'] += u"{{#"+altColName+u"}}<br /><span class=\"alts\">{{"+altColName+u"}}</span>{{/"+altColName+u"}}\n"
		for attrName in pool.getAttributeNames():
			t['qfmt'] += u"{{#"+attrName+u"}}<br /><span class=\"attrs\">({{"+attrName+u"}})</span>{{/"+attrName+"}}\n"
		for colName in pool.getAudioColumnNames():
			t['qfmt'] += u"{{#"+colName+u"}}<div style=\"display:none;\">{{"+colName+u"}}</div>{{/"+colName+"}}\n"
		t['afmt'] = u"{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+u"{{"+front+u"}}\n{{#"+frontAlternatives+u"}}<br /><span class=\"alts\">{{"+frontAlternatives+u"}}</span>{{/"+frontAlternatives+u"}}\n"
		for colName in pool.getImageColumnNames():
			t['afmt'] += u"{{#"+colName+u"}}<br />{{"+colName+u"}}{{/"+colName+"}}\n"
		mm.addTemplate(m, t)
		
		return m
	
	def __loadModel(self, thing, deck=None):
		model = self.__createMemriseModel(thing.level.course, thing.pool)
		
		modelStored = self.col.models.byName(model['name'])
		if modelStored:
			if self.col.models.scmhash(modelStored) == self.col.models.scmhash(model):
				model = modelStored
			else:
				model['name'] += u"-{}".format(uuid.uuid4())
			
		if deck and 'mid' in deck:
			deckModel = self.col.models.get(deck['mid'])
			if deckModel and self.col.models.scmhash(deckModel) == self.col.models.scmhash(model):
				model = deckModel
				
		if model and not model['id']:
			self.col.models.add(model)

		return model
	
	def getModel(self, thing, deck):
		if thing.pool.id in self.models:
			return self.models[thing.pool.id]
		
		self.__fillModelSelection()
		self.exec_()
		
		if self.modelSelection.currentIndex() == 0:
			self.models[thing.pool.id] = self.__loadModel(thing, deck)
		else:
			modelName = self.modelSelection.currentText()
			self.models[thing.pool.id] = self.col.models.byName(modelName)
		
		return self.models[thing.pool.id]

class FieldMappingDialog(QDialog):
	def __init__(self, col):
		super(FieldMappingDialog, self).__init__()
		self.col = col
		self.mappings = {}
		
		self.setWindowTitle("Assign Memrise Fields")
		layout = QVBoxLayout(self)
		
		self.label = QLabel("Define the field mapping for the selected note type.")
		layout.addWidget(self.label)
		
		self.grid = QGridLayout()
		layout.addLayout(self.grid)
		
		buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)

	@staticmethod
	def clearLayout(layout):
		while layout.count():
			child = layout.takeAt(0)
			if child.widget() is not None:
				child.widget().deleteLater()
			elif child.layout() is not None:
				FieldMappingDialog.clearLayout(child.layout())

	@staticmethod
	def __findIndexWithData(combobox, predicate):
		for index in range(0, combobox.count()):
			data = combobox.itemData(index)
			if predicate(data):
				return index
		return -1

	def __createModelFieldSelection(self, fieldNames):
		fieldSelection = QComboBox()
		fieldSelection.addItem(u"--- None ---")
		fieldSelection.insertSeparator(1)
		for fieldName in fieldNames:
			fieldSelection.addItem(fieldName)
		return fieldSelection

	def __createMemriseFieldSelection(self, pool):
		fieldSelection = QComboBox()
		fieldSelection.addItem(u"--- None ---")
		fieldSelection.insertSeparator(1)
		for colName in pool.getTextColumnNames():
			fieldSelection.addItem(u"Text: {}".format(colName), {'type': 'text', 'sub': 'value', 'name': colName})
			fieldSelection.addItem(u"{1}: {0}".format(colName, _("Alternatives")), {'type': 'text', 'sub': 'alternatives', 'name': colName})
			fieldSelection.addItem(u"{1}: {0}".format(colName, _("Hidden Alternatives")), {'type': 'text', 'sub': 'hidden_alternatives', 'name': colName})
			fieldSelection.addItem(u"{1}: {0}".format(colName, _("Typing Corrects")), {'type': 'text', 'sub': 'typing_corrects', 'name': colName})
		for colName in pool.getImageColumnNames():
			fieldSelection.addItem(u"Image: {}".format(colName), {'type': 'image', 'name': colName})
		for colName in pool.getAudioColumnNames():
			fieldSelection.addItem(u"Audio: {}".format(colName), {'type': 'audio', 'name': colName})
		for attrName in pool.getAttributeNames():
			fieldSelection.addItem(u"Attribute: {}".format(attrName), {'type': 'attribute', 'name': attrName})
		return fieldSelection

	def __buildGrid(self, pool, model):
		self.clearLayout(self.grid)

		self.grid.addWidget(QLabel("Note type fields:"), 0, 0)
		self.grid.addWidget(QLabel("Memrise fields:"), 0, 1)
		
		def findIndex(data, name):
			if not data:
				return False
			if name == data["name"]:
				return True
			if data["type"] == "text" and data["sub"] == "alternatives" and name == u"{} {}".format(data["name"], _("Alternatives")):
				return True
			if data["type"] == "text" and data["sub"] == "hidden_alternatives" and name == u"{} {}".format(data["name"], _("Hidden Alternatives")):
				return True
			if data["type"] == "text" and data["sub"] == "typing_corrects" and name == u"{} {}".format(data["name"], _("Typing Corrects")):
				return True
			return False
				
		fieldNames = filter(lambda fieldName: not fieldName in [_('Thing'), _('Level')], self.col.models.fieldNames(model))
		poolFieldCount = pool.countTextColumns()*2 + pool.countImageColumns() + pool.countAudioColumns() + pool.countAttributes()
		
		mapping = []
		for index in range(0, max(len(fieldNames), poolFieldCount)):
			modelFieldSelection = self.__createModelFieldSelection(fieldNames)
			self.grid.addWidget(modelFieldSelection, index+1, 0)

			memriseFieldSelection = self.__createMemriseFieldSelection(pool)
			self.grid.addWidget(memriseFieldSelection, index+1, 1)
			
			if index < len(fieldNames):
				modelFieldSelection.setCurrentIndex(index+2)
			
			fieldIndex = self.__findIndexWithData(memriseFieldSelection, partial(findIndex, name=modelFieldSelection.currentText()))
			if fieldIndex >= 0:
				memriseFieldSelection.setCurrentIndex(fieldIndex)
			
			mapping.append((modelFieldSelection, memriseFieldSelection))
		
		return mapping
		
	def getFieldMappings(self, pool, model):
		if pool.id in self.mappings:
			if model['id'] in self.mappings[pool.id]:
				return self.mappings[pool.id][model['id']]
		
		self.label.setText(u'Define the field mapping for the note type "{}".'.format(model["name"]))
		selectionMapping = self.__buildGrid(pool, model)
		self.exec_()
		
		mapping = {}
		for modelFieldSelection, memriseFieldSelection in selectionMapping:
			fieldName = None
			if modelFieldSelection.currentIndex() >= 2:
				fieldName = modelFieldSelection.currentText()
			
			data = None
			if memriseFieldSelection.currentIndex() >= 2:
				data = memriseFieldSelection.itemData(memriseFieldSelection.currentIndex())
			
			if fieldName and data:
				mapping.setdefault(fieldName, []).append(data)
		
		self.mappings.setdefault(pool.id, {})[model['id']] = mapping
		
		return mapping

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
		layout.addWidget(self.downloadMediaCheckBox)
		
		self.skipExistingMediaCheckBox = QCheckBox("Skip download of existing media files")
		layout.addWidget(self.skipExistingMediaCheckBox)
		
		self.downloadMediaCheckBox.stateChanged.connect(self.skipExistingMediaCheckBox.setEnabled)
		self.downloadMediaCheckBox.setChecked(True)
		self.skipExistingMediaCheckBox.setChecked(True)
		
		self.deckSelection = QComboBox()
		self.deckSelection.addItem("--- create new ---")
		self.deckSelection.insertSeparator(1)
		for name in sorted(mw.col.decks.allNames(dyn=False)):
			self.deckSelection.addItem(name)
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
			progressBar.setFormat("Downloading: %p% (%v/%m)")
		
		self.loader = MemriseCourseLoader(memriseService)
		self.loader.thingCountChanged.connect(partial(setTotalCount, self.progressBar))
		self.loader.thingsLoadedChanged.connect(self.progressBar.setValue)
		self.loader.finished.connect(self.importCourse)
		
		self.modelMapper = ModelMappingDialog(mw.col)
		self.fieldMapper = FieldMappingDialog(mw.col)
	
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
		
		fields = [(camelize(course.source), camelize(course.target)), (thing.pool.getTextColumnName(0), thing.pool.getTextColumnName(1)), (_('Front'), _('Back')), ('Front', 'Back')]
		for pair in fields:
			notes = mw.col.findNotes(u'deck:"{}" "{}:{}" "{}:{}"'.format(deckName, pair[0], u"<br/>".join(thing.getDefinitions(0,1)), pair[1], u"<br/>".join(thing.getDefinitions(1, None))))
			if notes:
				return mw.col.getNote(notes[0])
			
		return None

	def getWithSpec(self, thing, spec):
		if spec['type'] == 'text' and spec['sub'] == 'value':
			return self.prepareText(thing.getDefinition(spec['name']))
		elif spec['type'] == 'text' and spec['sub'] == 'alternatives':
			return map(self.prepareText, thing.getAlternatives(spec['name']))
		elif spec['type'] == 'text' and spec['sub'] == 'hidden_alternatives':
			return map(self.prepareText, thing.getHiddenAlternatives(spec['name']))
		elif spec['type'] == 'text' and spec['sub'] == 'typing_corrects':
			return map(self.prepareText, thing.getTypingCorrects(spec['name']))
		elif spec['type'] == 'image':
			return map(self.prepareImage, thing.getLocalImageUrls(spec['name']))
		elif spec['type'] == 'audio':
			return map(self.prepareAudio, thing.getLocalAudioUrls(spec['name']))
		elif spec['type'] == 'attribute':
			return self.prepareText(thing.getAttribute(spec['name']))
		return None
	
	def importCourse(self):
		if self.loader.isException():
			self.buttons.show()
			self.progressBar.hide()
			exc_info = self.loader.getExceptionInfo()
			raise exc_info[0], exc_info[1], exc_info[2]
		
		self.progressBar.setValue(0)
		self.progressBar.setFormat("Importing: %p% (%v/%m)")
		
		course = self.loader.getResult()
		
		noteCache = {}
		
		deck = None
		if self.deckSelection.currentIndex() != 0:
			deck = self.selectDeck(self.deckSelection.currentText(), merge=True)
		else:
			deck = self.selectDeck(course.title, merge=False)
		self.saveDeckUrl(deck, self.courseUrlLineEdit.text())
				
		for level in course:
			tags = self.getLevelTags(len(course), level)
			for thing in level:
				if thing.id in noteCache:
					ankiNote = noteCache[thing.id]
				else:
					ankiNote = self.findExistingNote(deck['name'], course, thing)
				if not ankiNote:
					model = self.modelMapper.getModel(thing, deck)
					self.saveDeckModelRelation(deck, model)
					ankiNote = mw.col.newNote()
				
				mapping = self.fieldMapper.getFieldMappings(thing.pool, ankiNote.model())
				for field, data in mapping.iteritems():
					values = []
					for spec in data:
						value = self.getWithSpec(thing, spec)
						if hasattr(value, '__iter__'):
							if len(value):
								values.extend(value)
						else:
							if value:
								values.append(value)
					ankiNote[field] = u", ".join(values)

				if _('Level') in ankiNote.keys():
					levels = set(filter(bool, map(unicode.strip, ankiNote[_('Level')].split(u','))))
					levels.add(str(level.index))
					ankiNote[_('Level')] = u', '.join(levels)
				
				if _('Thing') in ankiNote.keys():
					ankiNote[_('Thing')] = thing.id
				
				for tag in tags:
					ankiNote.addTag(tag)
					
				if not ankiNote.cards():
					mw.col.addNote(ankiNote)
				ankiNote.flush()
				noteCache[thing.id] = ankiNote
				
				self.progressBar.setValue(self.progressBar.value()+1)
				QApplication.processEvents()
		
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
		self.loader.skipExistingMedia = self.skipExistingMediaCheckBox.isChecked()
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
