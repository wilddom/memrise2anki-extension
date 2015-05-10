# -*- coding: utf-8 -*-

import memrise, cookielib, os.path, uuid, sys, datetime, re
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
		
		def downloadMems(self, thing):
			download = partial(self.sender.memriseService.downloadMedia, skipExisting=self.sender.skipExistingMedia)
			for mem in thing.pool.mems.getMems(thing).values():
				if mem.isImageMem():
					mem.localImageUrl = download(mem.remoteImageUrl)
			
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
		self.runnable = MemriseCourseLoader.RunnableWrapper(self)
		self.result = None
		self.exc_info = (None,None,None)
		self.downloadMedia = True
		self.skipExistingMedia = True
		self.downloadMems = True
	
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
		
		t['qfmt'] = u"{{"+front+u"}}\n"
		if front in pool.getTextColumnNames():
			frontAlternatives = u"{} {}".format(front, _("Alternatives"))
			t['qfmt'] += u"{{#"+frontAlternatives+u"}}<br /><span class=\"alts\">{{"+frontAlternatives+u"}}</span>{{/"+frontAlternatives+u"}}\n"
		
		for colName in filter(notFrontBack, pool.getTextColumnNames()):
			t['qfmt'] += u"<br />{{"+colName+u"}}\n"
			altColName = u"{} {}".format(colName, _("Alternatives"))
			t['qfmt'] += u"{{#"+altColName+u"}}<br /><span class=\"alts\">{{"+altColName+u"}}</span>{{/"+altColName+u"}}\n"
		
		for attrName in filter(notFrontBack, pool.getAttributeNames()):
			t['qfmt'] += u"{{#"+attrName+u"}}<br /><span class=\"attrs\">({{"+attrName+u"}})</span>{{/"+attrName+"}}\n"
		
		t['afmt'] = u"{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+u"{{"+back+u"}}\n"
		if back in pool.getTextColumnNames():
			backAlternatives = u"{} {}".format(back, _("Alternatives"))
			t['afmt'] += u"{{#"+backAlternatives+u"}}<br /><span class=\"alts\">{{"+backAlternatives+u"}}</span>{{/"+backAlternatives+u"}}\n"
		
		if front == pool.getTextColumnName(0):
			imageside = 'afmt'
			audioside = 'qfmt'
		else:
			imageside = 'qfmt'
			audioside = 'afmt'
			
		for colName in filter(notFrontBack, pool.getImageColumnNames()):
			t[imageside] += u"{{#"+colName+u"}}<br />{{"+colName+u"}}{{/"+colName+"}}\n"
		
		for colName in filter(notFrontBack, pool.getAudioColumnNames()):
			t[audioside] += u"{{#"+colName+u"}}<div style=\"display:none;\">{{"+colName+u"}}</div>{{/"+colName+"}}\n"
		
		if withMem:
			memField = u"{} {}".format(back, _("Mem"))
			t['afmt'] += u"{{#"+memField+u"}}<br />{{"+memField+u"}}{{/"+memField+"}}\n"
		
		return t
	
	def __createMemriseModel(self, course, pool):
		mm = self.col.models
				
		name = u"Memrise - {}".format(course.title)
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
		
		if self.memsEnabled:
			for direction in pool.mems.getDirections():
				fm = mm.newField(u"{} {}".format(direction.back, _("Mem")))
				mm.addField(m, fm)
		
		fm = mm.newField(_("Level"))
		mm.addField(m, fm)
		
		fm = mm.newField(_("Thing"))
		mm.addField(m, fm)
		
		m['css'] += "\n.alts {\n font-size: 14px;\n}"
		m['css'] += "\n.attrs {\n font-style: italic;\n font-size: 14px;\n}"
		
		for direction in course.directions:
			t = mm.newTemplate(unicode(direction))
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
				model['name'] += u" ({})".format(uuid.uuid4())
			
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

