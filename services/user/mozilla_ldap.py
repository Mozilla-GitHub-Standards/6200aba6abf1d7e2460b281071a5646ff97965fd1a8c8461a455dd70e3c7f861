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
#   Toby Elliott (telliott@mozilla.com)
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
""" LDAP Authentication
"""
from hashlib import sha1
import random

import ldap

from services import logger
from services.user import User
from services.util import BackendError, ssha
from services.user.ldapconnection import ConnectionManager


class LDAPUser(object):
    """LDAP authentication."""

    def __init__(self, ldapuri, users_root='ou=users,dc=mozilla',
                 check_account_state=True,
                 ldap_timeout=10, **kw):
        self.check_account_state = check_account_state
        self.users_root = users_root
        self.ldap_timeout = ldap_timeout

        self.conn = ConnectionManager(ldapuri, **kw)

    def _conn(self, bind=None, passwd=None):
        return self.conn.connection(bind, passwd)

    def _purge_conn(self, bind, passwd=None):
        self.conn.purge(bind, passwd=None)

    def get_user_id(self, user):
        """Returns the id for a user name"""
        if user.get('userid'):
            return user['userid']

        #getting the dn gets it as a side effect
        self._get_dn(user)
        return user.get('userid')

    def create_user(self, user_name, password, email):
        """Creates a user. Returns a user object on success."""
        user_name = str(user_name)   # XXX only ASCII

        #First make sure the username isn't taken. There'll still be a race
        #condition, but it's pretty small
        test_user = User()
        test_user['username'] = user_name
        dn = self._get_dn(test_user)
        if dn is not None:
            return False

        user_id = self._get_next_user_id()
        password_hash = ssha(password.encode('utf8'))
        key = '%s%s' % (random.randint(0, 9999999), user_name)
        key = sha1(key).hexdigest()

        user = {'cn': user_name,
                'sn': user_name,
                'uid': user_name,
                'uidNumber': str(user_id),
                'userPassword': password_hash,
                'primaryNode': '',
                'accountStatus': 1,
                'account-enabled': 'Yes',
                'mail': email,
                'mail-verified': key,
                'objectClass': ['dataStore', 'inetOrgPerson']}

        dn = "uidNumber=%i,%s" % (user_id, self.users_root)

        #need a copy with some of the info for the return value
        userobj = User()
        userobj['username'] = user['uid']
        userobj['userid'] = user['uidNumber']
        userobj['mail'] = email
        userobj['dn'] = dn

        #need to turn the user hash into tuples
        user = user.items()

        with self._conn() as conn:
            try:
                res, __ = conn.add_s(dn, user)
            except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
                logger.debug('Could not create the user.')
                raise BackendError(str(e))

        if res == ldap.RES_ADD:
            return userobj
        else:
            return False

    def authenticate_user(self, user, password, attrs=None):
        """Authenticates a user given a user_name and password.

        Returns the user id in case of success. Returns None otherwise."""

        if not user.get('username'):
            #cannot authenticate without a username
            return None

        dn = self._get_dn(user)
        if not dn:
            return None

        if attrs is None:
            attrs = []

        if self.check_account_state and 'account-enabled' not in attrs:
            attrs.append('account-enabled')

        try:
            with self._conn(dn, password) as conn:
                result = conn.search_st(dn, ldap.SCOPE_BASE,
                                      attrlist=attrs,
                                      timeout=self.ldap_timeout)
        except (ldap.NO_SUCH_OBJECT, ldap.INVALID_CREDENTIALS):
            return None
        except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
            logger.debug('Could not authenticate the user.')
            raise BackendError(str(e))

        if result is None:
            return None

        result = result[0][1]
        if self.check_account_state and result['account-enabled'][0] != 'Yes':
            return None

        for attr in attrs:
            user[attr] = result[attr][0]
        return user['userid']

    def get_user_info(self, user, attrs):
        """Returns user info

        Args:
            user_id: user id

        Returns:
            user object populated with attrs
        """

        need = [attr for attr in attrs if not user.get(attr)]
        if need == []:
            return user

        dn = self._get_dn(user)
        if not dn:
            return user

        scope = ldap.SCOPE_BASE

        with self._conn() as conn:
            try:
                res = conn.search_st(dn, scope, attrlist=need,
                                     timeout=self.ldap_timeout)
            except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
                logger.debug('Could not get the user info in ldap.')
                raise BackendError(str(e))
            except ldap.NO_SUCH_OBJECT:
                return user

        if res is None or len(res) == 0:
            return None, None

        res = res[0][1]
        for attr in need:
            user[attr] = res.get(attr, [None])[0]
        return user

    def update_field(self, user, password, key, value):
        """Change the value of a user's field
        True if the change was successful, False otherwise
        """
        dn = self._get_dn(user)
        return self._modify_record(user, key, value, dn, password)

    def admin_update_field(self, user, key, value):
        """Change the value of a user's field using an admin bind
        True if the change was successful, False otherwise
        """
        return self._modify_record(user, key, value)

    def update_password(self, user, old_password, new_password):
        """
        Change the user password. Uses the user bind.

        Args:
            user: user object
            new_password: new password
            old_password: old password of the user

        Returns:
            True if the change was successful, False otherwise
        """
        dn = self._get_dn(user)
        password_hash = ssha(new_password.encode('utf8'))
        return self._modify_record(user, 'userPassword', password_hash,
                                   dn, old_password)

    def admin_update_password(self, user, new_password, code=None):
        """
        Change the user password. Does this as admin. This assumes that a reset
        code or something similar has already been verified by the application.

        Args:
            user: user object
            new_password: new password

        Returns:
            True if the change was successful, False otherwise
        """
        password_hash = ssha(new_password.encode('utf8'))
        return self._modify_record(user, 'userPassword', password_hash)

    def delete_user(self, user, password=None):
        """
        Deletes a user.

        Args:
            user: the user object

        Returns:
            True if the deletion was successful, False otherwise
        """
        dn = self._get_dn(user)
        if dn is None:
            return True

        try:
            with self._conn() as conn:
                try:
                    res, __ = conn.delete_s(dn)
                except ldap.NO_SUCH_OBJECT:
                    return False
                except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
                    logger.debug('Could not delete the user in ldap')
                    raise BackendError(str(e))
        except ldap.INVALID_CREDENTIALS:
            return False

        self._purge_conn(dn)
        return res == ldap.RES_DELETE

    def _modify_record(self, user, key, value, ldap_user=None, ldap_pass=None):
        """
        Change a value in the user's account.
        Uses the account passed in with ldap_user and ldap_pass.

        Args:
            user: user object
            key: field in ldap to be changed
            value: value to change the field to
            ldap_user, ldap_pass: bind information (admin or user)

        Returns:
            True if the change was successful, False otherwise
        """
        dn = self._get_dn(user)
        if dn is None:
            return False

        action = [(ldap.MOD_REPLACE, key, value)]

        try:
            with self._conn(ldap_user, ldap_pass) as conn:
                try:
                    res, __ = conn.modify_s(dn, action)
                except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
                    logger.debug('Could not update the password in ldap.')
                    raise BackendError(str(e))
        except ldap.INVALID_CREDENTIALS:
            return False

        if res != ldap.RES_MODIFY:
            return False

        user[key] = value
        return True

    def _get_dn(self, user):
        """
        Gets the user's dn from either their id or username

        Args:
            user: user object (may be updated as a side effect)
        Returns:
            user's dn or None if the user cannot be found
        """
        if user.get('dn'):
            return user['dn']

        user_id = user.get('userid')
        if user_id:
            #build it from the user id
            user['dn'] = "uidNumber=%s,%s" % (user_id, self.users_root)
            return user['dn']

        user_name = user.get('username')
        if not user_name:
            #we have nothing to do a search on
            return None

        dn = self.users_root
        scope = ldap.SCOPE_SUBTREE
        filter = '(uid=%s)' % user_name
        attrs = ['uidNumber']

        with self._conn() as conn:
            try:
                res = conn.search_st(dn, scope, filterstr=filter,
                                     attrlist=attrs, timeout=self.ldap_timeout)
            except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
                logger.debug('Could not get the user info from ldap')
                raise BackendError(str(e))
            except ldap.NO_SUCH_OBJECT:
                return None

        if res is None or len(res) == 0:
            return None

        #dn is actually the first element that comes back. Don't need attr
        user['dn'] = res[0][0]
        user['userid'] = res[0][1]['uidNumber'][0]
        return user['dn']

    def _get_next_user_id(self):
        """
        Does a ldap delete, atomically followed by an ldap add. This is so the
        delete will fail if you have a race condition and someone else
        incremented between the read and write.

        Args:
            none
        Returns:
            the next user id
        """
        dn = 'cn=maxuid,ou=users,dc=mozilla'

        #these two variables are for loop control.
        #count loops so we can kill an infinite
        flag = 0

        #since it's a race condition, we'd expect the value to change.
        previous_loop_value = None

        while flag < 10:
            # get the value
            try:
                with self._conn() as conn:
                    record = conn.search_st(dn, ldap.SCOPE_BASE,
                                          attrlist=['uidNumber'],
                                          timeout=self.ldap_timeout)
            except (ldap.NO_SUCH_OBJECT, ldap.INVALID_CREDENTIALS):
                raise BackendError("No record found to get next id")
            except (ldap.TIMEOUT, ldap.SERVER_DOWN, ldap.OTHER), e:
                raise BackendError("LDAP problem getting next id: %s" % str(e))

            if record is None:
                raise BackendError("No record found to get next id")

            value = record[0][1]['uidNumber'][0]
            if value == previous_loop_value:
                #this is bad. It means the problem isn't a race condition. Bail.
                logger.error('failed uid increment, loop value is unchanged')
                raise BackendError('unable to generate new account')
            previous_loop_value = value

            new_value = int(value) + 1

            #remove the old value (which will fail if it isn't there) and
            #atomically add the new one
            old = (ldap.MOD_DELETE, 'uidNumber', value)
            new = (ldap.MOD_ADD, 'uidNumber', str(new_value))

            with self._conn() as conn:
                try:
                    conn.modify_s(dn, [old, new])
                    #if we don't bomb out here, we have a valid id
                    return new_value
                except ldap.NO_SUCH_ATTRIBUTE, e:
                    logger.error('collision on getting next id. %i' % new_value)
                    flag = flag + 1
                    continue
                except ldap.LDAPError, e:
                    raise BackendError(str(e))
        raise BackendError("Unable to get new id after 10 tries")
