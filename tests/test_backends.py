# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Backend tests."""


from collections import defaultdict
from contextlib import contextmanager
import os
import shutil
import tempfile
import unittest

import charmhelpers
import shelltoolbox

import backend
import utils


def get_mixin_names(test_backend):
    return tuple(b.__class__.__name__ for b in test_backend.mixins)


class GotEmAllDict(defaultdict):
    """A dictionary that returns the same default value for all given keys."""

    def get(self, key, default=None):
        return self.default_factory()


class TestBackendProperties(unittest.TestCase):
    """Ensure the correct mixins and property values are collected."""

    def test_staging_backend(self):
        test_backend = backend.Backend(config={
            'sandbox': False, 'staging': True, 'builtin-server': False})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('ImprovMixin', 'GuiMixin', 'HaproxyApacheMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl', 'zookeeper')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_sandbox_backend(self):
        test_backend = backend.Backend(config={
            'sandbox': True, 'staging': False, 'builtin-server': False})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('SandboxMixin', 'GuiMixin', 'HaproxyApacheMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_python_backend(self):
        test_backend = backend.Backend(config={
            'sandbox': False, 'staging': False, 'builtin-server': False})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('PythonMixin', 'GuiMixin', 'HaproxyApacheMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_go_backend(self):
        # Monkeypatch utils.CURRENT_DIR.
        base_dir = tempfile.mkdtemp()
        orig_current_dir = utils.CURRENT_DIR
        utils.CURRENT_DIR = tempfile.mkdtemp(dir=base_dir)
        # Create a fake agent file.
        agent_path = os.path.join(base_dir, 'agent.conf')
        open(agent_path, 'w').close()
        test_backend = backend.Backend(config={
            'sandbox': False, 'staging': False, 'builtin-server': False})
        # Cleanup.
        utils.CURRENT_DIR = orig_current_dir
        shutil.rmtree(base_dir)
        # Tests
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('GoMixin', 'GuiMixin', 'HaproxyApacheMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(
                ('apache2', 'curl', 'haproxy', 'openssl', 'python-yaml')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)


class TestBackendCommands(unittest.TestCase):

    def setUp(self):
        self.called = {}
        self.alwaysFalse = GotEmAllDict(lambda: False)
        self.alwaysTrue = GotEmAllDict(lambda: True)

        # Monkeypatch functions.
        self.utils_mocks = {
            'compute_build_dir': utils.compute_build_dir,
            'fetch_api': utils.fetch_api,
            'fetch_gui_from_branch': utils.fetch_gui_from_branch,
            'fetch_gui_release': utils.fetch_gui_release,
            'find_missing_packages': utils.find_missing_packages,
            'get_api_address': utils.get_api_address,
            'get_npm_cache_archive_url': utils.get_npm_cache_archive_url,
            'parse_source': utils.parse_source,
            'prime_npm_cache': utils.prime_npm_cache,
            'save_or_create_certificates': utils.save_or_create_certificates,
            'setup_apache': utils.setup_apache,
            'setup_gui': utils.setup_gui,
            'start_agent': utils.start_agent,
            'start_improv': utils.start_improv,
            'write_apache_config': utils.write_apache_config,
            'write_builtin_server_startup': utils.write_builtin_server_startup,
            'write_gui_config': utils.write_gui_config,
            'write_haproxy_config': utils.write_haproxy_config,
        }
        self.charmhelpers_mocks = {
            'log': charmhelpers.log,
            'open_port': charmhelpers.open_port,
            'service_control': charmhelpers.service_control,
        }

        def make_mock_function(name):
            def mock_function(*args, **kwargs):
                self.called[name] = True
                return (None, None)
            mock_function.__name__ = name
            return mock_function

        for name in self.utils_mocks.keys():
            setattr(utils, name, make_mock_function(name))
        for name in self.charmhelpers_mocks.keys():
            setattr(charmhelpers, name, make_mock_function(name))

        @contextmanager
        def mock_su(user):
            self.called['su'] = True
            yield
        self.orig_su = shelltoolbox.su
        shelltoolbox.su = mock_su

        def mock_apt_get_install(*debs):
            self.called['apt_get_install'] = True
        self.orig_apt_get_install = shelltoolbox.apt_get_install
        shelltoolbox.apt_get_install = mock_apt_get_install

        def mock_run(*debs):
            self.called['run'] = True
        self.orig_run = shelltoolbox.run
        shelltoolbox.run = mock_run

        # Monkeypatch directories.
        self.orig_juju_dir = utils.JUJU_DIR
        self.orig_sys_init_dir = backend.SYS_INIT_DIR
        self.temp_dir = tempfile.mkdtemp()
        utils.JUJU_DIR = self.temp_dir
        backend.SYS_INIT_DIR = self.temp_dir

    def tearDown(self):
        # Cleanup directories.
        backend.SYS_INIT_DIR = self.orig_sys_init_dir
        utils.JUJU_DIR = self.orig_juju_dir
        shutil.rmtree(self.temp_dir)
        # Undo the monkeypatching.
        shelltoolbox.run = self.orig_run
        shelltoolbox.apt_get_install = self.orig_apt_get_install
        shelltoolbox.su = self.orig_su
        for name, orig_fun in self.charmhelpers_mocks.items():
            setattr(charmhelpers, name, orig_fun)
        for name, orig_fun in self.utils_mocks.items():
            setattr(utils, name, orig_fun)

    def test_install_python(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.install()
        for mocked in (
            'apt_get_install', 'fetch_api', 'find_missing_packages', 'log',
            'setup_apache'
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_install_improv_builtin(self):
        test_backend = backend.Backend(config=self.alwaysTrue)
        test_backend.install()
        for mocked in (
            'apt_get_install', 'fetch_api', 'find_missing_packages', 'log',
            'run',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_start_agent(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.start()
        for mocked in (
            'compute_build_dir', 'open_port', 'service_control', 'start_agent',
            'su', 'write_apache_config', 'write_gui_config',
            'write_haproxy_config',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_start_improv_builtin(self):
        test_backend = backend.Backend(config=self.alwaysTrue)
        test_backend.start()
        for mocked in (
            'compute_build_dir', 'open_port', 'service_control',
            'start_improv', 'su', 'write_builtin_server_startup',
            'write_gui_config',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_stop(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.stop()
        for mocked in (
            'service_control', 'su'
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))


class TestBackendUtils(unittest.TestCase):

    def test_same_config(self):
        test_backend = backend.Backend(
            config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
            prev_config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
        )
        self.assertFalse(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))

    def test_different_config(self):
        test_backend = backend.Backend(
            config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
            prev_config={
                'sandbox': True, 'staging': False, 'builtin-server': False},
        )
        self.assertTrue(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))
