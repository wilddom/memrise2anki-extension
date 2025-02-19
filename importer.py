﻿# -*- coding: utf-8 -*-

import http.cookiejar, os.path, uuid, sys, datetime, html
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

		def downloadMedia(self, learnable):
			for colName in learnable.course.getImageColumnNames():
				for image in [f for f in learnable.getImageFiles(colName) if not f.isDownloaded()]:
					image.localUrl = self.sender.download(image.remoteUrl)
			for colName in learnable.course.getAudioColumnNames():
				for audio in [f for f in learnable.getAudioFiles(colName) if not f.isDownloaded()]:
					audio.localUrl = self.sender.download(audio.remoteUrl)

		def thingLoaded(self, learnable):
			if learnable and self.sender.downloadMedia:
				self.downloadMedia(learnable)
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
		self.askerFunction = None
		self.ignoreDownloadErrors = False

	def download(self, url):
		import urllib.request, urllib.error, urllib.parse
		while True:
			try:
				return self.memriseService.downloadMedia(url, skipExisting=self.skipExistingMedia)
			except (urllib.error.HTTPError, urllib.error.URLError) as e:
				if self.ignoreDownloadErrors:
					return None
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
		self.setIcon(QMessageBox.Icon.Warning)

		self.addButton(QMessageBox.StandardButton.Retry)
		self.addButton(QMessageBox.StandardButton.Ignore)
		self.addButton(QMessageBox.StandardButton.Abort)

		self.setEscapeButton(QMessageBox.StandardButton.Ignore)
		self.setDefaultButton(QMessageBox.StandardButton.Retry)

	@pyqtSlot(str, str, str, result=str)
	def askRetry(self, url, message, info):
		self.setText(message)
		self.setInformativeText(url)
		self.setDetailedText(info)
		ret = self.exec()
		if ret == QMessageBox.StandardButton.Retry:
			return "retry"
		elif ret == QMessageBox.StandardButton.Ignore:
			return "ignore"
		elif ret == QMessageBox.StandardButton.Abort:
			return "abort"
		return "abort"

class MemriseLoginDialog(QDialog):
	def __init__(self, memriseService):
		super(MemriseLoginDialog, self).__init__()
		self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

		self.memriseService = memriseService

		self.setWindowTitle("Memrise Login")

		layout = QVBoxLayout(self)

		innerLayout = QGridLayout()

		innerLayout.addWidget(QLabel("Username:"),0,0)
		self.usernameLineEdit = QLineEdit()
		innerLayout.addWidget(self.usernameLineEdit,0,1)

		innerLayout.addWidget(QLabel("Password:"),1,0)
		self.passwordLineEdit = QLineEdit()
		self.passwordLineEdit.setEchoMode(QLineEdit.EchoMode.Password)
		innerLayout.addWidget(self.passwordLineEdit,1,1)

		layout.addLayout(innerLayout)

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, Qt.Orientation.Horizontal, self)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)

	def accept(self):
		if self.memriseService.login(self.usernameLineEdit.text(),self.passwordLineEdit.text()):
			super(MemriseLoginDialog, self).accept()
		else:
			msgBox = QMessageBox()
			msgBox.setWindowTitle("Login")
			msgBox.setText("Couldn't log in. Please check your credentials.")
			msgBox.exec()

	def reject(self):
		super(MemriseLoginDialog, self).reject()


	@staticmethod
	def login(memriseService):
		dialog = MemriseLoginDialog(memriseService)
		return dialog.exec() == QDialog.DialogCode.Accepted


