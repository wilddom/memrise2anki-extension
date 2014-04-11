# -*- coding: utf-8 -*-

import codecs
import os.path
import re
import httplib
import time
import urllib
import urllib2
import urlparse
import Memrise_Course_Importer.uuid
from anki.importing import TextImporter
from anki.media import MediaManager
from aqt import mw
from aqt.qt import *
from BeautifulSoup import BeautifulSoup

class MemriseImportWidget(QWidget):
	TEXT_NOTE = 0
	IMAGE_NOTE = 1
	AUDIO_NOTE = 2

	def __init__(self):
		# set up the UI, basically
		super(MemriseImportWidget, self).__init__()
		self.setWindowTitle("Import Memrise Course")
		self.layout = QVBoxLayout(self)
		
		label = QLabel("Enter the home URL of the Memrise course to import\n(e.g. http://www.memrise.com/course/77958/memrise-intro-french/):")
		self.layout.addWidget(label)
		
		self.courseUrlLineEdit = QLineEdit()
		self.layout.addWidget(self.courseUrlLineEdit)
		
		importModeSelectionLayout = QHBoxLayout()
		self.layout.addLayout(importModeSelectionLayout)
		self.importModeSelection = QComboBox()
		self.importModeSelection.addItem("Update if first field matches existing note")
		self.importModeSelection.addItem("Ignore if first field matches existing note")
		self.importModeSelection.addItem("Import even if first field matches existing note")
		importModeSelectionLayout.addWidget(QLabel("Select import mode"))
		importModeSelectionLayout.addWidget(self.importModeSelection)
		self.importModeSelection.setCurrentIndex(0)
		
		patienceLabel = QLabel("Keep in mind that it can take a substantial amount of time to download \nand import your course. Good things come to those who wait!")
		self.layout.addWidget(patienceLabel)
		self.importCourseButton = QPushButton("Import course")
		self.importCourseButton.clicked.connect(self.importCourse)
		self.layout.addWidget(self.importCourseButton)
		
	# not used - the MediaManager class can provide the media directory path
	def selectMediaDirectory(self):
		fileDialog = QFileDialog()
		filename = fileDialog.getExistingDirectory(self, 'Select media folder')
		self.mediaDirectoryPathLineEdit.setText(filename)
		
	def importCourse(self):
		courseUrl = self.courseUrlLineEdit.text()
		# make sure the url given actually looks like a course home url
		if re.match('http://www.memrise.com/course/\d+/.+/', courseUrl) == None:
			self.courseUrlLineEdit.setText("Import failed. Does your URL look like the sample URL above?")
			return
			
		courseTitle, levelTitles = self.getCourseInfo(courseUrl)
		levelCount = len(levelTitles)
		
		# build list of urls for each level in the course
		levelUrls = map(lambda levelNum: format("%s%i" % (courseUrl, levelNum)), range(1, levelCount+1))
		
		# fetch notes data for each level
		memriseNotesByLevel = map(lambda levelUrl: self.getLevelNotes(levelUrl), levelUrls)
		# zip the notes data for a level together with its level title.
		levelData = zip(memriseNotesByLevel, levelTitles)
		
		
		# This looks ridiculous, sorry. Figure out how many zeroes we need
		# to order the subdecks alphabetically, e.g. if there are 100+ levels
		# we'll need to write "Level 001", "Level 002" etc.
		zeroCount = len(str(len(levelData)))
		levelNumber = 1
		
		# For each level, create an import file and import it as a deck
		for level in levelData:
			notes = level[0]
			levelTitle = level[1]
			
			if len(notes) == 0:
				continue
			
			importFilePath = self.createImportFile(notes)
			
			# import our file into Anki
			noteModel = mw.col.models.byName("Basic")
			mw.col.models.setCurrent(noteModel)
			deckTitle = format("%s::Level %s: %s" % (courseTitle, str(levelNumber).zfill(zeroCount), levelTitle))
			noteModel['did'] = mw.col.decks.id(deckTitle)
			mw.col.models.save(noteModel)
			importer = TextImporter(mw.col, importFilePath)
			importer.allowHTML = True
			importer.importMode = self.importModeSelection.currentIndex()
			importer.initMapping()
			importer.run()
			
			os.remove(importFilePath)
			levelNumber += 1
		
		# refresh deck browser so user can see the newly imported deck
		mw.deckBrowser.refresh()
		
		# bye!
		self.hide()
		
	def getCourseInfo(self, courseUrl):
		response = urllib2.urlopen(courseUrl)
		soup = BeautifulSoup(response.read())
		title = soup.find("h1", "course-name").string.strip()
		levelTitles = map(lambda x: x.string.strip(), soup.findAll("div", "level-title"))
		return title, levelTitles
		
	def getLevelNotes(self, levelUrl):
		soup = BeautifulSoup(self.downloadWithRetry(levelUrl, 3))
		
		# this looked a lot nicer when I thought I could use BS4 (w/ css selectors)
		# unfortunately Anki is still packaging BS3 so it's a little rougher
		# find the words in column a, whether they be text, image or audio
		colAParents = map(lambda x: x.find("div"), soup.findAll("div", "col_a"))
		colA = map(lambda x: (x.string, self.TEXT_NOTE), filter(lambda p: p["class"] == "text", colAParents))
		colA.extend(map(lambda x: (x.find("img")["src"], self.IMAGE_NOTE), filter(lambda p: p["class"] == "image", colAParents)))
		colA.extend(map(lambda x: (x.find("a")["href"], self.AUDIO_NOTE), filter(lambda p: p["class"] == "audio", colAParents)))
		
		# same deal for column b
		colBParents = map(lambda x: x.find("div"), soup.findAll("div", "col_b"))
		colB = map(lambda x: (x.string, self.TEXT_NOTE), filter(lambda p: p["class"] == "text", colBParents))
		colB.extend(map(lambda x: (x.find("img")["src"], self.IMAGE_NOTE), filter(lambda p: p["class"] == "image", colBParents)))
		colB.extend(map(lambda x: (x.find("a")["href"], self.AUDIO_NOTE), filter(lambda p: p["class"] == "audio", colBParents)))
		
		# pair the "fronts" and "backs" of the notes up
		# this is actually the reverse of what you might expect
		# the content in column A on memrise is typically what you're
		# expected to *produce*, so it goes on the back of the note
		return map(lambda x: self.Note(x[1], x[0]), zip(colA, colB))
		
	# Returns the path to the import file it creates	
	def createImportFile(self, notes):
		# The import file is created in the user's media directory (and deleted afterward)
		# Find where the media directory is and use a UUID for the filename
		mediaDirectoryPath = MediaManager(mw.col, None).dir()
		importFilename = Memrise_Course_Importer.uuid.uuid4().hex
		importPath = os.path.join(mediaDirectoryPath, importFilename + ".txt")
		importFile = codecs.open(importPath, 'w', 'utf-8')
		
		# prep each note and add it to the import file
		for note in notes:
			note.makeImportReady()
			importFile.write(note.toText())
			
		return importPath
		
	def downloadWithRetry(self, url, tryCount):
		if tryCount <= 0:
			return ""

		try:
			return urllib2.urlopen(url).read()
		except httplib.BadStatusLine:
			# not clear why this error occurs (seemingly randomly),
			# so I regret that all we can do is wait and retry.
			time.sleep(0.1)
			return self.downloadWithRetry(url, tryCount-1)

	class Note:	
		def __init__(self, front, back):
			self.Front = self.Side(front[0], front[1])
			self.Back = self.Side(back[0], back[1])

		def toText(self):
			typeFormatting =	{	
									MemriseImportWidget.TEXT_NOTE: '%s',
									MemriseImportWidget.IMAGE_NOTE: '<img src="%s">',
									MemriseImportWidget.AUDIO_NOTE: '[sound:%s]'
								}
			frontText = format(typeFormatting[self.Front.Type] % (self.Front.Content,))
			backText = format(typeFormatting[self.Back.Type] % (self.Back.Content,))
			return format("%s\t%s\n" % (frontText, backText))
			
		def makeImportReady(self):
			# Replace links to images and audio on the Memrise servers
			# by downloading the content to the user's media dir
			mediaDirectoryPath = MediaManager(mw.col, None).dir()
			for side in [self.Front, self.Back]:
				# If it's not a text note, we'll need to download the media first
				# (whether that's an audio file or an image)
				if side.Type != MemriseImportWidget.TEXT_NOTE:
					memrisePath = urlparse.urlparse(side.Content).path
					contentExtension = os.path.splitext(memrisePath)[1]
					localName = format("%s%s" % (Memrise_Course_Importer.uuid.uuid4(), contentExtension))
					fullMediaPath = os.path.join(mediaDirectoryPath, localName)
					mediaFile = open(fullMediaPath, "wb")
					mediaFile.write(urllib2.urlopen(side.Content).read())
					mediaFile.close()
					side.Content = localName
			
		class Side:
			def __init__(self, content, type):
				self.Content = content
				self.Type = type

def startCourseImporter():
	mw.memriseCourseImporter = MemriseImportWidget()
	mw.memriseCourseImporter.show()

action = QAction("Import Memrise Course...", mw)
mw.connect(action, SIGNAL("triggered()"), startCourseImporter)
mw.form.menuTools.addAction(action)