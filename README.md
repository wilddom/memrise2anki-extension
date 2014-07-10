memrise2anki-extension
======================

An extension for Anki 2 that downloads and converts a course from Memrise into an Anki deck.

A special note type is created with separate fiels for text definitions, text alternatives, images, audio and levels.
These fields can be renamed and reordered freely. This is done because it's not possible to accurately reproduce
the versatile Memrise levels. But having the fields separate gives the flexibility to rebuild them manually with Anki templates.

The special field named *Thing* is used to identify existing notes when a previously downloaded deck is updated. This allows to
update already downloaded notes without losing card statistics. Removing or renaming this field results in duplicated entries.
Therefore you are strongly encouraged to keep this field.

Memrise levels are stored in a field and notes get a corresponding tag. Creating a subdeck per level is no longer supported because
that's not the way Anki should be used ([Using Decks Appropriately](http://ankisrs.net/docs/manual.html#manydecks)). Instead 
[Filtered Decks](http://ankisrs.net/docs/am-manual.html#filtered) and the level tags can be used to learn levels separately.

Currently the first first text column is handled as front field and the other text columns are merged as back field.
This behaviour could be changed in a future release.

Credits
-------

This is more or less a complete rewrite of Pete Schlette's original addon (https://github.com/pschlette/memrise2anki-extension).


