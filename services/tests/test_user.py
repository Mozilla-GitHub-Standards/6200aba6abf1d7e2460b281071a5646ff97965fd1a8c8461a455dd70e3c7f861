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

from webob import Response
from webob.exc import HTTPServiceUnavailable

from services.user import User, get_basic_auth, extract_username
from services.pluginreg import load_and_configure
from services.respcodes import ERROR_INVALID_WRITE
from services.tests.support import CAN_MOCK_WSGI, mock_wsgi
from services.exceptions import BackendError


memory_config = {'backend': 'services.user.memory.MemoryUser'}
sql_config = {'backend': 'services.user.sql.SQLUser',
              'sqluri': 'sqlite:////tmp/test.db'}
ldap_config = {'backend': 'services.user.mozilla_ldap.LDAPUser',
               'ldapuri': 'ldap://localhost',
               'bind': 'uid=admin,dc=mozilla',
               'passwd': 'secret',
               'additional': 'foo'}
sreg_config = {'backend': 'services.user.sreg.SregUser',
               'ldapuri': 'ldap://localhost',
               'bind': 'uid=admin,dc=mozilla',
               'passwd': 'secret',
               'sreg_location': 'localhost',
               'sreg_path': '',
               'sreg_scheme': 'http'}


class Request(object):

    def __init__(self, path_info, environ):
        self.path_info = path_info
        self.environ = environ


