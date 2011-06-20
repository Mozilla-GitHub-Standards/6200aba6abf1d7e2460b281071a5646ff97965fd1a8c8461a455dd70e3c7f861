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
""" Base interface for user functions such as auth and account admin
"""

import abc
from services.pluginreg import PluginRegistry


class NoEmailError(Exception):
    """Raised when we need the user's email address and it doesn't exist."""
    pass


class NoUserIDError(Exception):
    """Raised when there's no userID fails."""
    pass


class User(dict):
    """
    A holding class for user data. One day it might be more, so better
    to put a class wrapper around it
    """
    def __init__(self, username=None, userid=None):
            self['username'] = username
            self['userid'] = userid


class ServicesUser(PluginRegistry):
    """Abstract Base Class for the authentication APIs."""

    @abc.abstractmethod
    def get_user_id(self, user):
        """Returns the id for a user name.

        Args:
            user: the user object. Will be updated as a side effect

        Returns:
            user id. None if not found.
        """

    @abc.abstractmethod
    def create_user(self, user_name, password, email):
        """Creates a user

        Args:
            - user_name: the user name
            - password: the password associated with the user
            - email: the email associated with the user

        Returns:
            a User object if the creation was successful, or False if not
        """

    @abc.abstractmethod
    def authenticate_user(self, user, password, attrs=None):
        """Authenticates a user.

        Args:
            user: a user object
            password: password
            attrs: a list of other attributes desired

        Returns:
            The user id in case of success. None otherwise. Updates the user
            object with requested attributes if they aren't already defined
        """

    @abc.abstractmethod
    def get_user_info(self, user, attrs):
        """Returns user info

        Args:
            user: the user object
            attrs: the pieces of data requested

        Returns:
            user object populated with attrs
        """

    @abc.abstractmethod
    def update_field(self, user, password, key, value):
        """Change the value of a field in the user record

        Args:
            user: user object
            password: the user's password
            key: name of the field.
            value: value to put in the field

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def admin_update_field(self, user, key, value):
        """
        Change the value of a field in the user record. Does this as admin.
        This assumes that a reset code or something similar has already
        been verified by the application, or the function is being called
        internally.

        Args:
            user: user object
            key: name of the field.
            value: value to put in the field

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def update_password(self, user, old_password, new_password):
        """
        Change the user password.

        Args:
            user: user object
            new_password: new password
            old_password: old password of the user

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def admin_update_password(self, user, new_password, code=None):
        """
        Change the user password. Does this as admin. This assumes that a reset
        code or something similar has already been verified by the application.

        Args:
            user: user object
            new_password: new password
            code: a reset code, if one needs to be proxied to a backend

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def delete_user(self, user, password=None):
        """
        Deletes a user.

        Args:
            user: the user object
            password: the user password, if one needs to be proxied
            to a backend

        Returns:
            True if the deletion was successful, False otherwise
        """
