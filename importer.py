# -*- coding: utf-8 -*-

import http.cookiejar, os.path, uuid, sys, datetime, re
import bs4
from anki.media import MediaManager
from aqt import mw
from aqt.qt import *
from functools import partial
from . import memrise, oembed

def camelize(content):
	return ''.join(x for x in content.title() if x.isalpha())

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
			for colName in thing.pool.getImageColumnNames():
				for image in [f for f in thing.getImageFiles(colName) if not f.isDownloaded()]:
					image.localUrl = self.sender.download(image.remoteUrl)
			for colName in thing.pool.getAudioColumnNames():
				for audio in [f for f in thing.getAudioFiles(colName) if not f.isDownloaded()]:
					audio.localUrl = self.sender.download(audio.remoteUrl)
		
		def downloadMems(self, thing):
			for mem in list(thing.pool.mems.getMems(thing).values()):
				for image in [f for f in mem.images if not f.isDownloaded()]:
					image.localUrl = self.sender.download(image.remoteUrl)
					if image.isDownloaded():
						mem.text = mem.text.replace(image.remoteUrl, image.localUrl)
				
				if self.sender.embedMemsOnlineMedia:
					soup = bs4.BeautifulSoup(mem.text)
					for link in soup.find_all("a", {"class": "embed"}):
						embedCode = oembed.loadEmbedCode(link.get("href"))
						if embedCode:
							link.replaceWith(bs4.BeautifulSoup(embedCode))
							mem.text = str(soup)
			
		def thingLoaded(self, thing):
			if thing and self.sender.downloadMedia:
				self.downloadMedia(thing)
			if thing and self.sender.downloadMems:
				self.downloadMems(thing)
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
		self.result = None
		self.exc_info = (None,None,None)
		self.downloadMedia = True
		self.skipExistingMedia = True
		self.downloadMems = True
		self.embedMemsOnlineMedia = False
		self.askerFunction = None
	
	def download(self, url):
		import urllib.request, urllib.error, urllib.parse
		while True:
			try:
				return self.memriseService.downloadMedia(url, skipExisting=self.skipExistingMedia)
			except (urllib.error.HTTPError, urllib.error.URLError) as e:
				if callable(self.askerFunction) and hasattr(self.askerFunction, '__self__'):
					action = QMetaObject.invokeMethod(self.askerFunction.__self__, self.askerFunction.__name__, Qt.BlockingQueuedConnection, Q_RETURN_ARG(str), Q_ARG(str, url), Q_ARG(str, str(e)), Q_ARG(str, url))
					if action == "ignore":
						return None
					elif action == "abort":
						raise e
				else:
					raise e
	
	def load(self, url):
		self.url = url
		self.run()
		
	def start(self, url):
		self.url = url
		self.runnable = MemriseCourseLoader.RunnableWrapper(self)
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
		self.result = None
		self.exc_info = (None,None,None)
		try:
			course = self.memriseService.loadCourse(self.url, MemriseCourseLoader.Observer(self))
			self.result = course
		except Exception:
			self.exc_info = sys.exc_info()
		self.finished.emit()

class DownloadFailedBox(QMessageBox):
	def __init__(self):
		super(DownloadFailedBox, self).__init__()
		
		self.setWindowTitle("Download failed")
		self.setIcon(QMessageBox.Warning)
		
		self.addButton(QMessageBox.Retry)
		self.addButton(QMessageBox.Ignore)
		self.addButton(QMessageBox.Abort)
		
		self.setEscapeButton(QMessageBox.Ignore)
		self.setDefaultButton(QMessageBox.Retry)
	
	@pyqtSlot(str, str, str, result=str)
	def askRetry(self, url, message, info):
		self.setText(message)
		self.setInformativeText(url)
		self.setDetailedText(info)
		ret = self.exec_()
		if ret == QMessageBox.Retry:
			return "retry"
		elif ret == QMessageBox.Ignore:
			return "ignore"
		elif ret == QMessageBox.Abort:
			return "abort"
		return "abort"

