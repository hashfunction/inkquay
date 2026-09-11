import tempfile
import unittest
from pathlib import Path
from unittest import mock
import inventoryWindows as inventory


class NativeInventoryTests(unittest.TestCase):
    def test_native_prefix_is_converted_once_instead_of_using_converted_environment(self):
        with mock.patch.dict(inventory.os.environ, {'MSYSTEM_PREFIX': 'D:/a/_temp/msys64/mingw64'}), mock.patch.object(inventory.subprocess, 'check_output', return_value='/mingw64\n') as convert:
            self.assertEqual(inventory.pacman_prefix(Path('D:/a/_temp/msys64/mingw64')), '/mingw64')
        convert.assert_called_once_with(['cygpath', '-u', str(Path('D:/a/_temp/msys64/mingw64'))], text=True, encoding='utf-8')

    def test_non_posix_conversion_and_unmatched_owner_prefix_fail(self):
        for output in ('D:/a/_temp/msys64/mingw64\n', '/mingw64\n/unexpected', ''):
            with self.subTest(output=output), mock.patch.object(inventory.subprocess, 'check_output', return_value=output), self.assertRaises(ValueError):
                inventory.pacman_prefix(Path('native-prefix'))
        with self.assertRaisesRegex(ValueError, 'package ownership prefix'):
            inventory.validate_provenance([], '/wrong', {'/mingw64/bin/a.dll': {'alpha'}})

    def test_required_font_config_and_runtime_owner_must_match(self):
        owners = {'/mingw64/bin/libfontconfig-1.dll': {'alpha'}}
        files = [{'path': name, 'sourcePath': name, 'package': 'alpha'} for name in inventory.REQUIRED_PACKAGE_FILES]
        result = inventory.validate_provenance(files, '/mingw64', owners)
        self.assertEqual(result['packageOwnedFiles'], len(files))
        for missing in inventory.REQUIRED_PACKAGE_FILES:
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                inventory.validate_provenance([row for row in files if row['path'] != missing], '/mingw64', owners)
        for unowned in ('bin/another.dll', 'bin/helper.exe'):
            with self.subTest(unowned=unowned), self.assertRaisesRegex(ValueError, 'package owner'):
                inventory.validate_provenance(files + [{'path': unowned, 'sourcePath': unowned}], '/mingw64', owners)

    def test_changed_or_missing_native_input_is_rejected_after_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, prefix = root / 'stage', root / 'prefix'
            for folder in (stage, prefix):
                for name in inventory.REQUIRED_PACKAGE_FILES:
                    path = folder / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'package bytes')
            owners = {'/mingw64/' + name: {'alpha'} for name in inventory.REQUIRED_PACKAGE_FILES}
            extra = 'bin/libgio-2.0-0.dll'
            owners['/mingw64/' + extra] = {'alpha'}
            (stage / extra).write_bytes(b'unverified bytes')
            for has_source in (False, True):
                if has_source:
                    (prefix / extra).write_bytes(b'original bytes')
                with self.subTest(has_source=has_source), self.assertRaisesRegex(ValueError, 'package owner'):
                    files = inventory.inventory_files(stage, prefix, '/mingw64', {'alpha': '1'}, owners)
                    inventory.validate_provenance(files, '/mingw64', owners)

    def test_only_exact_built_application_is_exempt_from_package_ownership(self):
        owners = {'/mingw64/bin/libfontconfig-1.dll': {'alpha'}}
        files = [{'path': name, 'sourcePath': name, 'package': 'alpha'} for name in inventory.REQUIRED_PACKAGE_FILES]
        application = {'path': 'bin/inkquay.exe', 'sha256': 'a' * 64}
        with self.assertRaises(ValueError):
            inventory.validate_provenance(files, '/mingw64', owners, 'a' * 64)
        with self.assertRaises(ValueError):
            inventory.validate_provenance(files + [application], '/mingw64', owners)
        inventory.validate_provenance(files + [application], '/mingw64', owners, 'a' * 64)
        with self.assertRaises(ValueError):
            inventory.validate_provenance(files + [application], '/mingw64', owners, 'b' * 64)
        with self.assertRaises(ValueError):
            inventory.validate_provenance(files + [{'path': 'bin/other.exe', 'sha256': 'a' * 64}], '/mingw64', owners, 'a' * 64)

    def test_ownership_index_preserves_spaces_unicode_and_ambiguity(self):
        result = inventory.package_file_owners('alpha /mingw64/share/Résumé note.txt\nbeta /mingw64/share/shared.txt\nalpha /mingw64/share/shared.txt\n')
        self.assertEqual(result['/mingw64/share/Résumé note.txt'], {'alpha'})
        self.assertEqual(result['/mingw64/share/shared.txt'], {'alpha', 'beta'})

    def test_wrapper_requires_its_own_exact_build_bytes_and_staged_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, prefix = root / 'stage', root / 'prefix'
            for folder in (stage, prefix):
                for name in inventory.REQUIRED_PACKAGE_FILES:
                    path = folder / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'package bytes')
            owners = {'/mingw64/' + name: {'alpha'} for name in inventory.REQUIRED_PACKAGE_FILES}
            app, wrapper = stage / 'bin/inkquay.exe', stage / 'bin/inkquay-wrapper.exe'
            app.write_bytes(b'actual main build')
            wrapper.write_bytes(b'actual wrapper build')
            app_hash, wrapper_hash = inventory.digest(app), inventory.digest(wrapper)
            def verify():
                files = inventory.inventory_files(stage, prefix, '/mingw64', {'alpha': '1'}, owners)
                return inventory.validate_provenance(files, '/mingw64', owners, app_hash, wrapper_hash)
            self.assertEqual(verify()['stagedFiles'], len(inventory.REQUIRED_PACKAGE_FILES) + 2)
            for changed in (app, wrapper):
                original = changed.read_bytes()
                changed.write_bytes(b'changed executable')
                with self.subTest(changed=changed.name), self.assertRaisesRegex(ValueError, 'exact application build'):
                    verify()
                changed.write_bytes(original)
            wrapper.rename(stage / 'bin/another-wrapper.exe')
            with self.assertRaisesRegex(ValueError, 'missing'):
                verify()
            wrapper.write_bytes(b'actual wrapper build')
            with self.assertRaisesRegex(ValueError, 'package owner'):
                verify()

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
