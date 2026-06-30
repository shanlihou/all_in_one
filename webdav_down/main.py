#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path
from config import load_config
from downloader import WebDAVDownloader


def main():
    parser = argparse.ArgumentParser(description="Download files from WebDAV using lftp")
    parser.add_argument("file", nargs="?", help="Remote file to download")
    parser.add_argument("-c", "--config", default="config.json", help="Config file path (default: config.json)")
    parser.add_argument("-o", "--output", help="Local output path")
    parser.add_argument("-l", "--list", metavar="PATTERN", help="List remote files matching pattern")
    parser.add_argument("-t", "--tries", type=int, help="Max number of retry attempts")

    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    downloader = WebDAVDownloader(config)

    if args.list:
        files = downloader.list_remote_files(args.list)
        for f in files:
            print(f)
        return

    if not args.file:
        parser.print_help()
        sys.exit(1)

    success = downloader.download(args.file, args.output, args.tries)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()