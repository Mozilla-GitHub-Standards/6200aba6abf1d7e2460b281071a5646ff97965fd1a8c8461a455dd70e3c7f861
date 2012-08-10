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
# Portions created by the Initial Developer are Copyright (C) 2012
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
"""
Helpers for sanity-checking gevent.

This module uses gevent's tracing facilities to implement event-loop-blocking
detection.  The amount of time elapsed between greenlet switches is monitored,
and if it exceeds a configured threshold then an error log is generated.
"""

import os
import time
import traceback
import contextlib

import greenlet
import gevent.hub

from metlog.holder import CLIENT_HOLDER

# The maximum amount of time that the eventloop can be blocked
# without causing an error to be logged.
MAX_BLOCKING_TIME = float(os.environ.get("GEVENT_MAX_BLOCKING_TIME", 0.1))


# A global variable for tracking the time of the last greenlet switch.
# Since the worker uses a single OS-level thread, a global works fine.
_last_switch_time = None


# A trace function that gets executed on every greenlet switch.
# It checks how much time has elapsed and logs an error if it was excessive.
# The Hub gets an exemption, because it's allowed to block on I/O.

def switch_time_tracer(what, (origin, target)):
    global _last_switch_time
    then = _last_switch_time
    now = _last_switch_time = time.time()
    if then is not None and origin is not gevent.hub.get_hub():
        blocking_time = now - then
        if blocking_time > MAX_BLOCKING_TIME:
            err_log = "Greenlet blocked the eventloop for %.4f seconds\n"
            err_log = err_log % (blocking_time, )
            CLIENT_HOLDER.default_client.error(err_log)


# Set the trace function if possible.
# This can be disabled by setting the environment variable to zero.
if hasattr(greenlet, "settrace") and MAX_BLOCKING_TIME > 0:
    greenlet.settrace(switch_time_tracer)


# The trace function can detect blocking, but only once the code eventually
# yields back to gevent.  This will almost certainly be at some other unrelated
# point in the code, giving no clues as to what code was actually at fault.
# To narrow the blocking down to some specific chunk of code, use this
# context manager.  If execution within this context does not yield to gevent
# then an error will be logged, including a traceback.
@contextlib.contextmanager
def check_for_gevent_blocking(name=""):
    old_switch_time = _last_switch_time
    start_time = time.time()
    yield None
    end_time = time.time()
    if old_switch_time is not None and old_switch_time == _last_switch_time:
        blocking_time = end_time - start_time
        if name:
            err_log = "Code %r did not yield to gevent for %.4f seconds"
            err_log = err_log % (name, blocking_time, )
        else:
            err_log = "Code did not yield to gevent for %.4f seconds"
            err_log = err_log % (blocking_time, )
        err_log += "".join(traceback.format_stack())
        CLIENT_HOLDER.default_client.error(err_log)
