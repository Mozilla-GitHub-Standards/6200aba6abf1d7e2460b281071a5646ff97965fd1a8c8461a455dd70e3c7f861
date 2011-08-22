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
""" SQL user management

Users are stored with digest password (ssha256)
"""

from sqlalchemy import create_engine, Integer, String
from sqlalchemy.interfaces import PoolListener
from sqlalchemy.ext.declarative import declarative_base, Column
from sqlalchemy.sql import bindparam, select, insert, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from services.util import (validate_password, ssha256, safe_execute)
from services.user import User

_Base = declarative_base()
tables = []


class Users(_Base):
    __tablename__ = 'user'

    userid = Column(Integer, primary_key=True, nullable=False)
    username = Column(String(32), unique=True, nullable=False)
    password = Column(String(128))
    accountStatus = Column(Integer, default=1)
    mail = Column(String(64))
    mailVerified = Column(Integer, default=0)
    syncNode = Column(String(64))

users = Users.__table__
tables.append(users)


_SQLURI = 'mysql://sync:sync@localhost/sync'

_USER_ID = select([users.c.userid], users.c.username == bindparam('username'))

_USER_NAME = select([users.c.username], users.c.userid == bindparam('userid'))


class SetTextFactory(PoolListener):
    """This ensures strings are not converted to unicode on queries
    when using SQLite
    """
    def connect(self, dbapi_con, con_record):
        dbapi_con.text_factory = str


class SQLUser(object):
    """SQL authentication."""

    def __init__(self, sqluri=_SQLURI, pool_size=20, pool_recycle=60,
                 check_account_state=True, create_tables=True, no_pool=False,
                 **kw):
        sqlkw = {'logging_name': 'weaveserver'}
        if sqluri.startswith('sqlite'):
            sqlkw['listeners'] = [SetTextFactory()]
        else:
            if not no_pool:
                sqlkw['pool_size'] = int(pool_size)
                sqlkw['pool_recycle'] = int(pool_recycle)
            if sqluri.startswith('mysql'):
                sqlkw['reset_on_return'] = False
        if no_pool or sqluri.startswith('sqlite'):
            sqlkw['poolclass'] = NullPool

        self.check_account_state = check_account_state
        self._engine = create_engine(sqluri, **sqlkw)
        users.metadata.bind = self._engine
        if create_tables:
            users.create(checkfirst=True)
        self.sqluri = sqluri

    def get_user_id(self, user):
        """Returns the id for a user name"""
        user_id = user.get('userid')
        if user_id is not None:
            return user_id

        username = user['username']
        if username is None:
            return None

        res = safe_execute(self._engine, _USER_ID,
                           username=username).fetchone()
        if res is None:
            return None
        user['userid'] = res.userid
        return res.userid

    def create_user(self, username, password, email):
        """Creates a user. Returns True on success."""
        password_hash = ssha256(password)
        query = insert(users).values(username=username, mail=email,
                                     password=password_hash,
                                     accountStatus=1,
                                     primaryNode='')
        try:
            res = safe_execute(self._engine, query)
        except IntegrityError:
            #Name already exists
            return False

        if res.rowcount != 1:
            return False

        #need a copy with some of the info for the return value
        userobj = User()
        userobj['username'] = username
        userobj['userid'] = res.lastrowid
        userobj['mail'] = email

        return userobj

    def authenticate_user(self, user, password, attrs=None):
        """Authenticates a user given a user object and password.

        Returns the user id in case of success. Returns None otherwise."""
        username = user.get('username')
        if username is None:
            return False

        fields = [users.c.userid, users.c.password, users.c.accountStatus]
        if attrs is not None:
            for attr in attrs:
                fields.append(getattr(users.c, attr))
        else:
            attrs = []

        _USER_AUTH = select(fields, users.c.username == bindparam('username'))
        res = safe_execute(self._engine, _USER_AUTH,
                           username=username).fetchone()
        if res is None:
            return None

        if self.check_account_state and res.accountStatus != 1:
            # user is disabled
            return None

        if validate_password(password, res.password):
            user['userid'] = res.userid
            for attr in attrs:
                user[attr] = getattr(res, attr)
            return res.userid

    def get_user_info(self, user, attrs):
        """Returns user info

        Args:
            user: the user object
            attrs: the pieces of data requested

        Returns:
            user object populated with attrs
        """
        user_id = self.get_user_id(user)
        if user_id is None:
            return user

        attrs = [attr for attr in attrs if not user.get(attr)]
        if attrs == []:
            return user

        fields = []
        for attr in attrs:
            fields.append(getattr(users.c, attr))

        _USER_INFO = select(fields, users.c.userid == bindparam('user_id'))
        res = safe_execute(self._engine, _USER_INFO,
                           user_id=user_id).fetchone()
        if res is None:
            return user
        for attr in attrs:
            try:
                user[attr] = getattr(res, attr)
            except AttributeError:
                user[attr] = None

        return user

    def update_field(self, user, password, key, value):
        """Change the value of a user's field
        True if the change was successful, False otherwise
        """
        if not self.authenticate_user(user, password):
            return False

        #we don't have the concept of differently permissioned users here
        return self.admin_update_field(user, key, value)

    def admin_update_field(self, user, key, value):
        """Change the value of a user's field using an admin bind
        True if the change was successful, False otherwise

        The sql model doesn't have the concept of different permissions,
        """
        user_id = self.get_user_id(user)
        if user_id is None:
            return False

        query = update(users, users.c.userid == user_id, {key: value})
        res = safe_execute(self._engine, query)
        user[key] = value
        return res.rowcount == 1

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
        if not self.authenticate_user(user, old_password):
            return False

        #we don't have the concept of differently permissioned users here
        return self.admin_update_password(user, new_password)

    def admin_update_password(self, user, new_password, code=None):
        """Change the user password

        Args:
            user_id: user id
            password: new password

        Returns:
            True if the change was successful, False otherwise
        """
        password_hash = ssha256(new_password.encode('utf8'))
        return self.admin_update_field(user, 'password', password_hash)

    def delete_user(self, user, password=None):
        """
        Deletes a user. Needs to be done with admin privileges, since
        users don't have permission to do it themselves.

        Args:
            user: the user object

        Returns:
            True if the deletion was successful, False otherwise
        """
        user_id = self.get_user_id(user)
        if user_id is None:
            return False

        query = delete(users).where(users.c.userid == user_id)
        res = safe_execute(self._engine, query)
        return res.rowcount == 1
