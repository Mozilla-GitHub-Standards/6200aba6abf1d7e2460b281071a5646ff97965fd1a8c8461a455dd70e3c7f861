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
"""
Various utilities
"""
import traceback
import random
import string
from hashlib import sha256, sha1, md5
import base64
import simplejson as json
import itertools
import struct
from email.mime.text import MIMEText
from email.header import Header
from rfc822 import AddressList
import smtplib
import socket
import re
import datetime
import os
import logging
import urllib2
from urlparse import urlparse, urlunparse
from decimal import Decimal, InvalidOperation
import time
import warnings

from webob.exc import HTTPBadRequest, HTTPServiceUnavailable
from webob import Response

from sqlalchemy.exc import OperationalError, TimeoutError

from services.config import Config, convert
from services import logger
from services.exceptions import BackendError, BackendTimeoutError  # NOQA


random.seed()
_RE_CODE = re.compile('[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}')


def function_moved(moved_to, follow_redirect=True):
    """This is a decorator that will emit a warning that a function has been
    moved elsewhere

    Arguments:
        moved_to: the string representing the new function name
        follow_redirect: if true, attempts to resolve the function specified in
        moved_to and calls that instead of the original function
    """
    def arg_wrapper(func):
        def moved_function(*args, **kwargs):
            from services.pluginreg import _resolve_name
            warnings.warn("%s has moved to %s" % (func.__name__, moved_to),
                          category=DeprecationWarning, stacklevel=2)
            if follow_redirect:
                new_func = _resolve_name(moved_to)
                return new_func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        return moved_function
    return arg_wrapper


def randchar(chars=string.digits + string.letters):
    """Generates a random char using urandom.

    If the system does not support it, the function fallbacks on random.choice

    See Haypo's explanation on the used formula to pick a char:
    http://bitbucket.org/haypo/hasard/src/tip/doc/common_errors.rst
    """
    try:
        pos = int(float(ord(os.urandom(1))) * 256. / 255.)
        return chars[pos % len(chars)]
    except NotImplementedError:
        return random.choice(chars)


def text_response(data, **kw):
    """Returns Response containing a plain text"""
    return Response(str(data), content_type='text/plain', **kw)


def json_response(data, **kw):
    """Returns Response containing a json string"""
    return Response(json.dumps(data, use_decimal=True),
                               content_type='application/json', **kw)


def html_response(data, **kw):
    """Returns Response containing a plain text"""
    return Response(str(data), content_type='text/html', **kw)


def newlines_response(lines, **kw):
    """Returns a Response object containing a newlines output."""
    def _convert(line):
        line = json.dumps(line, use_decimal=True).replace('\n', '\u000a')
        return '%s\n' % line

    data = [_convert(line) for line in lines]
    return Response(''.join(data), content_type='application/newlines', **kw)


def whoisi_response(lines, **kw):
    """Returns a Response object containing a whoisi output."""

    def _convert(line):
        line = json.dumps(line, use_decimal=True)
        size = struct.pack('!I', len(line))
        return '%s%s' % (size, line)

    data = [_convert(line) for line in lines]
    return Response(''.join(data), content_type='application/whoisi', **kw)


def convert_response(request, lines, **kw):
    """Returns the response in the appropriate format, depending on the accept
    request."""
    content_type = request.accept.first_match(('application/json',
                                               'application/newlines',
                                               'application/whoisi'))

    if content_type == 'application/newlines':
        return newlines_response(lines, **kw)
    elif content_type == 'application/whoisi':
        return whoisi_response(lines, **kw)

    # default response format is json
    return json_response(lines, **kw)


def time2bigint(value):
    """Encodes a float timestamp into a big int"""
    return int(value * 100)


def bigint2time(value, precision=2):
    """Decodes a big int into a timestamp.

    The returned timestamp is a 2 digits Decimal.
    """
    if value is None:   # unexistant
        return None
    res = Decimal(value) / 100
    digits = '0' * precision
    return res.quantize(Decimal('1.' + digits))