class ModelMappingDialog(QDialog):
	def __init__(self, col):
		super(ModelMappingDialog, self).__init__()
		self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

		self.col = col
		self.models = {}

		self.setWindowTitle("Note Type")
		layout = QVBoxLayout(self)

		layout.addWidget(QLabel("Select note type for newly imported notes:"))

		self.modelSelection = QComboBox()
		layout.addWidget(self.modelSelection)
		self.modelSelection.setToolTip("Either a new note type will be created or an existing one can be reused.")

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)

	def __fillModelSelection(self):
		self.modelSelection.clear()
		self.modelSelection.addItem("--- create new ---")
		self.modelSelection.insertSeparator(1)
		for name in sorted(self.col.models.all_names()):
			self.modelSelection.addItem(name)

	@staticmethod
	def __createTemplate(t, course, front, back):
		notFrontBack = partial(lambda fieldname, filtered=[]: fieldname not in filtered, filtered=[front,back])

		t['qfmt'] = "{{"+front+"}}\n"
		if front in course.getTextColumnNames():
			frontAlternatives = "{} {}".format(front, "Alternatives")
			t['qfmt'] += "{{#"+frontAlternatives+"}}<br /><span class=\"alts\">{{"+frontAlternatives+"}}</span>{{/"+frontAlternatives+"}}\n"

		for colName in filter(notFrontBack, course.getTextColumnNames()):
			t['qfmt'] += "<br />{{"+colName+"}}\n"
			altColName = "{} {}".format(colName, "Alternatives")
			t['qfmt'] += "{{#"+altColName+"}}<br /><span class=\"alts\">{{"+altColName+"}}</span>{{/"+altColName+"}}\n"

		for attrName in filter(notFrontBack, course.getAttributeNames()):
			t['qfmt'] += "{{#"+attrName+"}}<br /><span class=\"attrs\">({{"+attrName+"}})</span>{{/"+attrName+"}}\n"

		t['afmt'] = "{{FrontSide}}\n\n<hr id=\"answer\" />\n\n"+"{{"+back+"}}\n"
		if back in course.getTextColumnNames():
			backAlternatives = "{} {}".format(back, "Alternatives")
			t['afmt'] += "{{#"+backAlternatives+"}}<br /><span class=\"alts\">{{"+backAlternatives+"}}</span>{{/"+backAlternatives+"}}\n"

		if front in course.getTextColumnNames() and front == course.getTextColumnNames()[0]:
			imageside = 'afmt'
			audioside = 'qfmt'
		else:
			imageside = 'qfmt'
			audioside = 'afmt'

		for colName in filter(notFrontBack, course.getImageColumnNames()):
			t[imageside] += "{{#"+colName+"}}<br />{{"+colName+"}}{{/"+colName+"}}\n"

		for colName in filter(notFrontBack, course.getAudioColumnNames()):
			t[audioside] += "{{#"+colName+"}}<div style=\"display:none;\">{{"+colName+"}}</div>{{/"+colName+"}}\n"

		return t

	def __createMemriseModel(self, course):
		mm = self.col.models

		name = "Memrise - {}".format(course.title)
		m = mm.new(name)

		for colName in course.getTextColumnNames():
			dfm = mm.newField(colName)
			mm.addField(m, dfm)
			afm = mm.newField("{} {}".format(colName, "Alternatives"))
			mm.addField(m, afm)
			hafm = mm.newField("{} {}".format(colName, "Hidden Alternatives"))
			mm.addField(m, hafm)
			tcfm = mm.newField("{} {}".format(colName, "Typing Corrects"))
			mm.addField(m, tcfm)

		for attrName in course.getAttributeNames():
			fm = mm.newField(attrName)
			mm.addField(m, fm)

		for colName in course.getImageColumnNames():
			fm = mm.newField(colName)
			mm.addField(m, fm)

		for colName in course.getAudioColumnNames():
			fm = mm.newField(colName)
			mm.addField(m, fm)

		fm = mm.newField("Level")
		mm.addField(m, fm)

		fm = mm.newField("Learnable")
		mm.addField(m, fm)

		m['css'] += "\n.alts {\n font-size: 14px;\n}"
		m['css'] += "\n.attrs {\n font-style: italic;\n font-size: 14px;\n}"

		for direction in course.getDirections():
			t = mm.newTemplate(str(direction))
			self.__createTemplate(t, course, direction.front, direction.back)
			mm.addTemplate(m, t)

		return m

	def __loadModel(self, learnable, deck=None):
		model = self.__createMemriseModel(learnable.course)

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

	def getModel(self, learnable, deck):
		if learnable.course.id in self.models:
			return self.models[learnable.course.id]

		self.__fillModelSelection()
		self.exec()

		if self.modelSelection.currentIndex() == 0:
			self.models[learnable.course.id] = self.__loadModel(learnable, deck)
		else:
			modelName = self.modelSelection.currentText()
			self.models[learnable.course.id] = self.col.models.byName(modelName)

		return self.models[learnable.course.id]

