# -*- coding: utf-8 -*-
"""验证发给用户的便携包：解压到干净目录后，能不能真的「什么都不装就能跑」。

做法是把便携包解压到一个全新目录，然后把 app_dir 指过去 —— 这跟 exe 在那个
目录下运行时看到的是同一套东西，不必真的启动 GUI（那样会弹窗）。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import glob
# 按脚本自己的位置找源码和便携包（别写死路径，也别写死版本号）
SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
_zips = sorted(glob.glob(os.path.join(SRC, 'dist', 'Release', '*-portable.zip')))
ZIP = _zips[-1] if _zips else ''
import pdg_batch as B
import pdg_deps as D

fails = []
KEYS = ('PATH', 'ProgramFiles', 'ProgramFiles(x86)')


def chk(label, cond, extra=''):
    print('%-40s %s %s' % (label, 'OK' if cond else 'FAIL', extra))
    if not cond:
        fails.append(label)


print('--- 1) 便携包清单 ---')
if not os.path.isfile(ZIP):
    print('没有便携包，先跑 fab.py 生成')
    sys.exit(1)
root = os.path.join(tempfile.mkdtemp(prefix='portable_'), 'CathayPDG')
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    z.extractall(root)
print('   包内 %d 项：' % len(names))
for n in sorted(names):
    print('     ' + n)
want = {'程序组件/Pdg2Pic/Pdg2Pic.exe', '程序组件/7-Zip/7z.exe', '程序组件/7-Zip/7z.dll',
        '程序组件/config/passwords.txt', '程序组件/7-Zip/LICENSE-7-Zip.txt'}
chk('该带的都在', want <= set(names), '缺：' + str(want - set(names)) if want - set(names) else '五项齐全')
chk('没有把整份源码打进去', not any(n.startswith('程序组件/开发/') for n in names))
chk('exe 在包根', any(n.endswith('.exe') and '/' not in n for n in names))

print('\n--- 2) 假设这台机器很干净（PATH 里没 7-Zip，程序目录里也没有）---')
empty = tempfile.mkdtemp(prefix='empty_')
saved = {k: os.environ.get(k) for k in KEYS}
for k in KEYS:
    os.environ[k] = empty
_real_ad_B, _real_ad_D = B.app_dir, D._app_dir
for mod in (B, D):
    B._7Z_CACHE['done'] = False
try:
    B.app_dir = lambda: root
    D._app_dir = lambda: root

    s7 = B.find_7z()
    chk('找到 7z 引擎', bool(s7), os.path.relpath(s7, root) if s7 else '')
    chk('用的是包里那份（不是系统的）', bool(s7) and s7.startswith(root),
        '是' if s7 and s7.startswith(root) else '×')
    pdp = D._find_pdg2pic()
    chk('找到 Pdg2Pic 引擎', bool(pdp), os.path.relpath(pdp, root) if pdp else '')
    chk('用的是包里那份', bool(pdp) and pdp.startswith(root),
        '是' if pdp and pdp.startswith(root) else '×')
    rows = D.check()
    bad = [r for r in rows if not r['ok'] and r.get('required', True)]
    chk('体检表没有必需项缺失', not bad, '、'.join(r['name'] for r in bad) or '全绿')
    chk('密码本能读到', len(B.passwords()) >= 300, '%d 条' % len(B.passwords()))

    print('\n--- 3) 真跑一次：用包里的引擎解一个带中文名的 .7z ---')
    tmp = tempfile.mkdtemp(prefix='run_')
    try:
        name = '简体测试书  第01册'
        book = os.path.join(tmp, 'src', name)
        os.makedirs(book)
        for fn in ('000001.pdg', 'cov001.pdg'):
            open(os.path.join(book, fn), 'wb').write(b'PDGDATA' * 8)
        arc = os.path.join(tmp, '测试包.7z')
        subprocess.run([s7, 'a', arc, book, '-bso0', '-bsp0'], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        dest = os.path.join(tmp, 'out')
        ok, pw, note = B.extract_archive(arc, dest, [], log=lambda *a: None)
        chk('.7z 解压成功', ok, note)
        got = sorted(os.listdir(dest)) if ok else []
        chk('中文书名正确', got == [name], str(got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
finally:
    B.app_dir, D._app_dir = _real_ad_B, _real_ad_D
    B._7Z_CACHE['done'] = False
    for k in KEYS:
        os.environ[k] = saved[k]
    shutil.rmtree(empty, ignore_errors=True)
    shutil.rmtree(root, ignore_errors=True)

print()
print('=' * 60)
print('  %s' % ('全部通过 —— 干净机器上解压即用' if not fails else '失败：' + '；'.join(fails)))
print('=' * 60)
sys.exit(0 if not fails else 1)