def round_time(value=None, precision=2):
    """Transforms a timestamp into a two digits Decimal.

    Arg:
        value: timestamps representation - float or str.
        If None, uses time.time()

        precision: number of digits to keep. defaults to 2.

    Return:
        A Decimal two-digits instance.
    """
    if value is None:
        value = time.time()
    if not isinstance(value, str):
        value = str(value)
    try:
        digits = '0' * precision
        return Decimal(value).quantize(Decimal('1.' + digits))
    except InvalidOperation:
        raise ValueError(value)


_SALT_LEN = 8


def _gensalt():
    """Generates a salt"""
    return ''.join([randchar() for i in range(_SALT_LEN)])


def ssha(password, salt=None):
    """Returns a Salted-SHA password

    Args:
        password: password
        salt: salt to use. If none, one is generated
    """
    password = password.encode('utf8')
    if salt is None:
        salt = _gensalt()
    ssha = base64.b64encode(sha1(password + salt).digest()
                               + salt).strip()
    return "{SSHA}%s" % ssha


def ssha256(password, salt=None):
    """Returns a Salted-SHA256 password

    Args:
        password: password
        salt: salt to use. If none, one is generated

    """
    password = password.encode('utf8')
    if salt is None:
        salt = _gensalt()
    ssha = base64.b64encode(sha256(password + salt).digest()
                               + salt).strip()
    return "{SSHA-256}%s" % ssha


def validate_password(clear, hash):
    """Validates a Salted-SHA(256) password

    Args:
        clear: password in clear text
        hash: hash of the password
    """
    if hash.startswith('{SSHA-256}'):
        real_hash = hash.split('{SSHA-256}')[-1]
        hash_meth = ssha256
    else:
        real_hash = hash.split('{SSHA}')[-1]
        hash_meth = ssha

    salt = base64.decodestring(real_hash)[-_SALT_LEN:]

    # both hash_meth take a unicode value for clear
    password = hash_meth(clear, salt)
    return password == hash


def send_email(sender, rcpt, subject, body, smtp_host='localhost',
               smtp_port=25, smtp_user=None, smtp_password=None, **kw):
    """Sends a text/plain email synchronously.

    Args:
        sender: sender address
        rcpt: recipient address
        subject: subject
        body: email body
        smtp_host: smtp server -- defaults to localhost
        smtp_port: smtp port -- defaults to 25
        smtp_user: smtp user if the smtp server requires it
        smtp_password: smtp password if the smtp server requires it

    Returns:
        tuple: (True or False, Error Message)
    """
    # preparing the message
    msg = MIMEText(body.encode('utf8'), 'plain', 'utf8')

    def _normalize_realname(field):
        address = AddressList(field).addresslist
        if len(address) == 1:
            realname, email = address[0]
            if realname != '':
                return '%s <%s>' % (str(Header(realname, 'utf8')), str(email))
        return field

    msg['From'] = _normalize_realname(sender)
    msg['To'] = _normalize_realname(rcpt)
    msg['Subject'] = Header(subject, 'utf8')

    try:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=5)
    except (smtplib.SMTPConnectError, socket.error), e:
        return False, str(e)

    # auth
    if smtp_user is not None and smtp_password is not None:
        try:
            server.login(smtp_user, smtp_password)
        except (smtplib.SMTPHeloError,
                smtplib.SMTPAuthenticationError,
                smtplib.SMTPException), e:
            return False, str(e)

    # the actual sending
    try:
        server.sendmail(sender, [rcpt], msg.as_string())
    finally:
        server.quit()

    return True, None


_USER = '(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))'
_IP_DOMAIN = '([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})'
_NAME_DOMAIN = '(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,})'
_DOMAIN = '(%s|%s)' % (_IP_DOMAIN, _NAME_DOMAIN)
_RE_EMAIL = '^%s@%s$' % (_USER, _DOMAIN)
_RE_EMAIL = re.compile(_RE_EMAIL)


def valid_email(email):
    """Checks if the email is well-formed

    Args:
        email: e-mail to check

    Returns:
        True or False
    """
    return _RE_EMAIL.match(email) is not None


