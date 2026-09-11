#!/usr/bin/env python3
"""Copy exact original source notices into the existing Windows package stage.
Copyright 2026 Trieflow LLC. MIT.
"""
import argparse
from pathlib import Path
from msix_qualification import copy_notice_supplement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("stage", type=Path)
    args = parser.parse_args()
    measured = copy_notice_supplement(args.source_root, args.stage)
    print(f"Copied and verified {len(measured)} original notice/index files")


if __name__ == "__main__":
    main()
