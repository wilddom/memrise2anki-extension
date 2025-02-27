memrise2anki-extension
======================

An extension for Anki which downloads and converts a community course from Memrise into an Anki deck.

How to install
--------------

1. Download the ankiaddon file from [github releases](https://github.com/wilddom/memrise2anki-extension/releases)
2. Open Anki
3. Go to `Tools` -> `Add-ons`
4. Click on `Install from file...`
5. Select the previously downloaded ankiaddon file
6. Restart Anki


Note type
---------

A special note type is created with separate fields for text definitions, text alternatives, attributes, images,
audio and levels. This is done because it's not possible to accurately reproduce the versatility of Memrise levels.
But having the fields separate gives the flexibility to rebuild them manually with Anki templates.
All fields can be renamed and reordered freely.

Templates (Card type)
---------------------

Templates are generated for the directions in which you are tested on Memrise. Only when the course creator creates a
level with reversed columns, we generate a template for this direction. But you are free to create your own card types
in Anki after the import. If you want to update a previously downloaded deck and the templates have been renamed manually,
a dialog will help you to assign the existing template to a testing direction.

Field mapping
-------------

The field mapper allows to freely configure the fields from Memrise to the fields of the selected note type.
Multiple Memrise fields can be merged to one note field. This allows the reuse of existing note types without much hassle.

The *Learnable*
-----------

The special field named *Learnable* is used to identify existing notes when a previously downloaded deck is updated.
This allows to update already downloaded notes without losing card statistics. Removing or renaming this field
results in duplicated entries. **Therefore you are strongly encouraged to keep this field**.

Levels
------

Memrise levels are stored in a field and notes get a corresponding tag. Creating a subdeck per level is no longer supported because
that's not the way Anki should be used ([Using Decks Appropriately](http://ankisrs.net/docs/manual.html#manydecks)). Instead 
[Filtered Decks](http://ankisrs.net/docs/am-manual.html#filtered) and the level tags can be used to learn levels separately.

Intervals
---------

Progress (intervals, due dates, etc.) from Memrise can be imported. But be cautious to not overwrite your local Anki progress in
case you want to update an already downloaded deck.

Mems
----

Unfortunately importing your mems from Memrise is no longer possible.


Bug Reports
-----------

Please report bugs and suggestions using the [github issue tracker](https://github.com/wilddom/memrise2anki-extension/issues).

Fair use
--------

Memrise is sunsetting community courses. This add-on allows you to export these courses and your learning progress.
Nevertheless, the copyright of the courses remains with the respective authors. Please respect the rights of
the authors and their work.


Credits
-------

This is more or less a complete rewrite of Pete Schlette's original addon (https://github.com/pschlette/memrise2anki-extension).
Thanks to Slava Shklyaev (https://github.com/slava-sh) for the first version of the interval import.