class TemplateMappingDialog(QDialog):
	def __init__(self, col):
		super(TemplateMappingDialog, self).__init__()
		self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

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

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self)
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

	def getTemplate(self, learnable, note, direction):
		model = note.note_type()
		if direction in self.templates.get(model['id'], {}):
			return self.templates[model['id']][direction]

		for template in model['tmpls']:
			if template['name'] == str(direction):
				self.templates.setdefault(model['id'], {})[direction] = template
				return template

		self.frontName.setText(direction.front)
		frontField = FieldHelper(learnable.course.getColumn(direction.front))
		self.frontExample.setText(self.getFirst(frontField.get(learnable)))

		self.backName.setText(direction.back)
		backField = FieldHelper(learnable.course.getColumn(direction.back))
		self.backExample.setText(self.getFirst(backField.get(learnable)))

		self.__fillTemplateSelection(model)
		self.exec()

		template = self.templateSelection.itemData(self.templateSelection.currentIndex())
		self.templates.setdefault(model['id'], {})[direction] = template

		return template

class FieldHelper(object):
	def __init__(self, field, getter=None, name=None):
		self.field = field
		if getter is None:
			if isinstance(field, memrise.Column):
				if field.type == memrise.Field.Text:
					getter = memrise.Learnable.getDefinitions
				elif field.type == memrise.Field.Audio:
					getter = memrise.Learnable.getLocalAudioUrls
				elif field.type == memrise.Field.Image:
					getter = memrise.Learnable.getLocalImageUrls
			elif isinstance(field, memrise.Attribute):
				if field.type == memrise.Field.Text:
					getter = memrise.Learnable.getAttributes
			elif isinstance(field, memrise.Field):
				if field.type == memrise.Field.Mem:
					getter = None
		self.getter = getter
		self.name = name

	def get(self, learnable):
		return self.getter(learnable, self.field.name)

	def match(self, name):
		if self.name is not None:
			return name == self.name
		return name == self.field.name

