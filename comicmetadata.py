from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, dloraine'
__docformat__ = 'restructuredtext en'

from functools import partial
from calibre.utils.zipfile import ZipFile

from calibre_plugins.EmbedComicMetadata.config import prefs
from calibre_plugins.EmbedComicMetadata.genericmetadata import GenericMetadata
from calibre_plugins.EmbedComicMetadata.comicinfoxml import ComicInfoXml
from calibre_plugins.EmbedComicMetadata.comicbookinfo import ComicBookInfo


class ComicMetadata:
    '''
    An object for calibre to interact with comic metadata.
    '''

    def __init__(self, book_id, ia):
        # initialize the attributes
        self.book_id = book_id
        self.ia = ia
        self.db = ia.gui.current_db.new_api
        self.calibre_metadata = self.db.get_metadata(book_id)
        self.cbi_metadata = None
        self.cix_metadata = None
        self.calibre_md_in_comic_format = None
        self.comic_md_in_calibre_format = None
        self.comic_metadata = None
        self.checked_for_metadata = False
        self.file = None
        self.zipinfo = None

        # get the comic formats
        if self.db.has_format(book_id, "cbz"):
            self.format = "cbz"
        elif self.db.has_format(book_id, "cbr"):
            self.format = "cbr"
        else:
            self.format = None

        # generate a string with the books info, to show in the completion dialog
        if self.calibre_metadata.series:
            self.info = "{}: {} - ".format(self.calibre_metadata.series, self.calibre_metadata.series_index)
        self.info += "{} - {}".format(self.calibre_metadata.title, self.calibre_metadata.authors[0])

    def get_comic_metadata_from_file(self):
        if self.checked_for_metadata:
            return
        if self.format == "cbz":
            self.get_comic_metadata_from_cbz()
        elif self.format == "cbr":
            self.get_comic_metadata_from_cbr()
        self.checked_for_metadata = True

    def add_updated_comic_to_calibre(self):
        self.db.add_format(self.book_id, "cbz", self.file)

    def import_comic_metadata_to_calibre(self, comic_metadata):
        self.convert_comic_md_to_calibre_md(comic_metadata)
        self.db.set_metadata(self.book_id, self.comic_md_in_calibre_format)

    def overlay_metadata(self, comic_metadata):
        # make sure we have the metadata
        self.get_comic_metadata_from_file()
        # make the metadata generic, if none exists now
        if comic_metadata is None:
            comic_metadata = GenericMetadata()
        self.convert_calibre_md_to_comic_md()
        comic_metadata.overlay(self.calibre_md_in_comic_format)

    def embed_cix_metadata(self):
        '''
        Embeds the cix_metadata
        '''
        self.overlay_metadata(self.cix_metadata)
        cix_string = ComicInfoXml().stringFromMetadata(self.cix_metadata)

        # ensure we have a temp file
        self.make_temp_cbz_file()
        zf = ZipFile(self.file, "a")
        # save the metadata in the file
        if self.zipinfo is not None:
            zf.replacestr(self.zipinfo, cix_string.decode('utf-8', 'ignore'))
        else:
            zf.writestr("ComicInfo.xml", cix_string.decode('utf-8', 'ignore'))
        zf.close()

    def embed_cbi_metadata(self):
        '''
        Embeds the cbi_metadata
        '''
        self.overlay_metadata(self.cbi_metadata)
        cbi_string = ComicBookInfo().stringFromMetadata(self.cbi_metadata)

        # ensure we have a temp file
        self.make_temp_cbz_file()
        # save the metadata in the comment
        writeZipComment(self.file, cbi_string)

    def convert_calibre_md_to_comic_md(self):
        '''
        Maps the entries in the calibre metadata to comictagger metadata
        '''
        from calibre.utils.html2text import html2text
        from calibre.utils.date import UNDEFINED_DATE
        from calibre.utils.localization import lang_as_iso639_1

        if self.calibre_md_in_comic_format:
            return

        self.calibre_md_in_comic_format = GenericMetadata()
        mi = self.calibre_metadata

        # shorten some functions
        role = partial(set_role, credits=self.calibre_md_in_comic_format.credits)
        update_field = partial(update_comic_field, target=self.calibre_md_in_comic_format)

        # update the fields of comic metadata
        update_field("title", mi.title)
        role("Writer", mi.authors)
        update_field("series", mi.series)
        update_field("issue", mi.series_index)
        update_field("tags", mi.tags)
        update_field("publisher", mi.publisher)
        update_field("criticalRating", mi.rating)
        # need to check for None
        if mi.comments:
            update_field("comments", html2text(mi.comments))
        if mi.language:
            update_field("language", lang_as_iso639_1(mi.language))
        if mi.pubdate != UNDEFINED_DATE:
            update_field("year", mi.pubdate.year)
            update_field("month", mi.pubdate.month)
            update_field("day", mi.pubdate.day)

        # custom columns
        field = partial(self.db.field_for, book_id=self.book_id)

        # artists
        role("Penciller", field(prefs['penciller_column']))
        role("Inker", field(prefs['inker_column']))
        role("Colorist", field(prefs['colorist_column']))
        role("Letterer", field(prefs['letterer_column']))
        role("CoverArtist", field(prefs['cover_artist_column']))
        role("Editor", field(prefs['editor_column']))
        # others
        update_field("storyArc", field(prefs['storyarc_column']))
        update_field("characters", field(prefs['characters_column']))
        update_field("teams", field(prefs['teams_column']))
        update_field("locations", field(prefs['locations_column']))
        update_field("volume", field(prefs['volume_column']))
        update_field("genre", field(prefs['genre_column']))

    def convert_comic_md_to_calibre_md(self, comic_metadata):
        '''
        Maps the entries in the comic_metadata to calibre metadata
        '''
        import unicodedata
        from calibre.ebooks.metadata import MetaInformation
        from calibre.utils.date import parse_only_date
        from datetime import date
        from calibre.utils.localization import calibre_langcode_to_name

        if self.comic_md_in_calibre_format:
            return

        # synonyms for artists
        WRITER = ['writer', 'plotter', 'scripter']
        PENCILLER = ['artist', 'penciller', 'penciler', 'breakdowns']
        INKER = ['inker', 'artist', 'finishes']
        COLORIST = ['colorist', 'colourist', 'colorer', 'colourer']
        LETTERER = ['letterer']
        COVER_ARTIST = ['cover', 'covers', 'coverartist', 'cover artist']
        EDITOR = ['editor']

        # start with a fresh calibre metadata
        mi = MetaInformation(None, None)
        co = comic_metadata

        # shorten some functions
        role = partial(get_role, credits=co.credits)
        update_field = partial(update_calibre_field, target=mi)

        # Get title, if no title, try to assign series infos
        if co.title:
            mi.title = co.title
        elif co.series:
            mi.title = co.series
            if co.issue:
                mi.title += " " + str(co.issue)
        else:
            mi.title = ""

        # tags
        if co.tags != [] and prefs['import_tags']:
            if prefs['overwrite_calibre_tags']:
                mi.tags = co.tags
            else:
                mi.tags = list(set(self.calibre_metadata.tags + co.tags))

        # simple metadata
        update_field("authors", role(WRITER))
        update_field("series", co.series)
        update_field("rating", co.criticalRating)
        update_field("publisher", co.publisher)
        # special cases
        if co.language:
            update_field("language", calibre_langcode_to_name(co.language))
        if co.comments:
            update_field("comments", co.comments.strip())
        # issue
        if co.issue:
            if isinstance(co.issue, unicode):
                mi.series_index = unicodedata.numeric(co.issue)
            else:
                mi.series_index = float(co.issue)
        # pub date
        puby = co.year
        pubm = co.month
        if puby is not None:
            try:
                dt = date(int(puby), 6 if pubm is None else int(pubm), 15)
                dt = parse_only_date(str(dt))
                mi.pubdate = dt
            except:
                pass

        # custom columns
        custom_cols = self.db.field_metadata.custom_field_metadata()
        update_column = partial(update_custom_column, calibre_metadata=mi, custom_cols=custom_cols)
        # artists
        update_column(prefs['penciller_column'], role(PENCILLER))
        update_column(prefs['inker_column'], role(INKER))
        update_column(prefs['colorist_column'], role(COLORIST))
        update_column(prefs['letterer_column'], role(LETTERER))
        update_column(prefs['cover_artist_column'], role(COVER_ARTIST))
        update_column(prefs['editor_column'], role(EDITOR))
        # others
        update_column(prefs['storyarc_column'], co.storyArc)
        update_column(prefs['characters_column'], co.characters)
        update_column(prefs['teams_column'], co.teams)
        update_column(prefs['locations_column'], co.locations)
        update_column(prefs['volume_column'], co.volume)
        update_column(prefs['genre_column'], co.genre)

        self.comic_md_in_calibre_format = mi

    def make_temp_cbz_file(self):
        if not self.file and self.format == "cbz":
            self.file = self.db.format(self.book_id, "cbz", as_path=True)

    def delete_temp_cbz_file(self):
        delete_temp_file(self.file)

    def convert_to_cbz(self):
        '''
        Converts a cbr-comic to a cbz-comic
        '''
        from calibre.ptempfile import TemporaryFile, TemporaryDirectory
        from calibre.utils.unrar import RARFile, extract

        with TemporaryDirectory('_cbr2cbz') as tdir:
            # extract the rar file
            ffile = self.db.format(self.book_id, "cbr", as_path=True)
            extract(ffile, tdir)
            # get the comment
            with open(ffile, 'rb') as stream:
                zr = RARFile(stream, get_comment=True)
                comment = zr.comment
            delete_temp_file(ffile)

            # make the cbz file
            with TemporaryFile("comic.cbz") as tf:
                zf = ZipFile(tf, "w")
                zf.add_dir(tdir)
                zf.close()
                # write comment
                if comment:
                    writeZipComment(tf, comment)
                # add the cbz format to calibres library
                self.db.add_format(self.book_id, "cbz", tf)
                self.format = "cbz"

    def update_cover(self):
        # get the calibre cover
        cover_path = self.db.cover(self.book_id, as_path=True)
        fmt = cover_path.rpartition('.')[-1]
        new_cover_name = "00000000_cover." + fmt

        # open the zipfile
        self.make_temp_cbz_file()
        zf = ZipFile(self.file, "a")

        # search for a previously embeded cover
        cover_info = ""
        for name in zf.namelist():
            if name.rsplit(".", 1)[0] == "00000000_cover":
                cover_info = name
                break

        # save the metadata in the file
        if cover_info != "":
            zf.delete(cover_info)
        zf.write(cover_path, new_cover_name)
        zf.close()
        delete_temp_file(cover_path)

    def get_comic_metadata_from_cbz(self):
        '''
        Reads the comic metadata from the comic cbz file as comictagger metadata
        '''
        self.make_temp_cbz_file()
        # open the zipfile
        zf = ZipFile(self.file)

        # get cix metadata
        for name in zf.namelist():
            if name.lower() == "comicinfo.xml":
                self.cix_metadata = ComicInfoXml().metadataFromString(zf.read(name))
                self.zipinfo = zf.getinfo(name)
                break

        # get the cbi metadata
        if ComicBookInfo().validateString(zf.comment):
            self.cbi_metadata = ComicBookInfo().metadataFromString(zf.comment)
        zf.close()

        # get combined metadata
        self._get_combined_metadata()

    def get_comic_metadata_from_cbr(self):
        '''
        Reads the comic metadata from the comic cbr file as comictagger metadata
        and returns the metadata depending on do_action
        '''
        from calibre.utils.unrar import RARFile, extract_member, names

        ffile = self.db.format(self.book_id, "cbr", as_path=True)
        with open(ffile, 'rb') as stream:
            # get the cix metadata
            fnames = list(names(stream))
            for name in fnames:
                if name.lower() == "comicinfo.xml":
                    self.cix_metadata = extract_member(stream, match=None, name=name)[1]
                    self.cix_metadata = ComicInfoXml().metadataFromString(self.cix_metadata)
                    break

            # get the cbi metadata
            zr = RARFile(stream, get_comment=True)
            comment = zr.comment
            if ComicBookInfo().validateString(comment):
                self.cbi_metadata = ComicBookInfo().metadataFromString(comment)

        delete_temp_file(ffile)
        self._get_combined_metadata()

    def _get_combined_metadata(self):
        '''
        Combines the metadata from both sources
        '''
        self.comic_metadata = GenericMetadata()
        if self.cbi_metadata is not None:
            self.comic_metadata.overlay(self.cbi_metadata, False)
        if self.cix_metadata is not None:
            self.comic_metadata.overlay(self.cix_metadata, False)
        if self.cbi_metadata is None and self.cix_metadata is None:
            self.comic_metadata = None


