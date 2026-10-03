# -*- coding: utf-8 -*-
"""CathayPDG 一键发版：打包 exe → 校验值 → 发行说明骨架。用法：py -3 fab.py [--skip-build]"""
import hashlib
import io
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.dirname(HERE)                 # 程序组件\ —— config\ 和 Pdg2Pic\ 在这一层
NAME = 'CathayPDG'
ENTRY = 'gui.py'
VERSION_SRC = ['pdg_core.py', 'gui.py']
# pdg_deps 在 main() 里动态 import（启动前的依赖体检），静态扫描不到，必须显式声明
EXTRA = ['--collect-all', 'tkinterdnd2', '--collect-all', 'pyzipper',
         '--hidden-import', 'Crypto', '--hidden-import', 'pdg_deps']
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
    # 密码本 config\ 不在 开发\ 下，在上一级 程序组件\ —— 写 'config;config' 会打包失败
    cfg = os.path.join(UP, 'config')
    if not os.path.isdir(cfg):
        print('× 找不到密码本目录：%s' % cfg)
        return 1
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
           '--windowed', '--name', NAME, '--icon', 'app.ico',
           '--add-data', '%s;config' % cfg, '--add-data', 'app.ico;.',
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
    # 顺手出便携包：Release 上除了裸 exe，还得给一个解压即用的配齐版本
    # （失败不致命，别因为压个 zip 把整个发版判死刑）
    try:
        portable(v)
    except Exception as e:
        print('! 便携包没生成出来：%s' % e)
    return 0


def portable(v=None):
    """打包「零依赖便携包」：exe + 两个引擎 + 密码本，解压即用。

    单独一个 exe 是能跑，但 7-Zip 和 Pdg2Pic 是外面的文件夹 —— 只拎走 exe
    的话 .7z/.rar 和强加密页就废了。所以 Release 里除了裸 exe，再给一个配齐的 zip。
    不含便携 runtime（148MB）和源码，那两样留给想改代码的人。
    """
    import zipfile
    v = v or version()
    src_exe = os.path.join(RELDIR, NAME + '.exe')
    if not os.path.isfile(src_exe):
        print('× 先跑一次打包，没找到 %s' % src_exe)
        return 1
    OUT = os.path.join(RELDIR, '%s-%s-portable.zip' % (NAME, v))
    files = [(src_exe, '%s %s.exe' % (NAME, v))]           # 放进包里就叫带版本号的名字
    for sub in (os.path.join('Pdg2Pic', 'Pdg2Pic.exe'), os.path.join('Pdg2Pic', 'Pdg2Pic.ini'),
                os.path.join('7-Zip', '7z.exe'), os.path.join('7-Zip', '7z.dll'),
                os.path.join('7-Zip', 'LICENSE-7-Zip.txt'),
                os.path.join('config', 'passwords.txt')):
        p = os.path.join(UP, sub)
        if os.path.isfile(p):
            files.append((p, os.path.join('程序组件', sub)))
        else:
            print('  ! 缺 %s（便携包里会没有它）' % sub)
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, arc in files:
            z.write(src, arc)
    size = os.path.getsize(OUT)
    open(os.path.join(RELDIR, '校验值便携包.txt'), 'w', encoding='utf-8').write(
        '%s\n大小: %d 字节 (%.2f MB)\nSHA256: %s\n' %
        (os.path.basename(OUT), size, size / 1e6, sha256(OUT)))
    print('✓ 便携包 %s（%.2f MB，%d 个文件）' % (os.path.basename(OUT), size / 1e6, len(files)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
