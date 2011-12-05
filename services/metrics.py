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
#   Victor Ng (vng@mozilla.com)
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
Utility functions to instantiate the metrics logger from the sync
server configuration, as well as a decorator to time arbitrary
functions.
"""

from metlog.client import MetlogClient
from services.null import NullObject
import sys
import functools
import exceptions


def metlogger(config, klass):
    """
    Create a configured MetlogClient instance.

    Pass in the class so that the default logger_name can use the
    class name
    """
    # Just grab the caller location
    logger_name = "%s|%s" % (klass.__module__, klass.__name__)

    # Obtain the fully qualified classname of the sender class
    if config.get_section('metlog').get('disabled', True):
        return NullObject()

    fq_sender = config['metlog.sender']
    module_name = '.'.join(fq_sender.split('.')[:-1])
    cls_name = fq_sender.split('.')[-1]

    sender_module = __import__(module_name)
    for segment in module_name.split(".")[1:]:
        sender_module = getattr(sender_module, segment)
    klass = getattr(sender_module, cls_name)

    # Ok, now grab the arguments and instantiate
    config_prefix = 'metlog_%s.' % cls_name
    config_keys = [key for key in config.keys() \
            if key.startswith(config_prefix)]

    # Splice the ending off so that we can get named argument passing
    # working
    kwargs = {}
    for k in config_keys:
        argname = k.split(".")[-1]
        # Lists in the config file are always pipe delimited
        kwargs[argname] = config[k].split("|")

    sender = klass(**kwargs)
    client = MetlogClient(sender, logger_name)
    client._config = config

    return client


class MetlogHelper(object):
    """
    This is class acts as a kind of lazy proxy to the MetlogClient.
    We need this to provide late binding of the MetlogClient to the
    decorators
    """
    def __init__(self):
        self._reset()

    def _reset(self):
        """ Reset the MetlogClientHelper to it's initial state"""
        self._client = None
        self._registry = {}
        self._web_dispatcher = None

    def _resolve_fq_name(self, func, klass=None):
        """
        Resolve a fully qualified name for a function
        """
        try:
            name = "%s:%s.%s" % (klass.__module__, \
                                 klass.__name__, \
                                 func.func_name)
        except:
            name = "%s.%s" % (func.__module__, func.func_name)
        return name

    def set_client(self, client):
        """ set the metlog client on the helper """
        if client is None:
            self._reset()
            return

        self._client = client

        # update any registered functions now
        for fq_name, (fn, kwargs, ns) in self._registry.items():
            self.decorate(fn, kwargs, ns)

    def decorate(self, fn, kwargs, fq_name=None):
        """ Decorate a function with a metlog timer """
        if fq_name is None:
            fq_name = self._resolve_fq_name(fn)
        wrapped_fn = self._client.timer(fq_name, **kwargs)(fn)
        return wrapped_fn

HELPER = MetlogHelper()


def MetlogHelperPlugin():
    # this shim is required to provide access to the services.plugin
    # system
    return HELPER


def timeit(fn=None, **timer_kwargs):
    '''
    Strategy:

    This will only work on instance methods where the class is module
    level.

    If you decorate a method, the method is largely unaffected until
    you actually invoke it.

    At that time, it does a lazy import of the MetlogClientHelper and
    if the MetlogClient is defined, we grab the frame info and
    overwrite the module.class.method with a timed version.

    If no MetlogClient is defined, we overwrite the method with a pure
    undecorated version of the method.

    On this first invocation, we also need to call the wrapped method
    and return that value.

    This should work in general for any callable that is visible from
    a module level.

    Note that this means that on the very first invocation of the
    method, we will incur some overhead as we need to obtain the frame
    information of the original invocation.
    '''

    frame = sys._getframe(1)
    frame_info = getFrameInfo(frame)

    # TODO: need to do stronger checking on the stackframe to ensure
    # that we don't decorate stuff that is unsupportable
    if frame_info[0] == 'class':
        return _core_timeit_class(frame, frame_info, fn, timer_kwargs)
    elif frame_info[0] == 'module':
        return _core_timeit_module(frame, frame_info, fn, timer_kwargs)
    else:
        raise NotImplementedError("Unsupported timing method")


