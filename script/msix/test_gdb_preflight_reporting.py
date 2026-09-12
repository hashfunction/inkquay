"""Real live-fixture entry boundary retains setup errors without authorizing attach."""
# Copyright 2026 Trieflow LLC. MIT.
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdb_observer as observer
import test_gdb_observer_windows as live


class PreflightReportingTests(unittest.TestCase):
    def test_setup_failure_produces_bound_failure_receipt_without_launching_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'preflight.json'
            with patch.object(live.sys,'platform','win32'),patch.dict(os.environ,{'CI':'true','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}),\
                    patch.object(observer,'verified_debugger',side_effect=ValueError('Diagnostic runtime binding is absent')),patch.object(live,'run_case') as run:
                self.assertFalse(live.main(path));run.assert_not_called()
            value=json.loads(path.read_text())
            self.assertIs(value['passed'],False);self.assertEqual([],value['cases']);self.assertEqual([],value['results'])
            self.assertEqual('Diagnostic runtime binding is absent',value['error'])
            self.assertEqual('a'*40,value['source_commit']);self.assertEqual('123',value['workflow_run_id'])
            with self.assertRaisesRegex(ValueError,'fixture differs'):observer.validate_preflight(value,{},'a'*40,'123','1')


if __name__=='__main__':unittest.main()