class TemplateMappingDialog(QDialog):
	def __init__(self, col):
		super(TemplateMappingDialog, self).__init__()
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
		return values[0] if 0 < len(values) else u''
	
	def getTemplate(self, thing, note, direction):
		model = note.model()
		if direction in self.templates.get(model['id'], {}):
			return self.templates[model['id']][direction]
		
		for template in model['tmpls']:
			if template['name'] == unicode(direction):
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
		
		self.memsEnabled = False

	def setMemsEnabled(self, value):
		self.memsEnabled = value

	@staticmethod
	def clearLayout(layout):
		while layout.count():
			child = layout.takeAt(0)
			if child.widget() is not None:
				child.widget().deleteLater()
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
		fieldSelection.addItem(u"--- None ---")
		fieldSelection.insertSeparator(1)
		for fieldName in fieldNames:
			fieldSelection.addItem(fieldName)
		return fieldSelection

	def __createMemriseFieldSelection(self, pool):
		fieldSelection = QComboBox()
		fieldSelection.addItem(u"--- None ---")
		fieldSelection.insertSeparator(1)
		for column in pool.getTextColumns():
			fieldSelection.addItem(u"Text: {}".format(column.name),
								FieldHelper(column, memrise.Thing.getDefinitions))
			fieldSelection.addItem(u"{1}: {0}".format(column.name, _("Alternatives")),
								FieldHelper(column, memrise.Thing.getAlternatives, u"{} {}".format(column.name, _("Alternatives"))))
			fieldSelection.addItem(u"{1}: {0}".format(column.name, _("Hidden Alternatives")),
								FieldHelper(column, memrise.Thing.getHiddenAlternatives, u"{} {}".format(column.name, _("Hidden Alternatives"))))
			fieldSelection.addItem(u"{1}: {0}".format(column.name, _("Typing Corrects")),
								FieldHelper(column, memrise.Thing.getTypingCorrects, u"{} {}".format(column.name, _("Typing Corrects"))))
		for column in pool.getImageColumns():
			fieldSelection.addItem(u"Image: {}".format(column.name), FieldHelper(column, memrise.Thing.getLocalImageUrls))
		for column in pool.getAudioColumns():
			fieldSelection.addItem(u"Audio: {}".format(column.name), FieldHelper(column, memrise.Thing.getLocalAudioUrls))
		for attribute in pool.getAttributes():
			fieldSelection.addItem(u"Attribute: {}".format(attribute.name), FieldHelper(attribute, memrise.Thing.getAttributes))
		if self.memsEnabled:
			for direction in pool.mems.getDirections():
				fieldSelection.addItem(u"Mem: {}".format(direction.back),
									FieldHelper(memrise.Field(memrise.Field.Mem, None, None), lambda thing, fieldname, direction=direction: pool.mems.get(direction, thing), u"{} {}".format(direction.back, _("Mem"))))
			
		return fieldSelection

	def __buildGrid(self, pool, model):
		self.clearLayout(self.grid)

		self.grid.addWidget(QLabel("Note type fields:"), 0, 0)
		self.grid.addWidget(QLabel("Memrise fields:"), 0, 1)
				
		fieldNames = filter(lambda fieldName: not fieldName in [_('Thing'), _('Level')], self.col.models.fieldNames(model))
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
		
		label = QLabel("Minimal level tag width filled width zeros:")
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
		self.importMemsCheckBox.setChecked(True)
		importMemsTooltip = "activate \"Download media files\" in order to download image mems"
		self.importMemsCheckBox.setToolTip(importMemsTooltip)
		layout.addWidget(self.importMemsCheckBox)

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
		
		self.modelMapper = ModelMappingDialog(mw.col)
		self.fieldMapper = FieldMappingDialog(mw.col)
		self.templateMapper = TemplateMappingDialog(mw.col)
	
	def prepareTitleTag(self, tag):
		value = u''.join(x for x in tag.title() if x.isalnum())
		if value.isdigit():
			return ''
		return value
	
	def prepareLevelTag(self, levelNum, width):
		formatstr = u"Level{:0"+unicode(width)+"d}"
		return formatstr.format(levelNum)
	
	def getLevelTags(self, levelCount, level):
		tags = [self.prepareLevelTag(level.index, max(self.minimalLevelTagWidthSpinBox.value(), len(unicode(levelCount))))]
		titleTag = self.prepareTitleTag(level.title)
		if titleTag:
			tags.append(titleTag)
		return tags
		
	@staticmethod
	def prepareText(content):
		content = re.sub(r"\*([^\*]+)\*", '<strong>\\1</strong>', content)
		content = re.sub(r"_([^_]+)_", '<em>\\1</em>', content)
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
			
		return None

	def getWithSpec(self, thing, spec):
		values = spec.get(thing)
		if spec.field.type == memrise.Field.Text:
			return map(self.prepareText, values)
		elif spec.field.type == memrise.Field.Image:
			return map(self.prepareImage, values)
		elif spec.field.type == memrise.Field.Audio:
			return map(self.prepareAudio, values)
		elif spec.field.type == memrise.Field.Mem:
			if values.isTextMem():
				return self.prepareText(values.get())
			if values.isImageMem():
				return self.prepareImage(values.get())
						
		return None
	
	@staticmethod
	def toList(values):
		if hasattr(values, '__iter__'):
			return filter(None, values)
		elif values:
			return [values]
		else:
			return []
	
	def importCourse(self):
		if self.loader.isException():
			self.buttons.show()
			self.progressBar.hide()
			exc_info = self.loader.getExceptionInfo()
			raise exc_info[0], exc_info[1], exc_info[2]
		
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
					for field, data in mapping.iteritems():
						values = []
						for spec in data:
							values.extend(self.toList(self.getWithSpec(thing, spec)))
						ankiNote[field] = u", ".join(values)
	
					if _('Level') in ankiNote.keys():
						levels = set(filter(bool, map(unicode.strip, ankiNote[_('Level')].split(u','))))
						levels.add(unicode(level.index))
						ankiNote[_('Level')] = u', '.join(levels)
					
					if _('Thing') in ankiNote.keys():
						ankiNote[_('Thing')] = unicode(thing.id)
					
					for tag in tags:
						ankiNote.addTag(tag)
						
					if not ankiNote.cards():
						mw.col.addNote(ankiNote)
					ankiNote.flush()
					noteCache[thing.id] = ankiNote
	
					if self.importScheduleCheckBox.isChecked():
						scheduleInfo = thing.pool.schedule.get(level.direction, thing)
						if scheduleInfo:
							template = self.templateMapper.getTemplate(thing, ankiNote, scheduleInfo.direction)
							cards = [card for card in ankiNote.cards() if card.ord == template['ord']]
							
							if scheduleInfo.interval is not None:
								for card in cards:
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

					self.progressBar.setValue(self.progressBar.value()+1)
					QApplication.processEvents()
		
		except Exception:
			self.buttons.show()
			self.progressBar.hide()
			exc_info = sys.exc_info()
			raise exc_info[0], exc_info[1], exc_info[2]
		
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
		self.loader.downloadMems = self.importMemsCheckBox.isChecked() and self.downloadMediaCheckBox.isChecked()
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
