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
#   Ryan Kelly (rkelly@mozilla.com)
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
Authentication class based on repoze.who
"""

from webob.exc import HTTPUnauthorized
from cef import log_cef

from repoze.who.api import APIFactory
from repoze.who.config import WhoConfig

from services.pluginreg import load_and_configure

from services.whoauth.backendauth import BackendAuthPlugin


class WhoAuthentication(object):
    """Services authentication class based on repoze.who.

    This class can be used by applications that want to configure auth using
    the repoze.who framework of pluggable auth components.

    By default this class uses the services-specific BackendAuthPlugin for
    authentication, and will configure identifiers and challengers according
    to the auth schemes supported by the backend.  To override this default
    behaviour, specify who config file sections of the form::

        [who.section]
        key = value

    For example, to manually configure digest-auth as the only supported
    scheme you could use::

        [who.plugin.digest]
        use = repoze.who.plugins.digestauth
        realm = Sync

        [who.identifiers]
        plugins = digest

        [who.challengers]
        plugins = digest

    The sections will be extracted and passed to the repoze.who config loader.
    """

    def __init__(self, config):
        # Load the auth backend if specified.
        # There may not be one configured if repoze.who is going to look
        # elsewhere for credentials, e.g. in a htpasswd database.
        self.config = config
        try:
            self.backend = load_and_configure(self.config, 'auth')
        except KeyError:
            self.backend = None
        # Extract who-related settings from the config or from our defaults.
        # the configured authentication backend.
        who_settings = self._get_who_settings(self.config)
        # Build up a who.ini config file in memory.
        # Any settings of the form "A.B.C = X" get translated into
        # a config file section like "[A:B]\nC = X"
        who_ini_lines = []
        for key, value in who_settings.iteritems():
            try:
                section, var = key.rsplit(".", 1)
            except ValueError:
                pass
            else:
                section = section.replace(".", ":")
                who_ini_lines.append("[%s]" % (section,))
                who_ini_lines.append("%s = %s" % (var, value))
        # Now we can parse that config using repoze.who's own machinery.
        parser = WhoConfig("")
        parser.parse("\n".join(who_ini_lines))
        self._api_factory = APIFactory(parser.identifiers,
                                       parser.authenticators,
                                       parser.challengers,
                                       parser.mdproviders,
                                       parser.request_classifier,
                                       parser.challenge_decider)
        # Give all backend plugins access to the config.
        self._configure_backend_plugins(self._api_factory)

    def check(self, request, match):
        """Checks if the current request/match can be viewed.

        For WhoAuthentication this just delegates to the authenticate()
        API method, and uses the challenge() method if the user is not
        authorized for the request.
        """
        # Don't auth if it's not required by the match.
        if match.get('auth') != 'True':
            return

        # If they have REMOTE_USER, they've already authed.
        if "REMOTE_USER" in request.environ:
            return

        # Authenticate the user, and check against username in the match.
        api = self._api_factory(request.environ)
        identity = api.authenticate()
        if identity is None:
            self._raise_challenge(request)
        if match.get("username") not in (None, identity.get("username")):
            log_cef('Username Does Not Match URL', 7,
                    request.environ, self.config)
            self._raise_challenge(request)

        # Adjust environ to record the successful auth.
        # The identity must somehow get "userid" and "username" keys,
        # either from the authenticator or from an mdprovider.
        request.environ.pop("HTTP_AUTHORIZATION", None)
        match["user_id"] = identity["userid"]
        request.remote_user = identity["username"]
        request.environ["REMOTE_USER"] = identity["username"]

    def acknowledge(self, request, response):
        """Acknowledges successful auth back to the user.

        For repoze.who this calls the "remember" method on each IIdentifier
        plugin registered to the API.
        """
        identity = request.environ.get("repoze.who.identity", None)
        if identity is not None:
            api = self._api_factory(request.environ)
            #  Give all IIdentifiers a chance to remember the login.
            #  This is the same logic as inside the api.login() method,
            #  but without repeating the authentication step.
            for name, plugin in api.identifiers:
                i_headers = plugin.remember(request.environ, identity)
                if i_headers is not None:
                    response.headers.update(i_headers)

    def _raise_challenge(self, request):
        """Raise a HTTPUnauthorized to challenge for credentials."""
        api = self._api_factory(request.environ)
        # Get a WSGI app that will send the challenge.
        challenge_app = api.challenge()
        # If no challengers are configured, they just get 401 Unauthorized.
        if challenge_app is None:
            raise HTTPUnauthorized()
        # Otherwise, we use the response generated by the challenger.
        status, headers, app_iter = request.call_application(challenge_app)
        assert status.startswith("401 ")
        # Ensure that all IIdentifiers will forget the remembered login.
        logout_headers = api.logout()
        for header in logout_headers:
            if header not in headers:
                headers.append(header)
        raise HTTPUnauthorized(headerlist=list(headers), app_iter=app_iter,
                               request=request)

    def _get_who_settings(self, config):
        """Get a dict of settings for repoze.who from the given config.

        This method looks in the given config object for who-related settings,
        supplements them with some defaults based on the active backend, and
        returns them all as a dict.

        Default settings are provided according to the following rules:

            * if no authenticators are configured, the backend plugin
              is set as the only authenticator.
            * if not already present, a plugin called "backend" is defined
              to use services.whoauth.backendauth:BackendAuthPlugin.
            * if no challengers or identifiers are configured, then one is
              added for each auth scheme supported by the backend.

        """
        settings = config.get_section("who")
        # Add a "backend" plugin if not already present.
        if "plugin.backend.use" not in settings:
            if self.backend is not None:
                use = "services.whoauth.backendauth:make_plugin"
                settings["plugin.backend.use"] = use
        # Make "backend" the only authenticator if none are present.
        if "authenticators.plugins" not in settings:
            if self.backend is None:
                err = "WhoAuthentication default config requires an "\
                      "auth backend in your configuration"
                raise ValueError(err)
            settings["authenticators.plugins"] = "backend"
        # Ensure we have support for basic-auth if no identifiers are present.
        # Eventually we will interrogate the backend and add plugins for
        # all the auth schemes it supports.
        identifiers = settings.setdefault("identifiers.plugins", "")
        challengers = settings.setdefault("challengers.plugins", "")
        if not identifiers and not challengers:
            settings.update(self._get_basicauth_settings(settings))
            settings["identifiers.plugins"] += " basic"
            settings["challengers.plugins"] += " basic"
        return settings

    def _get_basicauth_settings(self, settings):
        """Get extra who config settings to support basic auth."""
        extra_settings = {}
        if "plugin.basic.use" not in settings:
            use = "repoze.who.plugins.basicauth:make_plugin"
            extra_settings["plugin.basic.use"] = use
            extra_settings["plugin.basic.realm"] = "Sync"
        return extra_settings

    def _configure_backend_plugins(self, api_factory):
        """Set up any extra configuration for BackendAuthPlugin instances.

        This method gives any loaded instances of BackendAuthPlugin a reference
        to the active auth backend and configuration dict.  It's a bit of a
        hack but saves having to back-reference them from the who config file.
        """
        backend_plugins = self._find_backend_plugins(api_factory)
        # If there are any, we must have a configured auth backend.
        if backend_plugins and self.backend is None:
            err = "services.whoauth.BackendAuthPlugin requires an auth "\
                  "backend to be configured."
            raise ValueError(err)
        # Give each BackendAuthPlugin the necessary references.
        for plugin in backend_plugins:
            if plugin.config is None:
                plugin.config = self.config
            if plugin.backend is None:
                plugin.backend = self.backend

    def _find_backend_plugins(self, api_factory):
        """Return set of BackendAuthPlugin objects used by the api factory."""
        # Find any configured instances of BackendAuthPlugin.
        backend_plugins = set()
        for name, plugin in api_factory.identifiers:
            if isinstance(plugin, BackendAuthPlugin):
                backend_plugins.add(plugin)
        for name, plugin in api_factory.authenticators:
            if isinstance(plugin, BackendAuthPlugin):
                backend_plugins.add(plugin)
        for name, plugin in api_factory.challengers:
            if isinstance(plugin, BackendAuthPlugin):
                backend_plugins.add(plugin)
        for name, plugin in api_factory.mdproviders:
            if isinstance(plugin, BackendAuthPlugin):
                backend_plugins.add(plugin)
        return backend_plugins
