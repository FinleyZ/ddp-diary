"""Role-specific share synchronization: host ingest, vm export.

These are the ONLY two files with role-specific I/O in the whole core — see
spec.md §6, §11. Everything else in `sync/` is shared by construction: there is
nothing else in this package.
"""
