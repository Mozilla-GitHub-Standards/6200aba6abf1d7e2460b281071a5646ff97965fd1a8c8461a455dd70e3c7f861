# -*- encoding: utf8 -*-
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
import base64
from webob.exc import HTTPUnauthorized

from services.wsgiauth import Authentication
from services.auth.dummy import DummyAuth


class Request(object):

    def __init__(self, path_info, environ):
        self.path_info = path_info
        self.environ = environ


class AuthTool(DummyAuth):

    def authenticate_user(self, *args):
        if args[0] == 'tarekbad':
            return None
        return 1


class ColonPasswordAuthTool(DummyAuth):

    def authenticate_user(self, *args):
        if args[0] == 'user' and args[1] == 'pass:word:':
            return 1
        return None


class AuthenticationTestCase(unittest.TestCase):

    def test_password_colons(self):
        # Passwords that contain colons are passed through to the
        # authentication function.
        config = {'auth.backend':
                  'services.tests.test_wsgiauth.ColonPasswordAuthTool'}
        auth = Authentication(config)
        token = 'Basic ' + base64.b64encode('user:pass:word:')
        req = Request('/1.0/tarek/info/collections',
                {'HTTP_AUTHORIZATION': token})
        res = auth.authenticate_user(req, {})
        self.assertEquals(res, 1)

    def test_authenticate_user(self):

        config = {'auth.backend': 'services.tests.test_wsgiauth.AuthTool'}
        auth = Authentication(config)
        token = 'Basic ' + base64.b64encode('tarek:tarek')
        req = Request('/1.0/tarek/info/collections', {})
        res = auth.authenticate_user(req, {})
        self.assertEquals(res, None)

        # authenticated by auth
        req = Request('/1.0/tarek/info/collections',
                {'HTTP_AUTHORIZATION': token})
        res = auth.authenticate_user(req, {})
        self.assertEquals(res, 1)

        # weird tokens should not break the function
        bad_token1 = 'Basic ' + base64.b64encode('tarektarek')
        bad_token2 = 'Basic' + base64.b64encode('tarek:tarek')
        req = Request('/1.0/tarek/info/collections',
                {'HTTP_AUTHORIZATION': bad_token1})

        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          {})
        req = Request('/1.0/tarek/info/collections',
                {'HTTP_AUTHORIZATION': bad_token2})
        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          {})
        # check a bad request to an invalid user.
        req = Request('/1.0/tarekbad',
                      {'HTTP_AUTHORIZATION': 'Basic ' +
                       base64.b64encode('tarekbad:tarek'),
                       'REQUEST_METHOD': 'TEST',
                       'PATH_INFO': 'TEST'})
        # the following options are required for cef dependency
        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          {'cef.version': '0.0',
                           'cef.vendor': 'test',
                           'cef.device_version': '0.0',
                           'cef.product': 'test',
                           'cef.file': 'test',
                            }, 'tarekbad')

    def test_bad_password(self):
        config = {'auth.backend': 'services.tests.test_wsgiauth.AuthTool'}
        auth = Authentication(config)
        password = u'И'.encode('cp866')
        token = 'tarek:%s' % password
        token = 'Basic ' + base64.b64encode(token)
        req = Request('/1.0/tarek/info/collections',
                     {'HTTP_AUTHORIZATION': token})

        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          {})