class FieldMappingDialog(QDialog):
	def __init__(self, col):
		super(FieldMappingDialog, self).__init__()
		self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

		self.col = col
		self.mappings = {}

		self.setWindowTitle("Assign Memrise Fields")
		layout = QVBoxLayout()

		self.label = QLabel("Define the field mapping for the selected note type.")
		layout.addWidget(self.label)

		viewport = QWidget()
		self.grid = QGridLayout()
		self.grid.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
		viewport.setLayout(self.grid)

		scrollArea = QScrollArea()
		scrollArea.setWidgetResizable(True)
		scrollArea.setWidget(viewport)

		layout.addWidget(scrollArea)

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self)
		buttons.accepted.connect(self.accept)
		layout.addWidget(buttons)

		self.setLayout(layout)

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

	def __createMemriseFieldSelection(self, course):
		fieldSelection = QComboBox()
		fieldSelection.addItem("--- None ---")
		fieldSelection.insertSeparator(1)
		for column in course.getTextColumns():
			fieldSelection.addItem("Text: {}".format(column.name),
								FieldHelper(column, memrise.Learnable.getDefinitions))
			fieldSelection.addItem("{1}: {0}".format(column.name, "Alternatives"),
								FieldHelper(column, memrise.Learnable.getAlternatives, "{} {}".format(column.name, "Alternatives")))
			fieldSelection.addItem("{1}: {0}".format(column.name, "Hidden Alternatives"),
								FieldHelper(column, memrise.Learnable.getHiddenAlternatives, "{} {}".format(column.name, "Hidden Alternatives")))
			fieldSelection.addItem("{1}: {0}".format(column.name, "Typing Corrects"),
								FieldHelper(column, memrise.Learnable.getTypingCorrects, "{} {}".format(column.name, "Typing Corrects")))
		for column in course.getImageColumns():
			fieldSelection.addItem("Image: {}".format(column.name), FieldHelper(column, memrise.Learnable.getLocalImageUrls))
		for column in course.getAudioColumns():
			fieldSelection.addItem("Audio: {}".format(column.name), FieldHelper(column, memrise.Learnable.getLocalAudioUrls))
		for attribute in course.getAttributes():
			fieldSelection.addItem("Attribute: {}".format(attribute.name), FieldHelper(attribute, memrise.Learnable.getAttributes))

		return fieldSelection

	def __buildGrid(self, course, model):
		self.clearLayout(self.grid)

		label1 = QLabel("Note type fields:")
		label1.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
		label2 = QLabel("Memrise fields:")
		label2.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
		self.grid.addWidget(label1, 0, 0)
		self.grid.addWidget(label2, 0, 1)

		fieldNames = [fieldName for fieldName in self.col.models.field_names(model) if not fieldName in ['Learnable', 'Level']]
		courseFieldCount = course.countTextColumns()*4 + course.countImageColumns() + course.countAudioColumns() + course.countAttributes()

		mapping = []
		for index in range(0, max(len(fieldNames), courseFieldCount)):
			modelFieldSelection = self.__createModelFieldSelection(fieldNames)
			self.grid.addWidget(modelFieldSelection, index+1, 0)

			memriseFieldSelection = self.__createMemriseFieldSelection(course)
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

	def getFieldMappings(self, course, model):
		if course.id in self.mappings:
			if model['id'] in self.mappings[course.id]:
				return self.mappings[course.id][model['id']]

		self.label.setText('Define the field mapping for the note type "{}".'.format(model["name"]))
		selectionMapping = self.__buildGrid(course, model)
		self.exec()

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

		self.mappings.setdefault(course.id, {})[model['id']] = mapping

		return mapping

