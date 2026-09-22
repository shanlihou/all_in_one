#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(r'F:\shdownload\music')
FFMPEG = shutil.which('ffmpeg') or r'ffmpeg'


def convert_one(src: Path, dst: Path) -> bool:
    cmd = [
        FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
        '-i', str(src),
        '-vn',
        '-codec:a', 'libmp3lame',
        '-q:a', '2',
        str(dst),
    ]
    try:
        result = subprocess.run(cmd, check=False)
    except FileNotFoundError:
        print('[错误] 未找到 ffmpeg，请确认已安装并加入 PATH', file=sys.stderr)
        return False
    if result.returncode != 0 or not dst.exists():
        print(f'[失败] {src.name} -> {dst.name} (code={result.returncode})', file=sys.stderr)
        return False
    return True


def main():
    if not SOURCE_DIR.exists() or not SOURCE_DIR.is_dir():
        print(f'[错误] 目录不存在: {SOURCE_DIR}', file=sys.stderr)
        sys.exit(1)

    files = sorted(SOURCE_DIR.rglob('*.m4s'))
    if not files:
        print(f'[提示] {SOURCE_DIR} 下未找到 .m4s 文件')
        return

    print(f'源目录: {SOURCE_DIR}')
    print(f'ffmpeg: {FFMPEG}')
    print(f'待转换: {len(files)} 个文件\n')

    ok = fail = skip = 0
    for i, src in enumerate(files, 1):
        dst = src.with_suffix('.mp3')
        if dst.exists():
            print(f'[{i}/{len(files)}] 跳过 (已存在) {dst.name}')
            skip += 1
            continue
        print(f'[{i}/{len(files)}] 转换 {src.name} -> {dst.name} ...', end='', flush=True)
        if convert_one(src, dst):
            print(' OK')
            ok += 1
        else:
            fail += 1

    print(f'\n完成: 成功 {ok}，失败 {fail}，跳过 {skip}')


if __name__ == '__main__':
    main()