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
import unittest
from services.metrics import timeit
from services.metrics import HELPER
from services.metrics import MetlogClient
from services.metrics import rebind_dispatcher
from services.metrics import logger
from services.metrics import MetlogHelperPlugin
from mock import Mock
from metlog.client import SEVERITY


@timeit
def some_method(x, y):
    return x * y


@timeit(logger='kwarg logger')
def some_kwarg_method(x, y):
    return x * y


class ModuleClass(object):

    @timeit
    def some_instance_method(self, x, y):
        return x * y

    @timeit(logger='instance logger')
    def some_kwarg_method(self, x, y):
        return x * y


@timeit
def d_some_method(x, y):
    return x * y


@timeit(logger='kwarg logger')
def d_some_kwarg_method(x, y):
    return x * y


class d_ModuleClass(object):

    @timeit
    def some_instance_method(self, x, y):
        return x * y

    @timeit(logger='instance logger')
    def some_kwarg_method(self, x, y):
        return x * y


from metrics_fixture import external_method
from metrics_fixture import external_kwarg_method
from metrics_fixture import ExternalClass

from metrics_fixture_disabled import d_external_method
from metrics_fixture_disabled import d_external_kwarg_method
from metrics_fixture_disabled import d_ExternalClass


class TestMetrics(unittest.TestCase):

    def setUp(self):
        HELPER.set_client(None)
        self._sender = Mock()
        self._client = MetlogClient(sender=self._sender)
        HELPER.set_client(self._client)

    def test_module_method(self):
        result = some_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        assert timer_call[1][0]['fields']['name'] == \
                'services.tests.test_metrics.some_method'

        # Check that the function has been properly clobbered
        assert some_method._decorated

    def test_external_method(self):
        result = external_method(5, 4)
        assert result == 20

        # Check that the timer was called once with the some_method
        # function name
        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        assert timer_call[1][0]['fields']['name'] == \
                'services.tests.metrics_fixture.external_method'

        # Check that the function has been properly clobbered
        assert external_method._decorated

    def test_kwarg_module_method(self):
        result = some_kwarg_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        assert timer_call[1][0]['fields']['name'] == \
                'services.tests.test_metrics.some_kwarg_method'
        assert timer_call[1][0]['logger'] == 'kwarg logger'

        # Check that the function has been properly clobbered
        assert some_kwarg_method._decorated

    def test_kwarg_external_method(self):
        result = external_kwarg_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        assert timer_call[1][0]['fields']['name'] == \
                'services.tests.metrics_fixture.external_kwarg_method'
        assert timer_call[1][0]['logger'] == 'kwarg external'

        # Check that the function has been properly clobbered
        assert external_kwarg_method._decorated


class TestClassMethods(unittest.TestCase):
    def setUp(self):
        HELPER.set_client(None)
        self._sender = Mock()
        self._client = MetlogClient(sender=self._sender)
        HELPER.set_client(self._client)

    def test_instance_method(self):
        foo = ModuleClass()
        result = foo.some_instance_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        assert timer_call[1][0]['fields']['name'] == \
                'services.tests.test_metrics:ModuleClass.some_instance_method'

        # Check that the function has been properly clobbered
        assert foo.some_instance_method._decorated

    def test_kwarg_instance_method(self):
        foo = ModuleClass()
        result = foo.some_kwarg_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        assert timer_call[1][0]['fields']['name'] == \
                'services.tests.test_metrics:ModuleClass.some_kwarg_method'
        assert timer_call[1][0]['logger'] == 'instance logger'

        # Check that the function has been properly clobbered
        assert foo.some_kwarg_method._decorated

    def test_external_method(self):
        foo = ExternalClass()
        result = foo.some_instance_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        name = 'services.tests.metrics_fixture:' + \
               'ExternalClass.some_instance_method'
        assert timer_call[1][0]['fields']['name'] == name

        # Check that the function has been properly clobbered
        assert foo.some_instance_method._decorated

    def test_external_kwarg_instance_method(self):
        foo = ExternalClass()
        result = foo.some_kwarg_method(5, 4)
        assert result == 20

        assert len(self._sender.method_calls) == 1
        timer_call = self._sender.method_calls[0]
        name = 'services.tests.metrics_fixture:' + \
                'ExternalClass.some_kwarg_method'
        assert timer_call[1][0]['fields']['name'] == name
        assert timer_call[1][0]['logger'] == 'instance logger'

        # Check that the function has been properly clobbered
        assert foo.some_kwarg_method._decorated


class TestDisabledMetrics(unittest.TestCase):

    def setUp(self):
        HELPER.set_client(None)

    def test_module_method(self):
        result = d_some_method(5, 4)
        assert result == 20
        assert not hasattr(d_some_method, '_decorated')

    def test_external_method(self):

        result = d_external_method(5, 4)
        assert result == 20
        assert not hasattr(d_external_method, '_decorated')

    def test_kwarg_module_method(self):
        result = d_some_kwarg_method(5, 4)
        assert result == 20
        assert not hasattr(d_some_kwarg_method, '_decorated')

    def test_kwarg_external_method(self):
        result = d_external_kwarg_method(5, 4)
        assert result == 20
        assert not hasattr(d_external_kwarg_method, '_decorated')