def valid_password(user_name, password):
    """Checks a password strength.

    Args:
        user_name: user name associated with the password
        password: password

    Returns:
        True or False
    """
    if password is None:
        return False

    password = password.encode('utf8')

    if len(password) < 8:
        return False

    user_name = user_name.encode('utf8')
    return user_name.lower().strip() != password.lower().strip()


def convert_config(config):
    """Loads the configuration.

    If a "configuration" option is found, reads it using config.Config.
    Each section/option is then converted to "section.option" in the resulting
    mapping.
    """
    res = {}
    for key, value in config.items():
        if not isinstance(value, basestring) or not value.startswith('file:'):
            res[key] = convert(value)
            continue
        # we load the configuration and inject it in the mapping
        filename = value[len('file:'):]
        if not os.path.exists(filename):
            raise ValueError('The configuration file was not found. "%s"' % \
                            filename)

        conf = Config(filename)
        res.update(conf.get_map())

    return res


def filter_params(namespace, data, replace_dot='_', splitchar='.'):
    """Keeps only params that starts with the namespace.
    """
    params = {}
    for key, value in data.items():
        if splitchar not in key:
            continue
        skey = key.split(splitchar)
        if skey[0] != namespace:
            continue
        params[replace_dot.join(skey[1:])] = value
    return params

def batch(iterable, size=100):
    """Returns the given iterable split into batches, of size."""
    counter = itertools.count()

    def ticker(key):
        return next(counter) // size

    for key, group in itertools.groupby(iter(iterable), ticker):
        yield group

@function_moved('services.resetcodes.ResetCode._generate_reset_code', False)
def generate_reset_code():
    """Generates a reset code

    Returns:
        reset code, expiration date
    """
    from services.resetcodes import ResetCode
    rc = ResetCode()

    code = rc._generate_reset_code()
    expiration = datetime.datetime.now() + datetime.timedelta(hours=6)
    return code, expiration

@function_moved('services.resetcodes.ResetCode._check_reset_code', False)
def check_reset_code(code):
    from services.resetcodes import ResetCode
    rc = ResetCode()
    return rc._check_reset_code
    pass

class HTTPJsonBadRequest(HTTPBadRequest):
    """Allow WebOb Exception to hold Json responses.

    XXX Should be fixed in WebOb
    """
    def generate_response(self, environ, start_response):
        if self.content_length is not None:
            del self.content_length

        headerlist = [(key, value) for key, value in
                      list(self.headerlist)
                      if key != 'Content-Type']
        body = json.dumps(self.detail, use_decimal=True)
        resp = Response(body,
            status=self.status,
            headerlist=headerlist,
            content_type='application/json')
        return resp(environ, start_response)


class HTTPJsonServiceUnavailable(HTTPServiceUnavailable):
    """Allow WebOb Exception to hold Json responses.

    XXX Should be fixed in WebOb
    """
    def generate_response(self, environ, start_response):
        if self.content_length is not None:
            del self.content_length
        self.headers['Content-Type'] = 'application/json'
        body = json.dumps(self.detail, use_decimal=True)
        resp = Response(body,
            status=self.status,
            headerlist=self.headers.items())
        return resp(environ, start_response)


def email_to_idn(addr):
    """ Convert an UTF-8 encoded email address to it's IDN (punycode)
        equivalent

        this method can raise the following:
        UnicodeError -- the passed string is not Unicode valid or BIDI
        compliant
          Be sure to examine the exception cause to determine the final error.
    """
    # decode the string if passed as MIME (some MIME encodes @)
    addr = urllib2.unquote(addr).decode('utf-8')
    if '@' not in addr:
        return addr
    prefix, suffix = addr.split('@', 1)
    return "%s@%s" % (prefix.encode('idna'), suffix.encode('idna'))


@function_moved('services.user.extract_username')
def extract_username(username):
    pass


