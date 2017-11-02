# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import List

from pgsqltoolsservice.query.result_set import ResultSet, ResultSetEvents
from pgsqltoolsservice.query.data_storage import service_buffer_file_stream as file_stream, StorageDataReader
from pgsqltoolsservice.query.contracts import DbColumn, DbCellValue, ResultSetSubset  # noqa
import pgsqltoolsservice.utils as utils
import time

class FileStorageResultSet(ResultSet):

    RESULT_SET_NOT_READ_ERROR = 'Result set not read'
    RESULT_SET_START_OUT_OF_RANGE_ERROR = 'Result set start row out of range'
    RESULT_SET_ROW_COUNT_OF_RANGE_ERROR = 'Result set row count out of range'

    def __init__(self, result_set_id: int, batch_id: int, events: ResultSetEvents = None) -> None:
        ResultSet.__init__(self, result_set_id, batch_id, events)

        self._total_bytes_written = 0
        self._output_file_name = file_stream.create_file()
        self._file_offsets: List[int] = []

    @property
    def row_count(self) -> int:
        return len(self._file_offsets)

    def get_subset(self, start_index: int, end_index: int):
        if not self._has_been_read:
            raise ValueError(FileStorageResultSet.RESULT_SET_NOT_READ_ERROR)

        if start_index < 0 or start_index >= end_index:
            raise KeyError(FileStorageResultSet.RESULT_SET_START_OUT_OF_RANGE_ERROR)

        if end_index < 0:
            raise KeyError(FileStorageResultSet.RESULT_SET_ROW_COUNT_OF_RANGE_ERROR)

        rows = []

        with file_stream.get_reader(self._output_file_name) as reader:
            rows_offsets = [self._file_offsets[index] for index in range(start_index, end_index)]
            rows = [reader.read_row(offset, index, self.columns_info) for index, offset in enumerate(rows_offsets)]

        subset = ResultSetSubset()

        subset.row_count = len(rows)
        subset.rows = rows

        return subset

    def add_row(self, cursor):
        new_offset = self._append_row_to_buffer(cursor)
        self._file_offsets.append(new_offset)

    def remove_row(self, row_id: int):
        if not self._has_been_read:
            raise ValueError(FileStorageResultSet.RESULT_SET_NOT_READ_ERROR)

        del self._file_offsets[row_id]

    def update_row(self, row_id: int, cursor):
        new_offset = self._append_row_to_buffer(cursor)
        self._file_offsets[row_id] = new_offset

    def get_row(self, row_id: int) -> List[DbCellValue]:

        if not self._has_been_read:
            raise ValueError(FileStorageResultSet.RESULT_SET_NOT_READ_ERROR)

        if row_id >= self.row_count:
            raise KeyError(FileStorageResultSet.RESULT_SET_START_OUT_OF_RANGE_ERROR)

        with file_stream.get_reader(self._output_file_name) as reader:
            return reader.read_row(self._file_offsets[row_id], row_id, self.columns_info)

    def read_result_to_end(self, cursor):
        utils.validate.is_not_none('cursor', cursor)

        self._has_been_read = True
        storage_data_reader = StorageDataReader(cursor)

        with file_stream.get_writer(self._output_file_name) as writer:

            duration1, duration2, duration3, duration4, duration5, duration6, duration7, duration8, duration9 = 0,0,0,0,0,0,0,0,0

            start = time.time()
            print(start)

            while storage_data_reader.read_row():
                self._file_offsets.append(self._total_bytes_written)
                #self._total_bytes_written += writer.write_row(storage_data_reader)
                temp_res = writer.write_row(storage_data_reader, duration1, duration2, duration3, duration4, duration5, duration6, duration7,duration8,duration9)
                self._total_bytes_written += temp_res[0]

                duration1, duration2, duration3, duration4, duration5, duration6, duration7, duration8,duration9 = temp_res[1],temp_res[2],temp_res[3],temp_res[4],temp_res[5],temp_res[6], temp_res[7], temp_res[8], temp_res[9]

            self.columns_info = storage_data_reader.columns_info

            end = time.time()
            print(end)
            print("writer: ", end - start)
            print("duration1: ", duration1)
            print("duration2: ", duration2)
            print("duration3: ", duration3)
            print("duration4: ", duration4)
            print("duration5: ", duration5)
            print("duration6: ", duration6)
            print("duration7: ", duration7)
            print("duration8: ", duration8)
            print("duration9: ", duration9)


    def _append_row_to_buffer(self, cursor):

        utils.validate.is_not_none('cursor', cursor)

        if not self._has_been_read:
            raise ValueError(FileStorageResultSet.RESULT_SET_NOT_READ_ERROR)

        storage_data_reader = StorageDataReader(cursor)

        with file_stream.get_writer(self._output_file_name) as writer:
            current_file_offset = self._total_bytes_written
            writer.seek(current_file_offset)
            self._total_bytes_written += writer.write_row(storage_data_reader)
            return current_file_offset
