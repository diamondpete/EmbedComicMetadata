"""
A python class to encapsulate the ComicBookInfo data
"""

"""
Copyright 2012-2014  Anthony Beville

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import json
from datetime import datetime
from calibre.utils.localization import calibre_langcode_to_name, canonicalize_lang, lang_as_iso639_1
from calibre_plugins.EmbedComicMetadata.genericmetadata import GenericMetadata

import sys

if sys.version_info[0] > 2:
    unicode = str


class ComicBookInfo:

    def metadataFromString(self, string):

        cbi_container = json.loads(unicode(string, 'utf-8'))

        metadata = GenericMetadata()

        cbi = cbi_container['ComicBookInfo/1.0']

        # helper func
        # If item is not in CBI, return None
        def xlate(cbi_entry):
            if cbi_entry in cbi:
                return cbi[cbi_entry]
            else:
                return None

        metadata.series = xlate('series')
        metadata.title = xlate('title')
        metadata.issue = xlate('issue')
        metadata.publisher = xlate('publisher')
        metadata.month = xlate('publicationMonth')
        metadata.year = xlate('publicationYear')
        metadata.issueCount = xlate('numberOfIssues')
        metadata.comments = xlate('comments')
        metadata.credits = xlate('credits')
        metadata.genre = xlate('genre')
        metadata.volume = xlate('volume')
        metadata.volumeCount = xlate('numberOfVolumes')
        metadata.language = xlate('language')
        metadata.country = xlate('country')
        metadata.criticalRating = xlate('rating')
        metadata.tags = xlate('tags')
        metadata.gtin = xlate('GTIN')

        # make sure credits and tags are at least empty lists and not None
        if metadata.credits is None:
            metadata.credits = []
        if metadata.tags is None:
            metadata.tags = []

        # need to massage the language string to be ISO
        # modified to use a calibre function
        if metadata.language is not None:
            metadata.language = lang_as_iso639_1(metadata.language)

        metadata.isEmpty = False

        return metadata

    def stringFromMetadata(self, metadata):

        cbi_container = self.createJSONDictionary(metadata)
        return json.dumps(cbi_container)

    # verify that the string actually contains CBI data in JSON format
    def validateString(self, string):

        try:
            cbi_container = json.loads(string)
        except:
            return False

        return ('ComicBookInfo/1.0' in cbi_container)

    def createJSONDictionary(self, metadata):

        # Create the dictionary that we will convert to JSON text
        cbi = dict()
        cbi_container = {'appID': 'ComicTagger/',
                         'lastModified': str(datetime.now()),
                         'ComicBookInfo/1.0': cbi}

        # helper func
        def assign(cbi_entry, md_entry):
            if md_entry is not None:
                cbi[cbi_entry] = md_entry

        # helper func
        def toInt(s):
            i = None
            if type(s) in [str, unicode, int]:
                try:
                    i = int(s)
                except ValueError:
                    pass
            return i

        assign('series', metadata.series)
        assign('title', metadata.title)
        assign('issue', metadata.issue)
        assign('publisher', metadata.publisher)
        assign('publicationMonth', toInt(metadata.month))
        assign('publicationYear', toInt(metadata.year))
        assign('numberOfIssues', toInt(metadata.issueCount))
        assign('comments', metadata.comments)
        assign('genre', metadata.genre)
        assign('volume', toInt(metadata.volume))
        assign('numberOfVolumes', toInt(metadata.volumeCount))
        assign('language', calibre_langcode_to_name(canonicalize_lang(metadata.language)))
        assign('country', metadata.country)
        assign('rating', metadata.criticalRating)
        assign('credits', metadata.credits)
        assign('tags', metadata.tags)
        assign('GTIN', metadata.gtin)

        return cbi_container
