# -*- encoding: utf-8 -*-
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
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#   Rob Miller (rmiller@mozilla.com)
#   Ryan Kelly (rkelly@mozilla.com)
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

import unittest

try:
    from services.whoauth import WhoAuthentication
    REPOZEWHO = True
except ImportError:
    REPOZEWHO = False
from services.tests.test_wsgiauth import HTTPBasicAuthAPITestCases


if REPOZEWHO:

    class TestWhoAuthentication(HTTPBasicAuthAPITestCases, unittest.TestCase):
        """Tests for WhoAuthentication class in default configuration."""
        auth_class = WhoAuthentication

    class TestWhoAuthentication_NewStyleAuth(TestWhoAuthentication):
        """Tests for WhoAuthentication class using new-style auth backend."""
        BASE_CONFIG = TestWhoAuthentication.BASE_CONFIG.copy()
        BASE_CONFIG["auth.backend"] = \
                            'services.tests.test_wsgiauth.BadPasswordUserTool'

    WHO_CONFIG = {
        "who.plugin.basic.use": "repoze.who.plugins.basicauth:make_plugin",
        "who.plugin.basic.realm": "Sync",
        "who.plugin.backend.use": "services.whoauth.backendauth:make_plugin",
        "who.authenticators.plugins": "backend",
        "who.identifiers.plugins": "basic",
        "who.challengers.plugins": "basic",
        }

    class TestWhoAuthentication_FromConfig(TestWhoAuthentication):
        """Tests for WhoAuthentication class loaded from a config file"""
        BASE_CONFIG = TestWhoAuthentication.BASE_CONFIG.copy()
        BASE_CONFIG.update(WHO_CONFIG)


def test_suite():
    suite = unittest.TestSuite()
    if REPOZEWHO:
        suite.addTest(unittest.makeSuite(TestWhoAuthentication))
        suite.addTest(unittest.makeSuite(TestWhoAuthentication_NewStyleAuth))
        suite.addTest(unittest.makeSuite(TestWhoAuthentication_FromConfig))
    return suite


if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
