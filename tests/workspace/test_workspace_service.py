# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Tuple
import unittest
from unittest.mock import MagicMock

from pgsqltoolsservice.hosting import JSONRPCServer, NotificationContext, ServiceProvider   # noqa
from pgsqltoolsservice.workspace import WorkspaceService, PGSQLConfiguration
from pgsqltoolsservice.workspace.workspace import Workspace, ScriptFile
from pgsqltoolsservice.workspace.contracts import (
    DidChangeConfigurationParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams
)
import tests.utils as utils


class TestWorkspaceService(unittest.TestCase):
    """Tests of the workspace service"""

    def test_init(self):
        # If: I create a new workspace service
        ws: WorkspaceService = WorkspaceService()

        # Then:
        # ... The service should have configuration and expose it via the property
        self.assertIsInstance(ws._configuration, PGSQLConfiguration)
        self.assertIs(ws.configuration, ws._configuration)

        # ... The service should have a workspace
        self.assertIsInstance(ws._workspace, Workspace)

        # ... The service should define callback lists
        self.assertListEqual(ws._config_change_callbacks, [])
        self.assertListEqual(ws._text_change_callbacks, [])
        self.assertListEqual(ws._text_open_callbacks, [])
        self.assertListEqual(ws._text_close_callbacks, [])

    def test_register(self):
        # Setup:
        # ... Create a mock service provider
        server: JSONRPCServer = JSONRPCServer(None, None)
        server.set_notification_handler = MagicMock()
        server.set_request_handler = MagicMock()
        sp: ServiceProvider = ServiceProvider(server, {}, utils.get_mock_logger())

        # If: I register a workspace service
        ws: WorkspaceService = WorkspaceService()
        ws.register(sp)

        # Then:
        # ... The notifications should have been registered
        server.set_notification_handler.assert_called()
        server.set_request_handler.assert_not_called()

        # ... The service provider should have been stored
        self.assertIs(ws._service_provider, sp)

    def test_register_callbacks(self):
        # Setup:
        # ... Create a workspace service
        ws: WorkspaceService = WorkspaceService()
        ws._logger = utils.get_mock_logger()

        # ... Create the list of methods to test and the list of handlers to check
        test_methods = [
            (ws.register_config_change_callback, ws._config_change_callbacks),
            (ws.register_text_change_callback, ws._text_change_callbacks),
            (ws.register_text_close_callback, ws._text_close_callbacks),
            (ws.register_text_open_callback, ws._text_open_callbacks)
        ]
        test_callback = MagicMock()

        for test_param in test_methods:
            # If: I register a callback with the workspace service
            test_param[0](test_callback)

            # Then: The callback list should be updated
            self.assertListEqual(test_param[1], [test_callback])

    def test_handle_did_change_config(self):
        # Setup: Create a workspace service with two mock config change handlers
        ws: WorkspaceService = WorkspaceService()
        ws._logger = utils.get_mock_logger()
        ws._config_change_callbacks = [MagicMock(), MagicMock()]

        # If: The workspace receives a config change notification
        nc: NotificationContext = utils.get_mock_notification_context()
        params: DidChangeConfigurationParams = DidChangeConfigurationParams.from_dict({
            'settings': {
                'pgsql': {
                    'setting': 'NonDefault'
                }
            }
        })
        ws._handle_did_change_config(nc, params)

        # Then:
        # ... No notifications should have been sent
        nc.send_notification.assert_not_called()

        # ... The config should have been updated
        self.assertIs(ws.configuration, params.settings.pgsql)

        # ... The mock config change callbacks should have been called
        for callback in ws._config_change_callbacks:
            callback.assert_called_once_with(params.settings.pgsql)

    def test_handle_text_notification_none(self):
        # Setup:
        # ... Create a workspace service with mock callbacks and a workspace that always returns None
        ws: WorkspaceService = WorkspaceService()
        ws._logger = utils.get_mock_logger()
        ws._text_change_callbacks = [MagicMock()]
        ws._text_open_callbacks = [MagicMock()]
        ws._text_close_callbacks = [MagicMock()]
        ws._workspace, sf = self._get_mock_workspace(all_none=True)

        nc: NotificationContext = utils.get_mock_notification_context()

        # ... Create a list of methods call and parameters to call them with
        test_calls = [
            (
                ws._handle_did_change_text_doc,
                self._get_change_text_doc_params(),
                ws._text_change_callbacks[0]
            ),
            (
                ws._handle_did_open_text_doc,
                self._get_open_text_doc_params(),
                ws._text_open_callbacks[0]
            ),
            (
                ws._handle_did_close_text_doc,
                self._get_close_text_doc_params(),
                ws._text_close_callbacks[0]
            )
        ]

        for call in test_calls:
            # If: The workspace service receives a request to handle a file that shouldn't be processed
            call[0](nc, call[1])

            # Then: The associated notification callback should not have been called
            call[2].assert_not_called()

    def test_handle_text_notification_success(self):
        # Setup:
        # ... Create a workspace service with a mock callback and a workspace that returns a mock script file
        ws: WorkspaceService = WorkspaceService()
        ws._logger = utils.get_mock_logger()
        ws._workspace, sf = self._get_mock_workspace(False)
        ws._text_change_callbacks = [MagicMock()]
        ws._text_open_callbacks = [MagicMock()]
        ws._text_close_callbacks = [MagicMock()]

        # ... Create a mock notification context
        nc: NotificationContext = utils.get_mock_notification_context()

        # ... Create a list of method calls and parameters to call them with
        test_calls = [
            (
                ws._handle_did_change_text_doc,
                ws._text_change_callbacks[0],
                self._get_change_text_doc_params(),
                self._test_handle_text_change_helper
            ),
            (
                ws._handle_did_open_text_doc,
                ws._text_open_callbacks[0],
                self._get_open_text_doc_params(),
                None
            ),
            (
                ws._handle_did_close_text_doc,
                ws._text_close_callbacks[0],
                self._get_close_text_doc_params(),
                None
            )
        ]

        for call in test_calls:
            # If: The workspace service receives a notification
            call[0](nc, call[2])

            # Then:
            # ... The callback should have been called with the script file
            call[1].assert_called_once_with(sf)

            # ... The notification sender should not have not been called
            nc.send_notification.assert_not_called()

            # ... Any additional validation should pass
            if call[3] is not None:
                call[3](call[2], sf)

        # ... Get, Open, and Close file should all have been called
        ws._workspace.get_file.assert_called_once()
        ws._workspace.open_file.assert_called_once()
        ws._workspace.close_file.assert_called_once()

    def test_handle_text_notification_exception(self):
        # Setup:
        # ... Create a workspace service with a workspace that always raises an exception
        ws: WorkspaceService = WorkspaceService()
        ws._logger = utils.get_mock_logger()
        ws._workspace, exp = self._get_mock_workspace(exception=True)

        # ... Create a mock notification context
        nc: NotificationContext = utils.get_mock_notification_context()

        # ... Create a list of method calls and parameters to call them with
        test_calls = [
            (ws._handle_did_change_text_doc, self._get_change_text_doc_params()),
            (ws._handle_did_open_text_doc, self._get_open_text_doc_params()),
            (ws._handle_did_close_text_doc, self._get_close_text_doc_params())
        ]

        for call in test_calls:
            # If: The workspace service gets an exception while handling the notification
            call[0](nc, call[1])

            # Then: Everything should succeed

    # IMPLEMENTATION DETAILS ###############################################

    @staticmethod
    def _test_handle_text_change_helper(params, sf):
        calls = [
            (params.content_changes[0]),
            (params.content_changes[1])
        ]
        sf.apply_change.has_calls(calls)

    @staticmethod
    def _get_change_text_doc_params() -> DidChangeTextDocumentParams:
        return DidChangeTextDocumentParams.from_dict({
            'textDocument': {
                'uri': 'someUri',
                'version': 1
            },
            'contentChanges': [
                {
                    'range': {
                        'start': {'line': 1, 'character': 1},
                        'end': {'line': 2, 'character': 3},
                    },
                    'rangeLength': 6,
                    'text': 'abcdefg'
                },
                {
                    'range': {
                        'start': {'line': 4, 'character': 2},
                        'end': {'line': 10, 'character': 4},
                    },
                    'rangeLength': 10,
                    'text': 'abcdefg'
                }
            ]
        })

    @staticmethod
    def _get_close_text_doc_params() -> DidCloseTextDocumentParams:
        return DidCloseTextDocumentParams.from_dict({
            'textDocument': {
                'uri': 'someUri',
                'languageId': 'SQL',
                'version': 2,
                'text': 'abcdef'
            }
        })

    @staticmethod
    def _get_open_text_doc_params() -> DidOpenTextDocumentParams:
        return DidOpenTextDocumentParams.from_dict({
            'textDocument': {
                'uri': 'someUri',
                'languageId': 'SQL',
                'version': 1,
                'text': 'abcdef'
            }
        })

    @staticmethod
    def _get_mock_script_file() -> ScriptFile:
        sf: ScriptFile = ScriptFile('path', 'path', '')
        sf.apply_change = MagicMock()

        return sf

    @staticmethod
    def _get_mock_workspace(all_none: bool=False, exception: bool=False) -> Tuple[Workspace, ScriptFile]:
        if exception:
            return_value = NameError()
            kwargs = {'side_effect': return_value}
        else:
            return_value = TestWorkspaceService._get_mock_script_file() if not all_none else None
            kwargs = {'return_value': return_value}

        workspace: Workspace = Workspace()
        workspace.get_file = MagicMock(**kwargs)
        workspace.open_file = MagicMock(**kwargs)
        workspace.close_file = MagicMock(**kwargs)

        return workspace, return_value
