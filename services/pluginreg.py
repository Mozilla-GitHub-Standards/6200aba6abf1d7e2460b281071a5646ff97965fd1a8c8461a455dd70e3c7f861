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
"""
Base plugin class with registration mechanism and configuration reading.
"""
import abc
from services.util import filter_params


def _resolve_name(name):
    """Resolves the name and returns the corresponding object."""
    ret = None
    parts = name.split('.')
    cursor = len(parts)
    module_name = parts[:cursor]

    while cursor > 0:
        try:
            ret = __import__('.'.join(module_name))
            break
        except ImportError:
            if cursor == 0:
                raise
            cursor -= 1
            module_name = parts[:cursor]

    for part in parts[1:]:
        try:
            ret = getattr(ret, part)
        except AttributeError:
            raise ImportError(name)

    if ret is None:
        raise ImportError(name)

    return ret


def load_and_configure(config, section=None, cls_param='backend'):
    """given a config file, extracts the class name, imports the class and
    returns an instance configured with the rest of the config file

    Can be used to load up classes that don't inherit from PluginRegistry,
    but will not do any validation that it implements required methods.

    Args:
        config: a configuration object
        section: the section of the config object to use in configuring.
            If the config file has already been filtered, do not pass this in.
        cls_param: the name of the parameter in that section of the config
            that defines the class to be used

    Returns:
        An instanciated object of the requested class if the change was
        successful, False otherwise
    """
    params = config
    if section:
        params = filter_params(section, params)

    backend_name = params[cls_param]
    backend = None
    try:
        backend = _resolve_name(backend_name)
    except ImportError:
        msg = ('Unknown fully qualified name for the backend:'
               ' %r') % backend_name
        raise KeyError(msg)
    if backend is None:
        raise KeyError('No plugin registered for "%s"' % backend_name)

    del params['backend']

    # now returning an instance
    return backend(**params)


class PluginRegistry(object):
    """Abstract Base Class for plugins."""
    __metaclass__ = abc.ABCMeta

    # Name for the family of plugins, defined at the class-level
    plugin_type = ''

    @classmethod
    def _get_backend_class(cls, name):
        try:
            klass = _resolve_name(name)
        except ImportError:
            msg = ('Unknown fully qualified name for the backend: %r') % name
            raise KeyError(msg)

        # let's register it
        cls.register(klass)
        return klass

    @classmethod
    def get_from_config(cls, config, section=None, cls_name_field='backend'):
        """Get a plugin from a config file."""
        if section:
            config = filter_params(section, config)
        backend_name = config[cls_name_field]
        del config[cls_name_field]
        return cls.get(backend_name, **config)

    @classmethod
    def get(cls, name, **params):
        """Instanciates a plugin given its fully qualified name."""
        klass = cls._get_backend_class(name)
        return klass(**params)

    @classmethod
    def __subclasshook__(cls, klass):
        for method in cls.__abstractmethods__:
            if any(method in base.__dict__ for base in klass.__mro__):
                continue
            raise TypeError('Missing "%s" in "%s"' % (method, klass))
        if klass not in cls._abc_registry:
            cls._abc_registry.add(klass)
        return True
