memrise2anki-extension
======================

An extension for Anki 2 that downloads and converts a course from Memrise into an Anki deck.

Note type
---------

A special note type is created with separate fiels for text definitions, text alternatives, attributes, images,
audio and levels. This is done because it's not possible to accurately reproduce the versatility of Memrise levels.
But having the fields separate gives the flexibility to rebuild them manually with Anki templates.
All fields can be renamed and reordered freely.

Templates (Card type)
---------------------

Templates are generated for the directions you are tested on Memrise. Only when the course creator creates a level with
reversed columns, we generate a template for this direction. But you are free to create your own card types in Anki
after the import.

Field mapping
-------------

The field mapper allows to freely configure the fields from Memrise to the fields of the selected note type.
Multiple Memrise fields can be merged to one note field. This allows the reuse of existing note types without much hassle.

The *Thing*
-----------

The special field named *Thing* is used to identify existing notes when a previously downloaded deck is updated.
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
case you want to update an already downloaded deck. If the templates have been renamed manually, a dialog will help you to
assign the existing template to a testing direction.

Mems
----

The import of your mems from Memrise is possible. A mem is assigned to a testing direction (front->back), therefore a field needs
to be created for each direction. As Anki does not officially support embedded media (youtube, etc.) a link will be placed instead.


Bug Reports
-----------

Please report bugs with the [github issue tracker](https://github.com/wilddom/memrise2anki-extension/issues).

Fair use
--------

Good wordlists don't come for free, they are the result of a lot of work. Respect the rights of the authors and their hard work.
And please support the guys at Memrise by subscribing to [premium](https://www.memrise.com/premium/).


Credits
-------

This is more or less a complete rewrite of Pete Schlette's original addon (https://github.com/pschlette/memrise2anki-extension).
Thanks to Slava Shklyaev (https://github.com/slava-sh) for the first version of the interval import.