# Helper Functions
# ------------------------------------------------------------------------------

def update_comic_field(field, source, target):
    '''
    Sets the attribute field of target to the value of source
    '''
    if source:
        setattr(target, field, source)


def update_calibre_field(field, source, target):
    '''
    Sets the attribute field of target to the value of source
    '''
    if source:
        target.set(field, source)


def update_custom_column(col_name, value, calibre_metadata, custom_cols):
    '''
    Updates the given custom column with the name of col_name to value
    '''
    if col_name and value:
        col = custom_cols[col_name]
        col['#value#'] = value
        calibre_metadata.set_user_metadata(col_name, col)


def get_role(role, credits):
    '''
    Gets a list of persons with the given role.
    First primary persons, then all others, alphabetically
    '''
    from calibre_plugins.EmbedComicMetadata.config import prefs

    persons = []
    for credit in credits:
        if credit['role'].lower() in role:
            persons.append(credit['person'])
    if persons and len(persons) > 0 and prefs['swap_names']:
        persons = swap_authors_names(persons)
    return persons


def set_role(role, persons, credits):
    '''
    Sets all persons with the given role to credits
    '''
    if persons and len(persons) > 0:
        for person in persons:
            credit = dict()
            person = swap_author_names_back(person)
            credit['person'] = person
            credit['role'] = role
            credits.append(credit)


