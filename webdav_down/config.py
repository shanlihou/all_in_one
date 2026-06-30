import json
import os
from dataclasses import dataclass


@dataclass
class WebDAVConfig:
    host: str
    port: int
    username: str
    password: str
    remote_dir: str
    local_dir: str


@dataclass
class DownloadConfig:
    max_tries: int
    timeout: int
    chunk_size: int


@dataclass
class Config:
    webdav: WebDAVConfig
    download: DownloadConfig


def load_config(config_path: str = "config.json") -> Config:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        data = json.load(f)

    webdav = WebDAVConfig(
        host=data["webdav"]["host"],
        port=data["webdav"]["port"],
        username=data["webdav"]["username"],
        password=data["webdav"]["password"],
        remote_dir=data["webdav"]["remote_dir"],
        local_dir=data["webdav"]["local_dir"],
    )

    download = DownloadConfig(
        max_tries=data["download"].get("max_tries", 5),
        timeout=data["download"].get("timeout", 300),
        chunk_size=data["download"].get("chunk_size", 10485760),
    )

    return Config(webdav=webdav, download=download)