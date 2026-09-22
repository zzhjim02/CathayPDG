# -*- coding: utf-8 -*-
"""CathayPDG 一键发版：打包 exe → 校验值 → 发行说明骨架。用法：py -3 fab.py [--skip-build]"""
import hashlib
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'CathayPDG'
ENTRY = 'gui.py'
VERSION_SRC = ['pdg_core.py', 'gui.py']
EXTRA = ['--collect-all', 'tkinterdnd2', '--collect-all', 'pyzipper', '--hidden-import', 'Crypto']
RELDIR = os.path.join(HERE, 'dist', 'Release')


def version():
    for f in [ENTRY] + VERSION_SRC:
        p = os.path.join(HERE, f)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            if 'APP_VERSION' in line or 'APP_TITLE' in line or 'root.title' in line:
                m = re.search(r"v[0-9]+[.][0-9]+(?:[.][0-9]+)?", line)
                if m:
                    return m.group(0)
    return 'v0.0.0'


def build():
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
           '--windowed', '--name', NAME, '--icon', 'app.ico',
           '--add-data', 'config;config', '--add-data', 'app.ico;.',
           '--distpath', os.path.join(HERE, 'dist'), '--workpath', os.path.join(HERE, 'build'),
           '--specpath', HERE] + EXTRA + [ENTRY]
    print('打包：', ' '.join(cmd))
    r = subprocess.run(cmd, cwd=HERE)
    return r.returncode


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    args = sys.argv[1:]
    v = version()
    if '--skip-build' not in args:
        rc = build()
        if rc != 0:
            print('× 打包失败 rc=%d' % rc)
            return 1
    exe = None
    for cand in (os.path.join(HERE, 'dist', NAME + '.exe'),
                 os.path.join(RELDIR, NAME + '.exe')):
        if os.path.exists(cand):
            exe = cand
            break
    if not exe:
        print('× 没找到成品 exe（先去掉 --skip-build 跑一次）')
        return 1
    os.makedirs(RELDIR, exist_ok=True)
    dst = os.path.join(RELDIR, NAME + '.exe')
    if os.path.abspath(exe) != os.path.abspath(dst):
        import shutil
        shutil.copy2(exe, dst)
    size = os.path.getsize(dst)
    h = sha256(dst)
    open(os.path.join(RELDIR, '校验值.txt'), 'w', encoding='utf-8').write(
        '%s\n大小: %d 字节 (%.2f MB)\nSHA256: %s\n' % (NAME + '.exe', size, size / 1e6, h))
    note = os.path.join(RELDIR, '发行说明_%s.md' % v)
    if not (os.path.exists(note) and os.path.getsize(note) > 200):
        open(note, 'w', encoding='utf-8').write(
            '# %s %s\n\n- 包内：%s.exe（单文件，免装 Python）+ config/（密码本）\n'
            '  - 便携版：开发\\ 里是源码 + runtime\\（便携 Python）\n'
            '- 下载：GitHub Releases ／ 百度网盘（密码 2026）\n\n'
            '## 校验\n\n- %s：%d 字节（%.2f MB）\n- SHA256：%s\n' %
            (NAME, v, NAME, NAME + '.exe', size, size / 1e6, h))
    print('✓ %s ｜ %s（%.2f MB）｜ SHA256 %s' % (NAME, v, size / 1e6, h[:16] + '...'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
