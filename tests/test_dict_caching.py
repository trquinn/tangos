from __future__ import absolute_import
import tangos.core.dictionary
from tangos import testing

__author__ = 'app'

import tangos as db

def setup():
    testing.init_blank_db_for_testing()


def test_set():
    bh_obj = tangos.core.dictionary.get_or_create_dictionary_item(db.core.get_default_session(), "BH")
    assert bh_obj is not None
    bh_obj2 = tangos.core.dictionary.get_or_create_dictionary_item(db.core.get_default_session(), "BH")
    assert bh_obj2 is bh_obj