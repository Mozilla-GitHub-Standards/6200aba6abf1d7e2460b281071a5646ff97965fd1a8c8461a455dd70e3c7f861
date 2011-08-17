# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Sync Server
#
# The Initial Developer of the Original Code is the Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
"""Tests for test.support
"""
import unittest
import logging

from services import logger
from services.tests.support import capture_logs


class TestSupport(unittest.TestCase):

    def setUp(self):
        self.old = logger.level
        self.disabled = logger.disabled
        logger.disabled = 0
        logger.setLevel(logging.DEBUG)
        self.root = logging.getLogger()
        self.root_level = self.root.level
        self.root.setLevel(logging.DEBUG)
        self.rhandlers = self.root.handlers[:]
        self.root.handlers[:] = []

    def tearDown(self):
        logger.setLevel(self.old)
        logger.disabled = self.disabled
        self.root.setLevel(self.root_level)
        self.root.handlers[:] = self.rhandlers

    def test_graberrors(self):
        # simpler case: services logger, error level
        with capture_logs() as errors:
            logger.error('Yeah')

        self.assertEqual(errors.read(), 'Yeah\n')

        # services logger, warning level
        with capture_logs(level=logging.WARNING) as wrn:
            logger.debug('Yeah')
            logger.warning('Yeah2')

        self.assertEqual(wrn.read(), 'Yeah2\n')

        # root logger, warning
        root = logging.getLogger()
        with capture_logs(logger='root', level=logging.WARNING) as wrn:
            root.debug('Yeah')
            root.warning('Yeah2')

        self.assertEqual(wrn.read(), 'Yeah2\n')