class TestDisasbledClassMethods(unittest.TestCase):
    def setUp(self):
        HELPER.set_client(None)

    def test_instance_method(self):
        foo = d_ModuleClass()
        result = foo.some_instance_method(5, 4)
        assert result == 20
        assert not hasattr(foo.some_instance_method, '_decorated')

    def test_kwarg_instance_method(self):
        foo = d_ModuleClass()
        result = foo.some_kwarg_method(5, 4)
        assert result == 20
        assert not hasattr(foo.some_kwarg_method, '_decorated')

    def test_external_method(self):
        foo = d_ExternalClass()
        result = foo.some_instance_method(5, 4)
        assert result == 20
        assert not hasattr(foo.some_instance_method, '_decorated')

    def test_external_kwarg_instance_method(self):
        foo = d_ExternalClass()
        result = foo.some_kwarg_method(5, 4)
        assert result == 20
        assert not hasattr(foo.some_kwarg_method, '_decorated')


class TestInvalidDecoration(unittest.TestCase):
    def test_nested_checks(self):
        """
        You can't time nested functions or methods
        """

        from services.metrics import timeit

        try:
            @timeit
            def nested_function(x, y):
                # This should throw an exception right away
                pass
            self.fail('This should have raised an exception right away')
        except NotImplementedError, e:
            assert e.args[0] == 'Unsupported timing method'

    def test_nested_class(self):
        class NestedClass(object):
            @timeit
            def nested_method(self, x, y):
                # This should throw an exception on first invocation
                pass

        try:
            obj = NestedClass()
            obj.nested_method(5, 2)
            raise AssertionError("Method invocation should fail")
        except NotImplementedError, e:
            assert e.args[0] == 'Unsupported timing method'

    def test_timed_class(self):
        try:
            @timeit
            class TimedClass(object):
                pass
        except NotImplementedError, e:
            assert e.args[0] == 'Unsupported timing method'


class RebindTarget(object):

    @rebind_dispatcher('rebinder')
    def some_method(self):
        return 42

    def rebinder(self):
        return 24


class NoRebindTarget(object):

    @rebind_dispatcher('rebinder')
    def some_method(self):
        return 42

    def rebinder(self):
        return 24


class TestRebindDispatch(unittest.TestCase):

    def test_rebind(self):
        HELPER.set_client(1)
        obj = RebindTarget()
        value = obj.some_method()
        assert value == 24

    def test_no_rebind(self):
        HELPER.set_client(None)
        obj = NoRebindTarget()
        value = obj.some_method()
        assert value == 42


class TestClassicLogger(unittest.TestCase):

    def test_oldstyle_logger(self):
        msgs = [(SEVERITY.DEBUG, 'debug', logger.debug),
        (SEVERITY.INFORMATIONAL, 'info', logger.info),
        (SEVERITY.WARNING, 'warning', logger.warn),
        (SEVERITY.ERROR, 'error', logger.error),
        (SEVERITY.ALERT, 'exception', logger.exception),
        (SEVERITY.CRITICAL, 'critical', logger.critical)]

        for lvl, msg, method in msgs:

            HELPER.set_client(None)
            self._sender = Mock()
            self._client = MetlogClient(sender=self._sender)
            HELPER.set_client(self._client)

            method("some %s" % msg)

            assert len(self._sender.method_calls) == 1
            timer_call = self._sender.method_calls[0]
            event = timer_call[1][0]
            assert event['logger'] == 'anonymous'
            assert event['type'] == 'oldstyle'
            assert event['payload'] == 'some %s' % msg
            assert event['severity'] == lvl

            # Check the that the 'logtext' field is being pushed 
            full_log = event['fields']['logtext']
            lvl_txt  = full_log[24:30].strip()

            # Log messages only keep the first 5 characters of the
            # text label for the severity level
            assert msg.upper()[:5] == lvl_txt
            assert full_log.endswith('some %s' % msg)


helper_config = {
    'enabled': True,
    'backend': 'services.metrics.MetlogHelperPlugin',
    'sender_backend': 'metlog.senders.ZmqPubSender',
    'sender_bindstrs': ['tcp://localhost:5585', 'tcp://localhost:5586'],
}


class TestHelperPlugin(unittest.TestCase):
    def test_create_plugin(self):
        helper = MetlogHelperPlugin(**helper_config)
        assert helper._client != None
        sender = helper._client.sender

        assert sender.__class__.__name__ == 'ZmqPubSender'
        assert sender.bindstrs == helper_config['sender_bindstrs']
