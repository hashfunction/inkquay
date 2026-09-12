# Scriblark Windows path comparison repair

Actual Windows run 34694024697 used mingw-w64-x86_64-python 3.14.7-1. Native product build and 135 product tests passed; the Store evidence fixture then failed before any installed workflow with `Package module path/identity differs` (two errors and one downstream failure).

The exact runtime fork sets ntpath.sep to `/` when sys._use_alt_sep is true. PureWindowsPath renders with that separator. The evidence parser incorrectly assumed its string output always used backslashes, then compared it against a literal backslash WindowsApps suffix. Primary source: https://github.com/msys2-contrib/cpython-mingw/blob/mingw-v3.14.7/Lib/ntpath.py and https://github.com/msys2-contrib/cpython-mingw/blob/mingw-v3.14.7/Lib/pathlib/__init__.py . The actual run records its Python path with forward slashes as well.

A platform-rendering fixture retains real Windows parsing and changes only string rendering. Before the repair it reproduces the exact complete-receipt error from the runner. Its explicit canonical-path assertion also fails. The production comparison now normalizes to backslashes through as_posix, and both sides of the SDK signer comparison use that same helper. Original recorded paths and files are never rewritten; all absolute-path, traversal, package identity, runtime hash and ownership requirements remain.

All 12 Store workflow evidence tests pass locally, including the complete MinGW-rendered receipt, foreign WindowsAppsBackup/module roots and traversal refusals. A fresh full Windows run is required; this is not proof of installed workflow success.
