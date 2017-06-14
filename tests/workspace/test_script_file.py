# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import unittest

from pgsqltoolsservice.workspace.contracts import Position, Range, TextDocumentChangeEvent
from pgsqltoolsservice.workspace.workspace import ScriptFile


class TestScriptFile(unittest.TestCase):
    # INIT TESTS ###########################################################

    def test_init_all_params(self):
        # If: I create a script file with all the parameters provided
        uri = 'file_uri'
        buffer = 'buffer'
        path = 'file_path'
        sf = ScriptFile(uri, buffer, path)

        # Then: The state should be setup with all the provided values
        self.assertEqual(sf._file_uri, uri)
        self.assertEqual(sf.file_uri, uri)
        self.assertEqual(sf._file_path, path)
        self.assertEqual(sf.file_path, path)
        self.assertListEqual(sf._file_lines, [buffer])
        self.assertListEqual(sf.file_lines, [buffer])

    def test_init_most_params(self):
        # If: I create a script file with all the parameters provided
        uri = 'file_uri'
        buffer = 'buffer'
        sf = ScriptFile(uri, buffer, None)

        # Then: The state should be setup with all the provided values
        self.assertEqual(sf._file_uri, uri)
        self.assertEqual(sf.file_uri, uri)
        self.assertIsNone(sf._file_path)
        self.assertIsNone(sf.file_path)
        self.assertListEqual(sf._file_lines, [buffer])
        self.assertListEqual(sf.file_lines, [buffer])

    def test_init_missing_params(self):
        for value in [None, '', '  \t\t\r\n\r\n']:
            with self.assertRaises(ValueError):
                # If: I create a script file while missing a file_uri
                # Then: I expect it to raise an exception
                ScriptFile(value, 'buffer', None)

        with self.assertRaises(ValueError):
            # If: I create a script file while missing a initial buffer
            ScriptFile('file_uri', None, None)

    # GET LINE TESTS #######################################################
    def test_get_line_valid(self):
        # Setup: Create a script file with a selection of test text
        sf = ScriptFile('uri', 'abc\r\ndef\r\nghij\r\nklm', None)

        # If: I ask for a valid line
        # Then: I should get that line w/o new lines
        self.assertEqual(sf.get_line(0), 'abc')
        self.assertEqual(sf.get_line(1), 'def')
        self.assertEqual(sf.get_line(3), 'klm')

    def test_get_line_invalid(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        for line in [-100, -1, 4, 100]:
            with self.assertRaises(ValueError):
                # If: I ask for an invalid line
                # Then: I should get an exception
                sf.get_line(line)

    # GET LINES IN RANGE TESTS #############################################

    def test_get_lines_in_range_valid(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I ask for the valid lines of the file
        params = Range.from_data(1, 1, 3, 1)
        result = sf.get_lines_in_range(params)

        # Then: I should get a set of lines with the expected result
        expected_result = ['ef', 'ghij', 'kl']
        self.assertEqual(result, expected_result)

    def test_get_lines_in_range_invalid_start(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        with self.assertRaises(ValueError):
            # If: I ask for the lines of a file that have an invalid start
            # Then: I should get an exception
            params = Range.from_data(-1, 200, 2, 3)
            sf.get_lines_in_range(params)

    def test_get_lines_in_range_invalid_end(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        with self.assertRaises(ValueError):
            # If: I ask for the lines of a file that have an invalid end
            # Then: I should get an exception
            params = Range.from_data(1, 1, 300, 3000)
            sf.get_lines_in_range(params)

    # GET TEXT IN RANGE TESTS ##############################################

    def test_get_text_in_range(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I ask for the valid lines of the file
        params = Range.from_data(1, 1, 3, 1)
        result = sf.get_text_in_range(params)

        # Then: I should get a set of lines with the expected result
        expected_result = os.linesep.join(['ef', 'ghij', 'kl'])
        self.assertEqual(result, expected_result)

    # VALIDATE POSITION TESTS ##############################################

    def test_validate_position_valid(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I validate a valid position
        # Then: It should complete successfully
        sf.validate_position(Position.from_data(2, 1))

    def test_validate_position_invalid_line(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I validate an invalid line
        for line in [-100, -1, 4, 400]:
            with self.assertRaises(ValueError):
                sf.validate_position(Position.from_data(line, 1))

    def test_validate_position_invalid_col(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I validate an invalid col
        for col in [-100, -1, 4, 400]:
            with self.assertRaises(ValueError):
                sf.validate_position(Position.from_data(2, col))

    # APPLY CHANGES TESTS ##################################################

    def test_apply_change_invalid_position(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I apply a change at an invalid part of the document
        # Then:
        # ... I should get an exception throws
        with self.assertRaises(ValueError):
            params = TextDocumentChangeEvent.from_dict({
                'range': {
                    'start': {'line': 1, 'character': -1},      # Invalid character
                    'end': {'line': 3, 'character': 1}
                },
                'text': ''
            })
            sf.apply_change(params)

        # ... The text should remain the same
        self.assertListEqual(sf.file_lines, self._get_test_script_file().file_lines)

    def test_apply_change_replace(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I apply a change that replaces the text
        params = TextDocumentChangeEvent.from_dict({
            'range': {
                'start': {'line': 1, 'character': 1},
                'end': {'line': 3, 'character': 1}
            },
            'text': '12\r\n3456\r\n78'
        })
        sf.apply_change(params)

        # Then:
        # ... The text should have updated
        expected_result = [
            'abc',
            'd12',
            '3456',
            '78m'
        ]
        self.assertListEqual(sf.file_lines, expected_result)

    def test_apply_change_remove(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I apply a change that removes the text
        params = TextDocumentChangeEvent.from_dict({
            'range': {
                'start': {'line': 1, 'character': 1},
                'end': {'line': 3, 'character': 1}
            },
            'text': '1'
        })
        sf.apply_change(params)

        # Then:
        # ... The text should have updated
        expected_result = [
            'abc',
            'd1m'
        ]
        self.assertListEqual(sf.file_lines, expected_result)

    def test_apply_change_add(self):
        # Setup: Create a script file with a selection of test text
        sf = self._get_test_script_file()

        # If: I apply a change that adds text
        params = TextDocumentChangeEvent.from_dict({
            'range': {
                'start': {'line': 1, 'character': 1},
                'end': {'line': 3, 'character': 1}
            },
            'text': '\r\npgsql\r\nis\r\nawesome\r\n'
        })
        sf.apply_change(params)

        # Then:
        # ... The text should have updated
        expected_result = [
            'abc',
            'd',
            'pgsql',
            'is',
            'awesome',
            'm'
        ]
        self.assertListEqual(sf.file_lines, expected_result)

    # SET FILE CONTENTS TESTS ##############################################

    def test_set_file_contents(self):
        # If: I set the contents of a script file
        sf = ScriptFile('uri', '', None)
        sf._set_file_contents('line 1\r\n  line 2\n  line 3  ')

        # Then: I should get the expected output lines
        expected_output = [
            'line 1',
            '  line 2',
            '  line 3  '
        ]
        self.assertListEqual(sf.file_lines, expected_output)
        self.assertListEqual(sf._file_lines, expected_output)

    def test_set_file_contents_empty(self):
        # If: I set the contents of a script file to empty
        sf = ScriptFile('uri', '', None)
        sf._set_file_contents('')

        # Then: I should expect a single, empty line in the file lines
        self.assertListEqual(sf.file_lines, [''])
        self.assertListEqual(sf._file_lines, [''])

    # IMPLEMENTATION DETAILS ###############################################

    @staticmethod
    def _get_test_script_file() -> ScriptFile:
        return ScriptFile('uri', 'abc\r\ndef\r\nghij\r\nklm', None)
