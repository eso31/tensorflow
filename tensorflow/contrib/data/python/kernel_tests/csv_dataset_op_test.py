#  Copyright 2018 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for CsvDatasetOp."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import tempfile
import time

import numpy as np

from tensorflow.contrib.data.python.ops import readers
from tensorflow.python.client import session
from tensorflow.python.data.ops import readers as core_readers
from tensorflow.python.framework import constant_op
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import errors
from tensorflow.python.framework import ops
from tensorflow.python.ops import gen_parsing_ops
from tensorflow.python.platform import gfile
from tensorflow.python.platform import googletest
from tensorflow.python.platform import test


class CsvDatasetOpTest(test.TestCase):

  def _assert_datasets_equal(self, g, ds1, ds2):
    assert ds1.output_shapes == ds2.output_shapes, ('output_shapes differ: %s, '
                                                    '%s') % (ds1.output_shapes,
                                                             ds2.output_shapes)
    assert ds1.output_types == ds2.output_types
    assert ds1.output_classes == ds2.output_classes
    next1 = ds1.make_one_shot_iterator().get_next()
    next2 = ds2.make_one_shot_iterator().get_next()
    with self.test_session(graph=g) as sess:
      # Run through datasets and check that outputs match, or errors match.
      while True:
        try:
          op1 = sess.run(next1)
        except (errors.OutOfRangeError, ValueError) as e:
          # If op1 throws an exception, check that op2 throws same exception.
          with self.assertRaises(type(e)):
            sess.run(next2)
          break
        op2 = sess.run(next2)
        self.assertAllEqual(op1, op2)

  def setup_files(self, inputs):
    filenames = []
    for i, ip in enumerate(inputs):
      fn = os.path.join(self.get_temp_dir(), 'temp_%d.txt' % i)
      with open(fn, 'w') as f:
        f.write('\n'.join(ip))
      filenames.append(fn)
    return filenames

  def _make_test_datasets(self, inputs, **kwargs):
    # Test by comparing its output to what we could get with map->decode_csv
    filenames = self.setup_files(inputs)
    dataset_expected = core_readers.TextLineDataset(filenames)
    dataset_expected = dataset_expected.map(
        lambda l: gen_parsing_ops.decode_csv(l, **kwargs))
    dataset_actual = readers.CsvDataset(filenames, **kwargs)
    return (dataset_actual, dataset_expected)

  def _test_by_comparison(self, inputs, **kwargs):
    """Checks that CsvDataset is equiv to TextLineDataset->map(decode_csv)."""
    with ops.Graph().as_default() as g:
      dataset_actual, dataset_expected = self._make_test_datasets(
          inputs, **kwargs)
      self._assert_datasets_equal(g, dataset_actual, dataset_expected)

  def _test_dataset(self,
                    inputs,
                    expected_output=None,
                    expected_err_re=None,
                    **kwargs):
    """Checks that elements produced by CsvDataset match expected output."""
    # Convert str type because py3 tf strings are bytestrings
    filenames = self.setup_files(inputs)
    with ops.Graph().as_default() as g:
      with self.test_session(graph=g) as sess:
        dataset = readers.CsvDataset(filenames, **kwargs)
        nxt = dataset.make_one_shot_iterator().get_next()
        if expected_err_re is None:
          # Verify that output is expected, without errors
          expected_output = [[
              v.encode('utf-8') if isinstance(v, str) else v for v in op
          ] for op in expected_output]
          for value in expected_output:
            op = sess.run(nxt)
            self.assertAllEqual(op, value)
          with self.assertRaises(errors.OutOfRangeError):
            sess.run(nxt)
        else:
          # Verify that OpError is produced as expected
          with self.assertRaisesOpError(expected_err_re):
            while True:
              try:
                sess.run(nxt)
              except errors.OutOfRangeError:
                break

  def testCsvDataset_floatRequired(self):
    record_defaults = [[]] * 4
    inputs = [['1,2,3,4']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_int(self):
    record_defaults = [[0]] * 4
    inputs = [['1,2,3,4', '5,6,7,8']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_float(self):
    record_defaults = [[0.0]] * 4
    inputs = [['1.0,2.1,3.2,4.3', '5.4,6.5,7.6,8.7']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_string(self):
    record_defaults = [['']] * 4
    inputs = [['1.0,2.1,hello,4.3', '5.4,6.5,goodbye,8.7']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_withQuoted(self):
    record_defaults = [['']] * 4
    inputs = [['1.0,2.1,"hello, it is me",4.3', '5.4,6.5,goodbye,8.7']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_mixedTypes(self):
    record_defaults = [
        constant_op.constant([], dtype=dtypes.int32),
        constant_op.constant([], dtype=dtypes.float32),
        constant_op.constant([], dtype=dtypes.string),
        constant_op.constant([], dtype=dtypes.float64)
    ]
    inputs = [['1,2.1,3.2,4.3', '5,6.5,7.6,8.7']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_withUseQuoteDelimFalse(self):
    record_defaults = [['']] * 4
    inputs = [['1,2,"3,4"', '"5,6",7,8']]
    self._test_by_comparison(
        inputs, record_defaults=record_defaults, use_quote_delim=False)

  def testCsvDataset_withFieldDelim(self):
    record_defaults = [[0]] * 4
    inputs = [['1:2:3:4', '5:6:7:8']]
    self._test_by_comparison(
        inputs, record_defaults=record_defaults, field_delim=':')

  def testCsvDataset_withEmptyValues(self):
    record_defaults = [[0]] * 4
    inputs = [['1,,3,4', ',6,7,8']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_withNaValue(self):
    record_defaults = [[0]] * 4
    inputs = [['1,NA,3,4', 'NA,6,7,8']]
    self._test_by_comparison(
        inputs, record_defaults=record_defaults, na_value='NA')

  def testCsvDataset_withSelectCols(self):
    record_defaults = [[0]] * 2
    inputs = [['1,2,3,4', '5,6,7,8']]
    self._test_by_comparison(
        inputs, record_defaults=record_defaults, select_cols=[1, 2])

  def testCsvDataset_withSelectColsTooHigh(self):
    record_defaults = [[0]] * 2
    inputs = [['1,2,3,4', '5,6,7,8']]
    self._test_dataset(
        inputs,
        expected_err_re='Expect 2 fields but have 1 in record',
        record_defaults=record_defaults,
        select_cols=[3, 4])

  def testCsvDataset_withMultipleFiles(self):
    record_defaults = [[0]] * 4
    inputs = [['1,2,3,4', '5,6,7,8'], ['5,6,7,8']]
    self._test_by_comparison(inputs, record_defaults=record_defaults)

  def testCsvDataset_withNewLine(self):
    # In this case, we expect it to behave differently from
    # TextLineDataset->map(decode_csv) since that flow has bugs
    record_defaults = [['']] * 4
    inputs = [['a,b,"""c""\n0","d\ne"', 'f,g,h,i']]
    expected = [['a', 'b', '"c"\n0', 'd\ne'], ['f', 'g', 'h', 'i']]
    self._test_dataset(inputs, expected, record_defaults=record_defaults)

  def testCsvDataset_withMultipleNewLines(self):
    # In this case, we expect it to behave differently from
    # TextLineDataset->map(decode_csv) since that flow has bugs
    record_defaults = [['']] * 4
    inputs = [['a,"b\n\nx","""c""\n \n0","d\ne"', 'f,g,h,i']]
    expected = [['a', 'b\n\nx', '"c"\n \n0', 'd\ne'], ['f', 'g', 'h', 'i']]
    self._test_dataset(inputs, expected, record_defaults=record_defaults)

  def testCsvDataset_withLeadingAndTrailingSpaces(self):
    record_defaults = [[0.0]] * 4
    inputs = [['0, 1, 2, 3']]
    expected = [[0.0, 1.0, 2.0, 3.0]]
    self._test_dataset(inputs, expected, record_defaults=record_defaults)

  def testCsvDataset_errorWithMissingDefault(self):
    record_defaults = [[]] * 2
    inputs = [['0,']]
    self._test_dataset(
        inputs,
        expected_err_re='Field 1 is required but missing in record!',
        record_defaults=record_defaults)

  def testCsvDataset_errorWithFewerDefaultsThanFields(self):
    record_defaults = [[0.0]] * 2
    inputs = [['0,1,2,3']]
    self._test_dataset(
        inputs,
        expected_err_re='Expect 2 fields but have more in record',
        record_defaults=record_defaults)

  def testCsvDataset_errorWithMoreDefaultsThanFields(self):
    record_defaults = [[0.0]] * 5
    inputs = [['0,1,2,3']]
    self._test_dataset(
        inputs,
        expected_err_re='Expect 5 fields but have 4 in record',
        record_defaults=record_defaults)

  def testCsvDataset_withHeader(self):
    record_defaults = [[0]] * 2
    inputs = [['col1,col2', '1,2']]
    expected = [[1, 2]]
    self._test_dataset(
        inputs,
        expected,
        record_defaults=record_defaults,
        header=True,
    )

  def testCsvDataset_withHeaderAndNoRecords(self):
    record_defaults = [[0]] * 2
    inputs = [['col1,col2']]
    expected = []
    self._test_dataset(
        inputs,
        expected,
        record_defaults=record_defaults,
        header=True,
    )

  def testCsvDataset_errorWithHeaderEmptyFile(self):
    record_defaults = [[0]] * 2
    inputs = [[]]
    self._test_dataset(
        inputs,
        expected_err_re="Can't read header of empty file",
        record_defaults=record_defaults,
        header=True,
    )

  def testCsvDataset_withEmptyFile(self):
    record_defaults = [['']] * 2
    inputs = [['']]  # Empty file
    self._test_dataset(
        inputs, expected_output=[], record_defaults=record_defaults)

  def testCsvDataset_errorWithEmptyRecord(self):
    record_defaults = [['']] * 2
    inputs = [['', '1,2']]  # First record is empty
    self._test_dataset(
        inputs,
        expected_err_re='Expect 2 fields but have 0 in record',
        record_defaults=record_defaults)

  def testCsvDataset_withChainedOps(self):
    # Testing that one dataset can create multiple iterators fine.
    # `repeat` creates multiple iterators from the same C++ Dataset.
    record_defaults = [[0]] * 4
    inputs = [['1,,3,4', '5,6,,8']]
    ds_actual, ds_expected = self._make_test_datasets(
        inputs, record_defaults=record_defaults)
    with ops.Graph().as_default() as g:
      self._assert_datasets_equal(g,
                                  ds_actual.repeat(5).prefetch(1),
                                  ds_expected.repeat(5).prefetch(1))

  def testCsvDataset_withTypeDefaults(self):
    # Testing using dtypes as record_defaults for required fields
    record_defaults = [dtypes.float32, dtypes.float32]
    inputs = [['1.0,2.0', '3.0,4.0']]
    self._test_dataset(
        inputs,
        [[1.0, 2.0], [3.0, 4.0]],
        record_defaults=record_defaults,
    )


class CsvDatasetBenchmark(test.Benchmark):
  """Benchmarks for the various ways of creating a dataset from CSV files.
  """

  def _setUp(self):
    # Since this isn't test.TestCase, have to manually create a test dir
    gfile.MakeDirs(googletest.GetTempDir())
    self._temp_dir = tempfile.mkdtemp(dir=googletest.GetTempDir())

    self._num_cols = [4, 64, 256]
    self._batch_size = 500
    self._filenames = []
    for n in self._num_cols:
      fn = os.path.join(self._temp_dir, 'file%d.csv' % n)
      with open(fn, 'w') as f:
        # Just write 10 rows and use `repeat`...
        row = ','.join(['1.23456E12' for _ in range(n)])
        f.write('\n'.join([row for _ in range(10)]))
      self._filenames.append(fn)

  def _tearDown(self):
    gfile.DeleteRecursively(self._temp_dir)

  def _runBenchmark(self, dataset, num_cols, prefix):
    next_element = dataset.make_one_shot_iterator().get_next()
    with session.Session() as sess:
      for _ in range(5):
        sess.run(next_element)
      deltas = []
      for _ in range(10):
        start = time.time()
        sess.run(next_element)
        end = time.time()
        deltas.append(end - start)
    median_wall_time = np.median(deltas) / 100
    print('%s num_cols: %d Median wall time: %f' % (prefix, num_cols,
                                                    median_wall_time))
    self.report_benchmark(
        iters=self._batch_size,
        wall_time=median_wall_time,
        name='%s_with_cols_%d' % (prefix, num_cols))

  def benchmarkBatchThenMap(self):
    self._setUp()
    for i in range(len(self._filenames)):
      num_cols = self._num_cols[i]
      kwargs = {'record_defaults': [[0.0]] * num_cols}
      dataset = core_readers.TextLineDataset(self._filenames[i]).repeat()
      dataset = dataset.map(lambda l: gen_parsing_ops.decode_csv(l, **kwargs))  # pylint: disable=cell-var-from-loop
      dataset = dataset.batch(self._batch_size)
      self._runBenchmark(dataset, num_cols, 'csv_map_then_batch')
    self._tearDown()

  def benchmarkCsvDataset(self):
    self._setUp()
    for i in range(len(self._filenames)):
      num_cols = self._num_cols[i]
      kwargs = {'record_defaults': [[0.0]] * num_cols}
      dataset = core_readers.TextLineDataset(self._filenames[i]).repeat()
      dataset = readers.CsvDataset(self._filenames[i], **kwargs).repeat()  # pylint: disable=cell-var-from-loop
      dataset = dataset.batch(self._batch_size)
      self._runBenchmark(dataset, num_cols, 'csv_fused_dataset')
    self._tearDown()


if __name__ == '__main__':
  test.main()