class CatchErrorMiddleware(object):
    """Middleware that catches error, log them and return a 500"""
    def __init__(self, app, logger_name='root', hook=None,
                 type='application/json'):
        self.app = app
        self.logger = logging.getLogger(logger_name)
        self.hook = hook
        self.ctype = type

    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        except:
            err = traceback.format_exc()
            hash = create_hash(err)
            self.logger.error(hash)
            self.logger.error(err)
            start_response('500 Internal Server Error',
                           [('content-type', self.ctype)])

            response = json.dumps("application error: crash id %s" % hash)
            if self.hook:
                try:
                    response = self.hook()
                except Exception:
                    pass

            return [response]


def get_url(url, method='GET', data=None, user=None, password=None, timeout=5,
            get_body=True, extra_headers=None):
    """Performs a synchronous url call and returns the status and body.

    This function is to be used to provide a gateway service.

    If the url is not answering after `timeout` seconds, the function will
    return a (504, {}, error).

    If the url is not reachable at all, the function will
    return (502, {}, error)

    Other errors are managed by the urrlib2.urllopen call.

    Args:
        - url: url to visit
        - method: method to use
        - data: data to send
        - user: user to use for Basic Auth, if needed
        - password: password to use for Basic Auth
        - timeout: timeout in seconds.
        - extra headers: mapping of headers to add
        - get_body: if set to False, the body is not retrieved

    Returns:
        - tuple : status code, headers, body
    """
    if isinstance(password, unicode):
        password = password.encode('utf-8')

    req = urllib2.Request(url, data=data)
    req.get_method = lambda: method

    if user is not None and password is not None:
        auth = base64.encodestring('%s:%s' % (user, password))
        req.add_header("Authorization", "Basic %s" % auth.strip())

    if extra_headers is not None:
        for name, value in extra_headers.items():
            req.add_header(name, value)

    try:
        res = urllib2.urlopen(req, timeout=timeout)
    except urllib2.HTTPError, e:
        if hasattr(e, 'headers'):
            headers = dict(e.headers)
        else:
            headers = {}

        if hasattr(e, 'read'):
            body = e.read()
        else:
            body = ''

        return e.code, headers, body

    except urllib2.URLError, e:
        if isinstance(e.reason, socket.timeout):
            return 504, {}, str(e)
        return 502, {}, str(e)

    if get_body:
        body = res.read()
    else:
        body = ''

    return res.getcode(), dict(res.headers), body


def proxy(request, scheme, netloc, timeout=5):
    """Proxies and return the result from the other server.

    - scheme: http or https
    - netloc: proxy location
    """
    parsed = urlparse(request.url)
    path = parsed.path
    params = parsed.params
    query = parsed.query
    fragment = parsed.fragment
    url = urlunparse((scheme, netloc, path, params, query, fragment))
    method = request.method
    data = request.body

    # copying all X- headers
    xheaders = {}
    for header, value in request.headers.items():
        if not header.startswith('X-'):
            continue
        xheaders[header] = value

    if 'X-Forwarded-For' not in request.headers:
        xheaders['X-Forwarded-For'] = request.remote_addr

    if hasattr(request, '_authorization'):
        xheaders['Authorization'] = request._authorization

    status, headers, body = get_url(url, method, data, timeout=timeout,
                                    extra_headers=xheaders)

    return Response(body, status, headers.items())


def safe_execute(engine, *args, **kwargs):
    """Execution wrapper that will raise a HTTPServiceUnavailableError
    on any OperationalError errors and log it.
    """
    try:
        return engine.execute(*args, **kwargs)
    except (OperationalError, TimeoutError), exc:
        err = traceback.format_exc()
        logger.error(err)
        raise BackendError(str(exc))


def get_source_ip(environ):
    """Extracts the source IP from the environ."""
    if 'HTTP_X_FORWARDED_FOR' in environ:
        return environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    elif 'REMOTE_ADDR' in environ:
        return environ['REMOTE_ADDR']
    return None


def create_hash(data):
    """Creates a unique hash using the data provided
    and a bit of randomness
    """
    rand = ''.join([randchar() for x in range(10)])
    data += rand
    return md5(data + rand).hexdigest()


def extract_node(node):
    """Takes a raw node result and splits it into a node and a dictionary
    of any additional key-value pairs specified"""
    vals = node.split('<')
    return vals[0], dict([val.split('=', 1) for val in vals[1:]])