class TestUser(unittest.TestCase):

    def _tests(self, mgr):

        #clean it up first if needed
        user1_del = User()
        user1_del['username'] = 'user1'
        user2_del = User()
        user2_del['username'] = 'user2'

        mgr.delete_user(user1_del)
        mgr.delete_user(user2_del)

        user1 = mgr.create_user('user1', u'password1', 'test@mozilla.com')
        user1_id = user1['userid']
        user2 = mgr.create_user('user2', u'pásswørd1', 'test2@mozilla.com')
        user2_id = user2['userid']
        user3 = User()
        user3['username'] = 'user3'

        #make sure it can't create an existing user
        self.assertEquals(mgr.create_user('user1', 'password1',
                                          'test@moz.com'),
                          False)

        self.assertEquals(mgr.authenticate_user(user1, 'password1'), user1_id)
        self.assertEquals(mgr.authenticate_user(user2, u'pásswørd1'),
                          user2_id)

        #make sure that an empty password doesn't do bad things
        self.assertEquals(mgr.authenticate_user(user2, ''), None)

        #start with an unpopulated object
        user1_new = User()
        self.assertEquals(user1_new.get('mail', None), None)
        user1_new['username'] = 'user1'
        self.assertEquals(mgr.authenticate_user(user1_new, 'password1'),
                          user1_id)

        user1_new = mgr.get_user_info(user1_new, ['mail', 'syncNode'])

        #should now have written all the object data
        self.assertEquals(user1_new.get('mail', None), 'test@mozilla.com')
        self.assertEquals(user1_new.get('primaryNode', ''), '')

        self.assertFalse(mgr.update_field(user1_new, 'bad_password',
                                          'mail', 'test3@mozilla.com'))

        self.assertTrue(mgr.update_field(user1_new, 'password1',
                                          'mail', 'test3@mozilla.com'))

        self.assertEquals(user1_new.get('mail', None), 'test3@mozilla.com')

        self.assertTrue(mgr.admin_update_field(user1_new, 'mail',
                                               'test4@mozilla.com'))
        self.assertEquals(user1_new.get('mail', None), 'test4@mozilla.com')

        #updating a nonexistent user should fail
        self.assertFalse(mgr.admin_update_field(user3, 'mail', 'foo'))

        #does the data persist?
        user1_new = User()
        self.assertEquals(user1_new.get('mail', None), None)
        user1_new['username'] = 'user1'
        user1_new = mgr.get_user_info(user1_new, ['mail', 'syncNode'])
        self.assertEquals(user1_new.get('mail', None), 'test4@mozilla.com')

        self.assertFalse(mgr.update_password(user1_new, 'bad_password',
                                             'password2'))

        self.assertTrue(mgr.update_password(user1_new, 'password1',
                                            'password2'))

        self.assertEquals(mgr.authenticate_user(user1, 'password1'), None)
        self.assertEquals(mgr.authenticate_user(user1, 'password2'), user1_id)

        self.assertTrue(mgr.admin_update_password(user1_new, 'password3'))
        self.assertEquals(mgr.authenticate_user(user1, 'password2'), None)
        self.assertEquals(mgr.authenticate_user(user1, 'password3'), user1_id)

        self.assertTrue(mgr.delete_user(user1))
        self.assertFalse(mgr.delete_user(user1))

        #make sure user 1 can't log in after deletion and user2 can
        self.assertEquals(mgr.authenticate_user(user1, 'password3'), None)
        self.assertEquals(mgr.authenticate_user(user2, u'pásswørd1'),
                          user2_id)

    def test_user_memory(self):
        self._tests(load_and_configure(memory_config))

    def test_user_sql(self):
        try:
            import sqlalchemy  # NOQA
        except ImportError:
            return

        self._tests(load_and_configure(sql_config))

    def test_user_ldap(self):
        try:
            import ldap  # NOQA
            user1 = User()
            user1['username'] = 'test'
            mgr = load_and_configure(ldap_config)
            mgr.authenticate_user(user1, 'password1')
        except Exception:
            # we probably don't have an LDAP configured here. Don't test
            return

        self._tests(mgr)

    def test_user_sreg(self):
        if not CAN_MOCK_WSGI:
            return
        try:
            import ldap  # NOQA
        except ImportError:
            # we probably don't have an LDAP configured here. Don't test
            return

        def _fake_response():
            return Response('0')

        def _username_response():
            return Response('"user1"')

        def _user_exists_response():
            r = Response()
            r.status = '400 Bad Request'
            r.body = str(ERROR_INVALID_WRITE)
            return r

        mgr = load_and_configure(sreg_config)

        with mock_wsgi(_username_response):
            user1 = mgr.create_user('user1', 'password1', 'test@mozilla.com')

            self.assertEquals(user1['username'], 'user1')

        with mock_wsgi(_fake_response):
            self.assertTrue(mgr.admin_update_password(user1, 'newpass',
                            'key'))

            self.assertTrue(mgr.delete_user(user1, 'password1'))

        with mock_wsgi(_user_exists_response):
            self.assertFalse(mgr.create_user('user1', 'password1',
                                             'test@mozilla.com'))

    def test_get_basic_auth(self):
        token1 = 'Basic ' + base64.b64encode('tarek:tarek')
        token2 = 'Basic ' + base64.b64encode('tarektarek')
        token3 = 'Basic' + base64.b64encode('tarek:tarek')

        r1 = Request('/foo', {'HTTP_AUTHORIZATION': token1})
        username, password = get_basic_auth(r1)
        self.assertEquals(username, 'tarek')
        self.assertEquals(password, 'tarek')

        self.assertRaises(ValueError, get_basic_auth, Request('/foo',
                                             {'HTTP_AUTHORIZATION': token2}))

        username, password = get_basic_auth(Request('/foo',
                                             {'HTTP_AUTHORIZATION': token3}))
        self.assertEquals(username, False)
        self.assertEquals(password, False)

    def test_extract_username(self):
        self.assertEquals(extract_username('username'), 'username')
        self.assertEquals(extract_username('test@test.com'),
                          'u2wqblarhim5su7pxemcbwdyryrghmuk')
        # test for non A-Za-z0-9._- with no @
        self.assertRaises(ValueError, extract_username, 'user\r\nname')
        self.assertRaises(ValueError, extract_username, '%3Cscript%3E')
        self.assertRaises(ValueError, extract_username, '')
        # test unicode/punycode (straight UTF8 and urlencoded)
        self.assertEquals(extract_username('Fran%c3%a7ios@valid.test'),
                          'ym3nccfhvptfrhn7nkhhyvzgf2yl7r5y')  # proper char
        self.assertRaises(UnicodeError, extract_username,
                          'bo%EF%bb@badcharacter.test')        # bad utf-8 char
        self.assertRaises(UnicodeError, extract_username,
                          'bo%ef%bb%bc@badbidiuser.test')      # invalid BIDI

    def test_backenderrors(self):
        # this test makes sure all BackendErrors in user/sreg
        # give useful info in the TB
        if not CAN_MOCK_WSGI:
            return

        mgr = load_and_configure(sreg_config)

        def _kill():
            return HTTPServiceUnavailable()

        tarek = User('tarek')

        with mock_wsgi(_kill):
            try:
                mgr.delete_user(tarek, 'pass')
            except BackendError, err:
                res = str(err)

        wanted = ('BackendError on http://localhost/tarek\n\nUnable to delete'
                  ' the user via sreg. Received body:\n503 Service '
                  'Unavailable\n\nThe server is currently unavailable. '
                  'Please try again at a later time.\n\n   \nReceived status:'
                  ' 503')
        self.assertEqual(res, wanted)

        with mock_wsgi(_kill):
            try:
                mgr.create_user('tarek', 'pass', 'mail')
            except BackendError, err:
                res = str(err)

        wanted = ('BackendError on http://localhost/tarek\n\nUnable to create'
                  ' the user via sreg. Received body:\n503 Service '
                  'Unavailable\n\nThe server is currently unavailable. '
                  'Please try again at a later time.\n\n   \nReceived status:'
                  ' 503')

        self.assertEqual(res, wanted)

        with mock_wsgi(_kill):
            try:
                mgr.admin_update_password(tarek, 'pass', 'key')
            except BackendError, err:
                res = str(err)

        wanted = ('BackendError on http://localhost/tarek/password\n\nUnable '
                  'to change the user password via sreg. Received body:\n503 '
                  'Service Unavailable\n\nThe server is currently '
                  'unavailable. Please try again at a later time.\n\n   '
                  '\nReceived status: 503')
        self.assertEqual(res, wanted)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestUser))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