def _core_timeit_class(frame, frame_info, fn, timer_kwargs):
    if fn is None and timer_kwargs:
        def wrapped(func):
            return wrap_method(func, timer_kwargs)
        return wrapped
    else:
        # No kwarg @timeit
        return wrap_method(fn, timer_kwargs)


def wrap_method(fn, timer_kwargs):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        # We have to rewrite the method first invocation
        klass = args[0].__class__

        # We need to do a runtime check to make sure that
        # we are using a class that is module level
        frame = sys._getframe(1)
        frame_info = getFrameInfo(frame)
        module = frame_info[1]
        if getattr(module, klass.__name__, None) <> klass:
            raise NotImplementedError("Unsupported timing method")

        if not HELPER._client:
            setattr(klass, fn.__name__, fn)
            return fn(*args, **kwargs)

        fq_name = HELPER._resolve_fq_name(fn, klass)

        timed_func = HELPER.decorate(fn, timer_kwargs, fq_name)
        timed_func._decorated = True

        # Clobber the method
        setattr(klass, fn.__name__, timed_func)

        # Since this is the first time we've invoked the
        # function, we also need to directly invoke it

        return timed_func(*args, **kwargs)
    return inner


def _core_timeit_module(frame, frame_info, fn, timer_kwargs):
    if fn is None and timer_kwargs:
        def wrapped(func):
            return wrap_module_func(func, timer_kwargs)
        return wrapped
    else:
        # No kwarg @timeit
        return wrap_module_func(fn, timer_kwargs)


def wrap_module_func(fn, timer_kwargs):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        # We have to rewrite the module on method invocation
        frame = sys._getframe(1)
        frame_info = getFrameInfo(frame)

        module = frame_info[1]

        if not HELPER._client:
            setattr(module, fn.__name__, fn)
            return fn(*args, **kwargs)

        timed_func = HELPER.decorate(fn, timer_kwargs)
        timed_func._decorated = True

        # Clobber the function
        setattr(module, fn.__name__, timed_func)

        return timed_func(*args, **kwargs)
    return inner


def rebind_dispatcher(method_name):
    """
    Rebind this method to method_name if the MetlogClient is defined
    in the MetlogHelper.
    """
    def wrapped(func):
        """
        This decorator is used to just rebind the dispatch method so that
        we do not incur overhead on execution of controller methods when
        the metrics logging is disabled.
        """
        @functools.wraps(func)
        def inner(*args, **kwargs):
            klass = args[0].__class__
            if not HELPER._client:
                # Get rid of the decorator
                setattr(klass, func.__name__, func)
                return func(*args, **kwargs)
            else:
                new_method = getattr(klass, method_name, None)
                if not new_method:
                    msg = 'No such method: [%s]' % method_name
                    raise exceptions.LookupError(msg)
                setattr(klass, func.__name__, new_method)
                return new_method(*args, **kwargs)
        return inner
    return wrapped


def getFrameInfo(frame):
    """Return (kind,module,locals,globals) for a frame

    'kind' is one of "exec", "module", "class", "function call", or "unknown".
    """

    f_locals = frame.f_locals
    f_globals = frame.f_globals

    sameNamespace = f_locals is f_globals
    hasModule = '__module__' in f_locals
    hasName = '__name__' in f_globals

    sameName = hasModule and hasName
    sameName = sameName and f_globals['__name__'] == f_locals['__module__']

    module = hasName and sys.modules.get(f_globals['__name__']) or None

    namespaceIsModule = module and module.__dict__ is f_globals

    if not namespaceIsModule:
        # some kind of funky exec
        kind = "exec"
    elif sameNamespace and not hasModule:
        kind = "module"
    elif sameName and not sameNamespace:
        kind = "class"
    elif not sameNamespace:
        kind = "function call"
    else:
        # How can you have f_locals is f_globals, and have '__module__' set?
        # This is probably module-level code, but with a '__module__' variable.
        kind = "unknown"
    return kind, module, f_locals, f_globals
