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
#   Ryan Kelly (rfkelly@mozilla.com)
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
"""Mozilla Authentication via a caching proxy.

This authentication class provides a local cache proxy of the auth data
from anothe system.  It talks to the server-whoami API to authenticate and
retrieve user account details, and caches them in a local SQL database for
to speed up future requests.

We plan to use it for a quick deployment of some server-storage nodes into
AWS.  It probably shouldn't be used in other scenarios without careful
consideration of the tradeoffs.

The use of a local SQL database as a cache has some subtle implications,
which are fine for this deployment but deserve to be called out explicitly:

    * Password changes will not be picked up straight away.  If the user
      changes their password through account-portal but leaves it unchanged
      in the sync client, the old password will continue to work until we
      decide to refresh the cache.  The timeout for this can be set in the
      config file, and even a very low timeout would still dramatically
      reduce the costs of password checking.

    * Authentication failures, however, are always treated as a cache miss.
      So if the user puts their new password into the sync client, it will
      work right away - it fails auth in the cache, is treated as a miss, and
      hits the main store where it's found to be correct.

    * Similarly, node re-assignments will not be picked up straight away.
      You'll have to wait for the cache timeout to expire before the node
      starts giving 401s to unassigned users.  Or just blow up the node
      every time you re-assigned away from it, which will clean up the cache
      as a side-effect...

"""

import time
import json

from services.http_helpers import get_url
from services.exceptions import BackendError

from services.user.sql import SQLUser, _password_to_credentials


# This is a field in the SQLUser auth database, that we're going to
# hijack to store the last-checked timestamp for user passwords.
# Inelegant, but means we can re-use the SQLUser code unchanged.
CACHE_TIMESTAMP_FIELD = "accountStatus"


class ProxyCacheUser(object):
    """Caching Proxy User backend, that keeps an SQL cache of main user db.

    This is a special-purpose User backend for doing authentication in some
    external infrastructure, such as AWS.  It re-purposes the SQL storage
    backend to act as a local cache of the remote, authoritative auth data,
    which it populates on-demand by hitting the special server-whoami web API.

    Some implementation notes:

        * Only the authenticate_user() method is implemented, since this is
          the only one used by server-storage.  All other methods will raise
          an error if you try to use them.

        * We check for account existence, verify passwords, and grab account
          details by making a single request to the server-whoami web API,
          passing the account credentials provided by the user.

        * The accountStatus db column is repurposed here to store an integer
          timestamp for the last cache refresh.  This allows us to expire
          the cache without fiddling with the underlying SQL queries etc.
          Ugly, but minimally invasive.

        * Passwords are hashed using a single iteration of sha256; this
          is very bad and should be fixed in the SQLUser backend.

    """

    def __init__(self, whoami_uri, cache_timeout=60*60, **kw):
        self.whoami_uri = whoami_uri.rstrip("/")
        self.cache_timeout = int(cache_timeout)
        # We use the accountStatus field as a timestamp to track cache
        # freshness, so make sure we don't use it for account state checking.
        kw["check_account_state"] = False
        self._cache = SQLUser(**kw)

    @_password_to_credentials
    def authenticate_user(self, user, credentials, attrs=None):
        password = credentials.get("password")
        if not password:
            return None

        # We always want to load the timestamp field, for freshness checking.
        if not attrs:
            attrs = [CACHE_TIMESTAMP_FIELD]
        else:
            attrs = list(attrs) + [CACHE_TIMESTAMP_FIELD]

        # Look locally first.  With luck, the full account exists in the cache
        # and the cached password is up-to-date.
        now = int(time.time())
        userid = self._cache.authenticate_user(user, password, attrs)
        if userid is not None:
            expiry_time = user[CACHE_TIMESTAMP_FIELD] + self.cache_timeout
            if expiry_time > now:
                return userid

        # This might have failed due to missing account, missing or expired
        # password cache, or an actual bad password.  All cases get treated
        # like a cache miss.  We make an authenticated request to the whoami
        # API, and write the returned data into the local cache.
        username = user.get("username")
        if username is None:
            return None
        code, _, body = get_url(self.whoami_uri, "GET",
                                user=username, password=password)
        if code == 401:
            return None
        if code != 200:
            raise BackendError("whoami API unexpected behaviour")

        # Now we know the account is good, write it into the cache db.
        try:
            user_data = json.loads(body)
        except ValueError:
            raise BackendError("whoami API produced invalid JSON")

        self._cache.delete_user(user)

        new_user_data = {
            "userid": user_data["userid"],
            "username": username,
            "password": password,
            "email": user_data.get("mail", ""),
            CACHE_TIMESTAMP_FIELD: now,
            "syncNode": user_data.get("syncNode", ""),
        }

        # This could fail if there's a race for a particular user,
        # but it'll just return False rather than raising an exception.
        self._cache.create_user(**new_user_data)

        user.update(new_user_data)
        return user["userid"]

    # All other methods are disabled on the proxy.
    # Only authenticate_user() is allowed.

    def get_user_id(self, user):
        raise BackendError("Disabled in ProxyCacheUser")

    def get_user_info(self, user, attrs=None):
        raise BackendError("Disabled in ProxyCacheUser")

    def create_user(self, username, password, email):
        raise BackendError("Disabled in ProxyCacheUser")

    def update_field(self, user, credentials, key, value):
        raise BackendError("Disabled in ProxyCacheUser")

    def admin_update_field(self, user, key, value):
        raise BackendError("Disabled in ProxyCacheUser")

    def update_password(self, user, credentials, new_password):
        raise BackendError("Disabled in ProxyCacheUser")

    def admin_update_password(self, user, new_password, code=None):
        raise BackendError("Disabled in ProxyCacheUser")

    def delete_user(self, user, credentials=None):
        raise BackendError("Disabled in ProxyCacheUser")