class MemriseImportDialog(QDialog):
	def __init__(self, memriseService):
		super(MemriseImportDialog, self).__init__()
		self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

		# set up the UI, basically
		self.setWindowTitle("Import Memrise Course")
		layout = QVBoxLayout(self)

		self.deckSelection = QComboBox()
		self.deckSelection.addItem("--- create new ---")
		self.deckSelection.insertSeparator(1)
		for name in sorted([x.name for x in mw.col.decks.all_names_and_ids(include_filtered=False)]):
			self.deckSelection.addItem(name)
		deckSelectionTooltip = "<b>Updates a previously downloaded course.</b><br />In order for this to work the field <i>Learnable</i> must not be removed or renamed, it is needed to identify existing notes."
		self.deckSelection.setToolTip(deckSelectionTooltip)
		label = QLabel("Update existing deck:")
		label.setToolTip(deckSelectionTooltip)
		layout.addWidget(label)
		layout.addWidget(self.deckSelection)
		self.deckSelection.currentIndexChanged.connect(self.loadDeckUrl)

		label = QLabel("Enter the home URL of the Memrise course to import:")
		self.courseUrlLineEdit = QLineEdit()
		courseUrlTooltip = "e.g. https://community-courses.memrise.com/community/course/77958/memrise-intro-french/"
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

		self.downloadMediaCheckBox = QCheckBox("Download media files")
		layout.addWidget(self.downloadMediaCheckBox)

		self.skipExistingMediaCheckBox = QCheckBox("Skip download of existing media files")
		layout.addWidget(self.skipExistingMediaCheckBox)

		self.downloadMediaCheckBox.stateChanged.connect(self.skipExistingMediaCheckBox.setEnabled)
		self.downloadMediaCheckBox.setChecked(True)
		self.skipExistingMediaCheckBox.setChecked(True)

		self.ignoreDownloadErrorsCheckBox = QCheckBox("Ignore download errors")
		layout.addWidget(self.ignoreDownloadErrorsCheckBox)

		layout.addWidget(QLabel("Keep in mind that it can take a substantial amount of time to download \nand import your course. Good things come to those who wait!"))

		self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, Qt.Orientation.Horizontal, self)
		self.buttons.accepted.connect(self.loadCourse)
		self.buttons.rejected.connect(self.reject)
		okButton = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
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
		return '{:s}'.format(html.escape(content.strip()))

	@staticmethod
	def prepareHtml(content):
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
		if model['did'] != deck["id"]:
			deck['mid'] = model['id']
			mw.col.decks.save(deck)

			model["did"] = deck["id"]
			mw.col.models.save(model)

	def findExistingNote(self, deckName, course, learnable):
		notes = mw.col.find_notes('deck:"{}" {}:"{}"'.format(deckName, 'Learnable', learnable.id))
		if notes:
			return mw.col.getNote(notes[0])

		return None

	def getWithSpec(self, learnable, spec):
		values = spec.get(learnable)
		if spec.field.type == memrise.Field.Text:
			return list(map(self.prepareText, values))
		elif spec.field.type == memrise.Field.Image:
			return list(map(self.prepareImage, list(filter(bool, values))))
		elif spec.field.type == memrise.Field.Audio:
			return list(map(self.prepareAudio, list(filter(bool, values))))
		elif spec.field.type == memrise.Field.Mem:
			return [self.prepareHtml(values.get())]

		return None

	@staticmethod
	def toList(values):
		if isinstance(values, str):
			return [values]
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

			noteCache = {}

			deck = None
			if self.deckSelection.currentIndex() != 0:
				deck = self.selectDeck(self.deckSelection.currentText(), merge=True)
			else:
				deck = self.selectDeck(course.title, merge=False)
			self.saveDeckUrl(deck, self.courseUrlLineEdit.text())

			for level in course:
				tags = self.getLevelTags(len(course), level)
				for learnable in level:
					if learnable.id in noteCache:
						ankiNote = noteCache[learnable.id]
					else:
						ankiNote = self.findExistingNote(deck['name'], course, learnable)
					if not ankiNote:
						model = self.modelMapper.getModel(learnable, deck)
						self.saveDeckModelRelation(deck, model)
						ankiNote = mw.col.newNote()

					mapping = self.fieldMapper.getFieldMappings(course, ankiNote.note_type())
					for field, data in list(mapping.items()):
						values = []
						for spec in data:
							values.extend(self.toList(self.getWithSpec(learnable, spec)))
						ankiNote[field] = ", ".join(values)

					if 'Level' in list(ankiNote.keys()):
						levels = set(filter(bool, list(map(str.strip, ankiNote['Level'].split(',')))))
						levels.add(str(level.index))
						ankiNote['Level'] = ', '.join(sorted(levels))

					if 'Learnable' in list(ankiNote.keys()):
						ankiNote['Learnable'] = str(learnable.id)

					for tag in tags:
						ankiNote.add_tag(tag)

					if not ankiNote.cards():
						mw.col.addNote(ankiNote)
					ankiNote.flush()
					noteCache[learnable.id] = ankiNote

					scheduleInfo = learnable.progress
					if scheduleInfo:
						template = self.templateMapper.getTemplate(learnable, ankiNote, learnable.direction)
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
									card.reps = scheduleInfo.attempts
									card.lapses = scheduleInfo.incorrect
									card.due = mw.col.sched.today + (scheduleInfo.next_date.date() - datetime.datetime.now(datetime.UTC).date()).days
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
		self.loader.ignoreDownloadErrors = self.ignoreDownloadErrorsCheckBox.isChecked()
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
		memriseCourseImporter.exec()

action = QAction("Import Memrise Course...", mw)
action.triggered.connect(startCourseImporter)
mw.form.menuTools.addAction(action)
