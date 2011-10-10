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
""" Exceptions
"""

_TMP = """\
%s on %s

%s"""


class BackendError(Exception):
    """Raised when the backend is down or fails"""
    def __init__(self, msg='', server='localhost', retry_after=None,
                 request=None):
        """
        - msg, server will be dumped in str()
        - retry_after, if set to a positive integer, will be used to send
          back a Retry-After header value. If not set, a default value is
          returned. If set to 0, the header is explicitely skipped.
        - request: the original Request object, if available.
        """
        self.msg = msg
        self.server = server
        self.retry_after = retry_after
        self.request = request

    def __str__(self):
        log = _TMP % (self.__class__.__name__, self.server, self.msg)
        if self.request:
            call = '%s %s' % (self.request.method, self.request.path_info)
            log = call + '\n' + log
        return log


class BackendTimeoutError(BackendError):
    """Raised when the backend times out."""
    pass