class MemriseLoginDialog(QDialog):
	def __init__(self, memriseService):
		super(MemriseLoginDialog, self).__init__()
		self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
		
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
		self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
		
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
		
		self.memsEnabled = False
		
	def setMemsEnabled(self, value):
		self.memsEnabled = value
	
	def __fillModelSelection(self):
		self.modelSelection.clear()
		self.modelSelection.addItem("--- create new ---")
		self.modelSelection.insertSeparator(1)
		for name in sorted(self.col.models.allNames()):
			self.modelSelection.addItem(name)
	
	@staticmethod
	def __createTemplate(t, pool, front, back, withMem):
		notFrontBack = partial(lambda fieldname, filtered=[]: fieldname not in filtered, filtered=[front,back])
		
		t['qfmt'] = "{{"+front+"}}\n"
		if front in pool.getTextColumnNames():
			frontAlternatives = "{} {}".format(front, _("Alternatives"))
			t['qfmt'] += "{{#"+frontAlternatives+"}}<br /><span class=\"alts\">{{"+frontAlternatives+"}}</span>{{/"+frontAlternatives+"}}\n"
		
		for colName in filter(notFrontBack, pool.getTextColumnNames()):
			t['qfmt'] += "<br />{{"+colName+"}}\n"
			altColName = "{} {}".format(colName, _("Alternatives"))
			t['qfmt'] += "{{#"+altColName+"}}<br /><span class=\"alts\">{{"+altColName+"}}</span>{{/"+altColName+"}}\n"
		
		for attrName in filter(notFrontBack, pool.getAttributeNames()):
			t['qfmt'] += "{{#"+attrName+"}}<br /><span class=\"attrs\">({{"+attrName+"}})</span>{{/"+attrName+"}}\n"
		
		t['afmt'] = "{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+"{{"+back+"}}\n"
		if back in pool.getTextColumnNames():
			backAlternatives = "{} {}".format(back, _("Alternatives"))
			t['afmt'] += "{{#"+backAlternatives+"}}<br /><span class=\"alts\">{{"+backAlternatives+"}}</span>{{/"+backAlternatives+"}}\n"
		
		if front == pool.getTextColumnName(0):
			imageside = 'afmt'
			audioside = 'qfmt'
		else:
			imageside = 'qfmt'
			audioside = 'afmt'
			
		for colName in filter(notFrontBack, pool.getImageColumnNames()):
			t[imageside] += "{{#"+colName+"}}<br />{{"+colName+"}}{{/"+colName+"}}\n"
		
		for colName in filter(notFrontBack, pool.getAudioColumnNames()):
			t[audioside] += "{{#"+colName+"}}<div style=\"display:none;\">{{"+colName+"}}</div>{{/"+colName+"}}\n"
		
		if withMem:
			memField = "{} -> {} {}".format(front, back, _("Mem"))
			t['afmt'] += "{{#"+memField+"}}<br />{{"+memField+"}}{{/"+memField+"}}\n"
		
		return t
	
	def __createMemriseModel(self, course, pool):
		mm = self.col.models
				
		name = "Memrise - {} - {}".format(course.title, pool.name)
		m = mm.new(name)
		
		for colName in pool.getTextColumnNames():
			dfm = mm.newField(colName)
			mm.addField(m, dfm)
			afm = mm.newField("{} {}".format(colName, _("Alternatives")))
			mm.addField(m, afm)
			hafm = mm.newField("{} {}".format(colName, _("Hidden Alternatives")))
			mm.addField(m, hafm)
			tcfm = mm.newField("{} {}".format(colName, _("Typing Corrects")))
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
		
		if self.memsEnabled:
			for direction in pool.mems.getDirections():
				fm = mm.newField("{} -> {} {}".format(direction.front, direction.back, _("Mem")))
				mm.addField(m, fm)
		
		fm = mm.newField(_("Level"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Thing"))
		mm.addField(m, fm)
		
		m['css'] += "\n.alts {\n font-size: 14px;\n}"
		m['css'] += "\n.attrs {\n font-style: italic;\n font-size: 14px;\n}"
		
		for direction in pool.directions:
			t = mm.newTemplate(str(direction))
			self.__createTemplate(t, pool, direction.front, direction.back, self.memsEnabled and direction in pool.mems.getDirections())
			mm.addTemplate(m, t)
		
		return m
	
	def __loadModel(self, thing, deck=None):
		model = self.__createMemriseModel(thing.pool.course, thing.pool)
		
		modelStored = self.col.models.byName(model['name'])
		if modelStored:
			if self.col.models.scmhash(modelStored) == self.col.models.scmhash(model):
				model = modelStored
			else:
				model['name'] += " ({})".format(str(uuid.uuid4()))
			
		if deck and 'mid' in deck:
			deckModel = self.col.models.get(deck['mid'])
			if deckModel and self.col.models.scmhash(deckModel) == self.col.models.scmhash(model):
				model = deckModel
				
		if model and not model['id']:
			self.col.models.add(model)

		return model
	
	def reject(self):
		# prevent close on ESC
		pass
	
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

class TemplateMappingDialog(QDialog):
	def __init__(self, col):
		super(TemplateMappingDialog, self).__init__()
		self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
		
		self.col = col
		self.templates = {}
		
		self.setWindowTitle("Assign Template Direction")
		layout = QVBoxLayout(self)
		
		self.grid = QGridLayout()
		layout.addLayout(self.grid)
		
		self.grid.addWidget(QLabel("Front:"), 0, 0)
		self.frontName = QLabel()
		self.grid.addWidget(self.frontName, 0, 1)
		self.frontExample = QLabel()
		self.grid.addWidget(self.frontExample, 0, 2)
		
		self.grid.addWidget(QLabel("Back:"), 1, 0)
		self.backName = QLabel()
		self.grid.addWidget(self.backName, 1, 1)
		self.backExample = QLabel()
		self.grid.addWidget(self.backExample, 1, 2)
		
		layout.addWidget(QLabel("Select template:"))
		self.templateSelection = QComboBox()
		layout.addWidget(self.templateSelection)
		self.templateSelection.setToolTip("Select the corresponding template for this direction.")
		
		buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)
	
	def __fillTemplateSelection(self, model):
		self.templateSelection.clear()
		for template in model['tmpls']:
			self.templateSelection.addItem(template['name'], template)
	
	@staticmethod
	def getFirst(values):
		return values[0] if 0 < len(values) else ''
	
	def reject(self):
		# prevent close on ESC
		pass
	
	def getTemplate(self, thing, note, direction):
		model = note.model()
		if direction in self.templates.get(model['id'], {}):
			return self.templates[model['id']][direction]
		
		for template in model['tmpls']:
			if template['name'] == str(direction):
				self.templates.setdefault(model['id'], {})[direction] = template
				return template

		self.frontName.setText(direction.front)
		frontField = FieldHelper(thing.pool.getColumn(direction.front))
		self.frontExample.setText(self.getFirst(frontField.get(thing)))

		self.backName.setText(direction.back)
		backField = FieldHelper(thing.pool.getColumn(direction.back))
		self.backExample.setText(self.getFirst(backField.get(thing)))

		self.__fillTemplateSelection(model)
		self.exec_()

		template = self.templateSelection.itemData(self.templateSelection.currentIndex())
		self.templates.setdefault(model['id'], {})[direction] = template
		
		return template

class FieldHelper(object):
	def __init__(self, field, getter=None, name=None):
		self.field = field
		if getter is None:
			if isinstance(field, memrise.Column):
				if field.type == memrise.Field.Text:
					getter = memrise.Thing.getDefinitions
				elif field.type == memrise.Field.Audio:
					getter = memrise.Thing.getLocalAudioUrls
				elif field.type == memrise.Field.Image:
					getter = memrise.Thing.getLocalImageUrls
			elif isinstance(field, memrise.Attribute):
				if field.type == memrise.Field.Text:
					getter = memrise.Thing.getAttributes
			elif isinstance(field, memrise.Field):
				if field.type == memrise.Field.Mem:
					getter = None
		self.getter = getter
		self.name = name

	def get(self, thing):
		return self.getter(thing, self.field.name)

	def match(self, name):
		if self.name is not None:
			return name == self.name
		return name == self.field.name

class FieldMappingDialog(QDialog):
	def __init__(self, col):
		super(FieldMappingDialog, self).__init__()
		self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
		
		self.col = col
		self.mappings = {}
		
		self.setWindowTitle("Assign Memrise Fields")
		layout = QVBoxLayout()
		
		self.label = QLabel("Define the field mapping for the selected note type.")
		layout.addWidget(self.label)

		viewport = QWidget()
		self.grid = QGridLayout()
		self.grid.setSizeConstraint(QLayout.SetMinAndMaxSize)
		viewport.setLayout(self.grid)

		scrollArea = QScrollArea()
		scrollArea.setWidgetResizable(True)
		scrollArea.setWidget(viewport)

		layout.addWidget(scrollArea)
		
		buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)
		
		self.setLayout(layout)

		self.memsEnabled = False

	def setMemsEnabled(self, value):
		self.memsEnabled = value

	@staticmethod
	def clearLayout(layout):
		while layout.count():
			child = layout.takeAt(0)
			if child.widget() is not None:
				child.widget().deleteLater()
				child.widget().setParent(None)
			elif child.layout() is not None:
				FieldMappingDialog.clearLayout(child.layout())

	@staticmethod
	def __findIndexWithData(combobox, name):
		for index in range(0, combobox.count()):
			data = combobox.itemData(index)
			if data and data.match(name):
				return index
		return -1

	def __createModelFieldSelection(self, fieldNames):
		fieldSelection = QComboBox()
		fieldSelection.addItem("--- None ---")
		fieldSelection.insertSeparator(1)
		for fieldName in fieldNames:
			fieldSelection.addItem(fieldName)
		return fieldSelection

	def __createMemriseFieldSelection(self, pool):
		fieldSelection = QComboBox()
		fieldSelection.addItem("--- None ---")
		fieldSelection.insertSeparator(1)
		for column in pool.getTextColumns():
			fieldSelection.addItem("Text: {}".format(column.name),
								FieldHelper(column, memrise.Thing.getDefinitions))
			fieldSelection.addItem("{1}: {0}".format(column.name, _("Alternatives")),
								FieldHelper(column, memrise.Thing.getAlternatives, "{} {}".format(column.name, _("Alternatives"))))
			fieldSelection.addItem("{1}: {0}".format(column.name, _("Hidden Alternatives")),
								FieldHelper(column, memrise.Thing.getHiddenAlternatives, "{} {}".format(column.name, _("Hidden Alternatives"))))
			fieldSelection.addItem("{1}: {0}".format(column.name, _("Typing Corrects")),
								FieldHelper(column, memrise.Thing.getTypingCorrects, "{} {}".format(column.name, _("Typing Corrects"))))
		for column in pool.getImageColumns():
			fieldSelection.addItem("Image: {}".format(column.name), FieldHelper(column, memrise.Thing.getLocalImageUrls))
		for column in pool.getAudioColumns():
			fieldSelection.addItem("Audio: {}".format(column.name), FieldHelper(column, memrise.Thing.getLocalAudioUrls))
		for attribute in pool.getAttributes():
			fieldSelection.addItem("Attribute: {}".format(attribute.name), FieldHelper(attribute, memrise.Thing.getAttributes))
		if self.memsEnabled:
			for direction in pool.mems.getDirections():
				fieldSelection.addItem("Mem: {} -> {}".format(direction.front, direction.back),
									FieldHelper(memrise.Field(memrise.Field.Mem, None, None), lambda thing, fieldname, direction=direction: pool.mems.get(direction, thing), "{} -> {} {}".format(direction.front, direction.back, _("Mem"))))
			
		return fieldSelection

	def __buildGrid(self, pool, model):
		self.clearLayout(self.grid)

		label1 = QLabel("Note type fields:")
		label1.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
		label2 = QLabel("Memrise fields:")
		label2.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
		self.grid.addWidget(label1, 0, 0)
		self.grid.addWidget(label2, 0, 1)
				
		fieldNames = [fieldName for fieldName in self.col.models.fieldNames(model) if not fieldName in [_('Thing'), _('Level')]]
		poolFieldCount = pool.countTextColumns()*4 + pool.countImageColumns() + pool.countAudioColumns() + pool.countAttributes()
		if self.memsEnabled:
			poolFieldCount += pool.mems.countDirections()
		
		mapping = []
		for index in range(0, max(len(fieldNames), poolFieldCount)):
			modelFieldSelection = self.__createModelFieldSelection(fieldNames)
			self.grid.addWidget(modelFieldSelection, index+1, 0)

			memriseFieldSelection = self.__createMemriseFieldSelection(pool)
			self.grid.addWidget(memriseFieldSelection, index+1, 1)
			
			if index < len(fieldNames):
				modelFieldSelection.setCurrentIndex(index+2)
			
			fieldIndex = self.__findIndexWithData(memriseFieldSelection, modelFieldSelection.currentText())
			if fieldIndex >= 2:
				memriseFieldSelection.setCurrentIndex(fieldIndex)
			
			mapping.append((modelFieldSelection, memriseFieldSelection))
		
		return mapping
	
	def reject(self):
		# prevent close on ESC
		pass
	
	def getFieldMappings(self, pool, model):
		if pool.id in self.mappings:
			if model['id'] in self.mappings[pool.id]:
				return self.mappings[pool.id][model['id']]
		
		self.label.setText('Define the field mapping for the note type "{}".'.format(model["name"]))
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
		self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)

		# set up the UI, basically
		self.setWindowTitle("Import Memrise Course")
		layout = QVBoxLayout(self)
		
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
		
		label = QLabel("Enter the home URL of the Memrise course to import:")
		self.courseUrlLineEdit = QLineEdit()
		courseUrlTooltip = "e.g. http://www.memrise.com/course/77958/memrise-intro-french/"
		label.setToolTip(courseUrlTooltip)
		self.courseUrlLineEdit.setToolTip(courseUrlTooltip)
		layout.addWidget(label)
		layout.addWidget(self.courseUrlLineEdit)
		
		label = QLabel("Minimal number of digits in the level tag:")
		self.minimalLevelTagWidthSpinBox = QSpinBox()
		self.minimalLevelTagWidthSpinBox.setMinimum(1)
		self.minimalLevelTagWidthSpinBox.setMaximum(9)
		self.minimalLevelTagWidthSpinBox.setValue(2)
		minimalLevelTagWidthTooltip = "e.g. 3 results in Level001"
		label.setToolTip(minimalLevelTagWidthTooltip)
		self.minimalLevelTagWidthSpinBox.setToolTip(minimalLevelTagWidthTooltip)
		layout.addWidget(label)
		layout.addWidget(self.minimalLevelTagWidthSpinBox)

		self.importScheduleCheckBox = QCheckBox("Import scheduler information")
		self.importScheduleCheckBox.setChecked(True)
		self.importScheduleCheckBox.setToolTip("e.g. next due date, interval, etc.")
		layout.addWidget(self.importScheduleCheckBox)
		def setScheduler(checkbox, predicate, index):
			checkbox.setChecked(predicate(index))
		self.deckSelection.currentIndexChanged.connect(partial(setScheduler,self.importScheduleCheckBox,lambda i: i==0))

		self.importMemsCheckBox = QCheckBox("Import mems")
		importMemsTooltip = "activate \"Download media files\" in order to download image mems"
		self.importMemsCheckBox.setToolTip(importMemsTooltip)
		layout.addWidget(self.importMemsCheckBox)
		
		self.embedMemsOnlineMediaCheckBox = QCheckBox("Embed online media in mems (experimental)")
		embedMemsOnlineMediaTooltip = "Warning: Embedding online media is not officially supported by Anki,\n it may or may not work depending on your platform."
		self.embedMemsOnlineMediaCheckBox.setToolTip(embedMemsOnlineMediaTooltip)
		layout.addWidget(self.embedMemsOnlineMediaCheckBox)

		self.importMemsCheckBox.stateChanged.connect(self.embedMemsOnlineMediaCheckBox.setEnabled)
		self.importMemsCheckBox.setChecked(True)
		self.embedMemsOnlineMediaCheckBox.setChecked(False)

		self.downloadMediaCheckBox = QCheckBox("Download media files")
		layout.addWidget(self.downloadMediaCheckBox)
		
		self.skipExistingMediaCheckBox = QCheckBox("Skip download of existing media files")
		layout.addWidget(self.skipExistingMediaCheckBox)
		
		self.downloadMediaCheckBox.stateChanged.connect(self.skipExistingMediaCheckBox.setEnabled)
		self.downloadMediaCheckBox.setChecked(True)
		self.skipExistingMediaCheckBox.setChecked(True)

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
		self.loader.askerFunction = DownloadFailedBox().askRetry
		
		self.modelMapper = ModelMappingDialog(mw.col)
		self.fieldMapper = FieldMappingDialog(mw.col)
		self.templateMapper = TemplateMappingDialog(mw.col)
	
	def prepareTitleTag(self, tag):
		value = ''.join(x for x in tag.title() if x.isalnum())
		if value.isdigit():
			return ''
		return value
	
	def prepareLevelTag(self, levelNum, width):
		formatstr = "Level{:0"+str(width)+"d}"
		return formatstr.format(levelNum)
	
	def getLevelTags(self, levelCount, level):
		tags = [self.prepareLevelTag(level.index, max(self.minimalLevelTagWidthSpinBox.value(), len(str(levelCount))))]
		titleTag = self.prepareTitleTag(level.title)
		if titleTag:
			tags.append(titleTag)
		return tags
		
	@staticmethod
	def prepareText(content):
		return '{:s}'.format(content.strip())
	
	@staticmethod
	def prepareAudio(content):
		return '[sound:{:s}]'.format(content)
	
	@staticmethod
	def prepareImage(content):
		return '<img src="{:s}">'.format(content)
	
	def selectDeck(self, name, merge=False):
		did = mw.col.decks.id(name, create=False)
		if not merge:
			if did:
				did = mw.col.decks.id("{}-{}".format(name, str(uuid.uuid4())))
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
		notes = mw.col.findNotes('deck:"{}" {}:"{}"'.format(deckName, 'Thing', thing.id))
		if notes:
			return mw.col.getNote(notes[0])
			
		return None

	def getWithSpec(self, thing, spec):
		values = spec.get(thing)
		if spec.field.type == memrise.Field.Text:
			return list(map(self.prepareText, values))
		elif spec.field.type == memrise.Field.Image:
			return list(map(self.prepareImage, list(filter(bool, values))))
		elif spec.field.type == memrise.Field.Audio:
			return list(map(self.prepareAudio, list(filter(bool, values))))
		elif spec.field.type == memrise.Field.Mem:
			return self.prepareText(values.get())
						
		return None
	
	@staticmethod
	def toList(values):
		if hasattr(values, '__iter__'):
			return [_f for _f in values if _f]
		elif values:
			return [values]
		else:
			return []
	
	def importCourse(self):
		if self.loader.isException():
			self.buttons.show()
			self.progressBar.hide()
			exc_info = self.loader.getExceptionInfo()
			raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])
		
		try:
			self.progressBar.setValue(0)
			self.progressBar.setFormat("Importing: %p% (%v/%m)")
			
			course = self.loader.getResult()
			
			self.modelMapper.setMemsEnabled(self.importMemsCheckBox.isEnabled())
			self.fieldMapper.setMemsEnabled(self.importMemsCheckBox.isEnabled())
			
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
					for field, data in list(mapping.items()):
						values = []
						for spec in data:
							values.extend(self.toList(self.getWithSpec(thing, spec)))
						ankiNote[field] = ", ".join(values)
	
					if _('Level') in list(ankiNote.keys()):
						levels = set(filter(bool, list(map(str.strip, ankiNote[_('Level')].split(',')))))
						levels.add(str(level.index))
						ankiNote[_('Level')] = ', '.join(sorted(levels))
					
					if _('Thing') in list(ankiNote.keys()):
						ankiNote[_('Thing')] = str(thing.id)
					
					for tag in tags:
						ankiNote.addTag(tag)
						
					if not ankiNote.cards():
						mw.col.addNote(ankiNote)
					ankiNote.flush()
					noteCache[thing.id] = ankiNote
	
					scheduleInfo = thing.pool.schedule.get(level.direction, thing)
					if scheduleInfo:
						template = self.templateMapper.getTemplate(thing, ankiNote, scheduleInfo.direction)
						cards = [card for card in ankiNote.cards() if card.ord == template['ord']]

						if self.importScheduleCheckBox.isChecked():
							for card in cards:
								if scheduleInfo.interval is None:
									card.type = 0
									card.queue = 0
									card.ivl = 0
									card.reps = 0
									card.lapses = 0
									card.due = scheduleInfo.position
									card.factor = 0
								else:
									card.type = 2
									card.queue = 2
									card.ivl = int(round(scheduleInfo.interval))
									card.reps = scheduleInfo.total
									card.lapses = scheduleInfo.incorrect
									card.due = mw.col.sched.today + (scheduleInfo.due.date() - datetime.date.today()).days
									card.factor = 2500
								card.flush()
							if scheduleInfo.ignored:
								mw.col.sched.suspendCards([card.id for card in cards])
						else:
							for card in cards:
								if card.type == 0 and card.queue == 0:
									card.due = scheduleInfo.position
									card.flush()

					self.progressBar.setValue(self.progressBar.value()+1)
					QApplication.processEvents()
		
		except Exception:
			self.buttons.show()
			self.progressBar.hide()
			exc_info = sys.exc_info()
			raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])
		
		mw.col.reset()
		mw.reset()
		
		# refresh deck browser so user can see the newly imported deck
		mw.deckBrowser.refresh()
		
		self.accept()

	def reject(self):
		# prevent close while background process is running
		if not self.buttons.isHidden():
			super(MemriseImportDialog, self).reject()

	def loadCourse(self):
		self.buttons.hide()
		self.progressBar.show()
		self.progressBar.setValue(0)
		
		courseUrl = self.courseUrlLineEdit.text()
		self.loader.downloadMedia = self.downloadMediaCheckBox.isChecked()
		self.loader.skipExistingMedia = self.skipExistingMediaCheckBox.isChecked()
		self.loader.downloadMems = self.importMemsCheckBox.isChecked() and self.downloadMediaCheckBox.isChecked()
		self.loader.embedMemsOnlineMedia = self.importMemsCheckBox.isChecked() and self.embedMemsOnlineMediaCheckBox.isChecked()
		self.loader.start(courseUrl)

def startCourseImporter():
	downloadDirectory = MediaManager(mw.col, None).dir()
	cookiefilename = os.path.join(mw.pm.profileFolder(), 'memrise.cookies')
	cookiejar = http.cookiejar.MozillaCookieJar(cookiefilename)
	if os.path.isfile(cookiefilename):
		cookiejar.load()
	memriseService = memrise.Service(downloadDirectory, cookiejar)
	if memriseService.isLoggedIn() or MemriseLoginDialog.login(memriseService):
		cookiejar.save()
		memriseCourseImporter = MemriseImportDialog(memriseService)
		memriseCourseImporter.exec_()

action = QAction("Import Memrise Course...", mw)
action.triggered.connect(startCourseImporter)
mw.form.menuTools.addAction(action)
