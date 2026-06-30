import subprocess
import os
import sys
from pathlib import Path
from typing import Optional, List
from config import Config


class WebDAVDownloader:
    def __init__(self, config: Config):
        self.config = config

    def _build_lftp_command(self, remote_path: str, local_path: str) -> List[str]:
        host = self.config.webdav.host
        port = self.config.webdav.port
        username = self.config.webdav.username
        password = self.config.webdav.password

        cmd = [
            "lftp",
            "-c",
            f"set net:timeout {self.config.download.timeout}; "
            f"set http:timeout {self.config.download.timeout}; "
            f"set ftp:timeout {self.config.download.timeout}; "
            f"connect webdav://{username}:{password}@{host}:{port}{self.config.webdav.remote_dir}; "
            f"pget -c -n 4 \"{remote_path}\" -o \"{local_path}\""
        ]
        return cmd

    def download(self, remote_file: str, local_file: Optional[str] = None, max_tries: Optional[int] = None) -> bool:
        if max_tries is None:
            max_tries = self.config.download.max_tries

        remote_path = f"{self.config.webdav.remote_dir}/{remote_file}"
        if local_file is None:
            local_file = os.path.join(self.config.webdav.local_dir, remote_file)

        os.makedirs(os.path.dirname(local_file) if os.path.dirname(local_file) else ".", exist_ok=True)

        for attempt in range(1, max_tries + 1):
            try:
                cmd = self._build_lftp_command(remote_path, local_file)
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0 and os.path.exists(local_file):
                    print(f"Successfully downloaded: {remote_file}")
                    return True
                else:
                    print(f"Attempt {attempt}/{max_tries} failed: {result.stderr}", file=sys.stderr)
                    if attempt < max_tries:
                        print(f"Retrying...")
            except Exception as e:
                print(f"Attempt {attempt}/{max_tries} failed: {e}", file=sys.stderr)
                if attempt < max_tries:
                    print(f"Retrying...")

        print(f"Failed to download {remote_file} after {max_tries} attempts", file=sys.stderr)
        return False

    def list_remote_files(self, pattern: str = "*") -> List[str]:
        host = self.config.webdav.host
        port = self.config.webdav.port
        username = self.config.webdav.username
        password = self.config.webdav.password

        cmd = [
            "lftp",
            "-c",
            f"set net:timeout {self.config.download.timeout}; "
            f"connect webdav://{username}:{password}@{host}:{port}{self.config.webdav.remote_dir}; "
            f"cls -1 {pattern}"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                return files
            else:
                print(f"Failed to list remote files: {result.stderr}", file=sys.stderr)
                return []
        except Exception as e:
            print(f"Error listing remote files: {e}", file=sys.stderr)
            return []