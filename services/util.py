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
Various utilities
"""
import traceback
import random
import string
from hashlib import sha256, sha1, md5
import base64
import simplejson as json
import itertools
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
from decimal import Decimal, InvalidOperation
import time
import warnings

from webob.exc import HTTPBadRequest, HTTPServiceUnavailable
from webob import Response

from sqlalchemy.exc import OperationalError, TimeoutError

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


def batch(iterable, size=100):
    """Returns the given iterable split into batches, of size."""
    counter = itertools.count()

    def ticker(key):
        return next(counter) // size

    for key, group in itertools.groupby(iter(iterable), ticker):
        yield group


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


@function_moved('services.user.extract_username')
def extract_username(username):
    pass


@function_moved('services.formatters.text_response')
def text_response(data, **kw):
    pass


@function_moved('services.formatters.json_response')
def json_response(data, **kw):
    pass


@function_moved('services.formatters.html_response')
def html_response(data, **kw):
    pass


@function_moved('services.formatters.newlines_response')
def newlines_response(lines, **kw):
    pass


@function_moved('services.formatters.whoisi_response')
def whoisi_response(lines, **kw):
    pass


@function_moved('services.formatters.convert_response')
def convert_response(request, lines, **kw):
    pass


@function_moved('services.http_helpers.get_url')
def get_url(url, method='GET', data=None, user=None, password=None, timeout=5,
            get_body=True, extra_headers=None):
    pass


@function_moved('services.http_helpers.proxy')
def proxy(request, scheme, netloc, timeout=5):
    pass


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
