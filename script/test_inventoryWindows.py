import tempfile
import unittest
from pathlib import Path
from unittest import mock
import inventoryWindows as inventory


class NativeInventoryTests(unittest.TestCase):
    def test_ownership_index_preserves_spaces_unicode_and_ambiguity(self):
        result = inventory.package_file_owners('alpha /mingw64/share/Résumé note.txt\nbeta /mingw64/share/shared.txt\nalpha /mingw64/share/shared.txt\n')
        self.assertEqual(result['/mingw64/share/Résumé note.txt'], {'alpha'})
        self.assertEqual(result['/mingw64/share/shared.txt'], {'alpha', 'beta'})

    def test_malformed_package_listing_is_rejected(self):
        for listing in ('alpha\n', 'alpha relative/path\n'):
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                inventory.package_file_owners(listing)

    def test_inventory_verifies_bytes_without_per_file_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, prefix = root / 'stage', root / 'prefix'
            for folder in (stage, prefix):
                (folder / 'share').mkdir(parents=True)
                (folder / 'share/Résumé note.txt').write_bytes(b'exact package bytes')
                (folder / 'share/changed.txt').write_bytes(b'original package bytes')
                (folder / 'share/shared.txt').write_bytes(b'shared bytes')
            (stage / 'share/changed.txt').write_bytes(b'changed application copy')
            (stage / 'application.txt').write_bytes(b'our app resource')
            owners = inventory.package_file_owners('alpha /mingw64/share/Résumé note.txt\nalpha /mingw64/share/changed.txt\nalpha /mingw64/share/shared.txt\nbeta /mingw64/share/shared.txt\n')
            with mock.patch.object(inventory.subprocess, 'run', side_effect=AssertionError('per-file process')), mock.patch.object(inventory.subprocess, 'check_output', side_effect=AssertionError('per-file process')):
                files = inventory.inventory_files(stage, prefix, '/mingw64', {'alpha': '1.2-3', 'beta': '4.5-6'}, owners)
            rows = {row['path']: row for row in files}
            self.assertEqual(rows['share/Résumé note.txt']['package'], 'alpha')
            self.assertEqual(rows['share/Résumé note.txt']['packageVersion'], '1.2-3')
            self.assertNotIn('package', rows['share/changed.txt'])
            self.assertNotIn('package', rows['application.txt'])
            self.assertNotIn('package', rows['share/shared.txt'])
            self.assertEqual(rows['share/shared.txt']['ambiguousPackageOwners'], ['alpha', 'beta'])
            self.assertTrue(all(len(row['sha256']) == 64 for row in rows.values()))


if __name__ == '__main__':
    unittest.main()