def swap_authors_names(authors):
    '''
    Swaps the names of all names in authors to "LN, FN"
    '''
    from calibre.ebooks.metadata import author_to_author_sort

    swaped_authors = []
    for author in authors:
        if ',' not in author:
            author = author_to_author_sort(author)
        swaped_authors.append(author)
    return swaped_authors


def swap_author_names_back(author):
    if author is None:
        return author
    if ',' in author:
        parts = author.split(',')
        if len(parts) <= 1:
            return author
        surname = parts[0]
        return '%s %s' % (' '.join(parts[1:]), surname)
    return author


def delete_temp_file(ffile):
    try:
        import os
        if os.path.exists(ffile):
            os.remove(ffile)
    except:
        pass


def writeZipComment(filename, comment):
    '''
    This is a custom function for writing a comment to a zip file,
    since the built-in one doesn't seem to work on Windows and Mac OS/X

    Fortunately, the zip comment is at the end of the file, and it's
    easy to manipulate.  See this website for more info:
    see: http://en.wikipedia.org/wiki/Zip_(file_format)#Structure
    '''
    from os import stat
    from struct import pack

    # get file size
    statinfo = stat(filename)
    file_length = statinfo.st_size

    try:
        fo = open(filename, "r+b")

        # the starting position, relative to EOF
        pos = -4

        found = False
        value = bytearray()

        # walk backwards to find the "End of Central Directory" record
        while (not found) and (-pos != file_length):
            # seek, relative to EOF
            fo.seek(pos, 2)

            value = fo.read(4)

            # look for the end of central directory signature
            if bytearray(value) == bytearray([0x50, 0x4b, 0x05, 0x06]):
                found = True
            else:
                # not found, step back another byte
                pos = pos - 1
            # print pos,"{1} int: {0:x}".format(bytearray(value)[0], value)

        if found:

            # now skip forward 20 bytes to the comment length word
            pos += 20
            fo.seek(pos, 2)

            # Pack the length of the comment string
            format = "H"                   # one 2-byte integer
            comment_length = pack(format, len(comment))  # pack integer in a binary string

            # write out the length
            fo.write(comment_length)
            fo.seek(pos + 2, 2)

            # write out the comment itself
            fo.write(comment)
            fo.truncate()
            fo.close()
        else:
            raise Exception('Failed to write comment to zip file!')
    except:
        return False
    else:
        return True
