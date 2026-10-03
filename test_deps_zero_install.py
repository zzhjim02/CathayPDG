# -*- coding: utf-8 -*-
"""验证：用户机器上「什么都没装」时，CathayPDG 还能不能干活。

模拟手段：把 PATH 和 ProgramFiles 都指到空目录，让系统里那套 7-Zip 彻底看不见。
"""
import os
import subprocess
import sys
import tempfile
import shutil

# 按脚本自己的位置找源码（不要写死路径，换台机器就能跑）
SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
import pdg_batch as B
import pdg_deps as D

fails = []


def _restore(saved_map, keys, mod=None):
    for k in keys:
        v = saved_map.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    if mod is not None:
        mod._7Z_CACHE['done'] = False


def chk(label, cond, extra=''):
    print('%-42s %s %s' % (label, 'OK' if cond else 'FAIL', extra))
    if not cond:
        fails.append(label)


print('--- 1) 模拟「空白机器」：PATH 和 ProgramFiles 都没有 7-Zip ---')
empty = tempfile.mkdtemp(prefix='empty_')
KEYS = ('PATH', 'ProgramFiles', 'ProgramFiles(x86)')
saved = {k: os.environ.get(k) for k in KEYS}
os.environ['PATH'] = empty
os.environ['ProgramFiles'] = empty
os.environ['ProgramFiles(x86)'] = empty
try:
    B._7Z_CACHE['done'] = False          # 清缓存逼它重新探测
    s7 = B.find_7z()
    chk('还能找到解压引擎', bool(s7), s7 or '')
    chk('找到的是随包那份', bool(s7) and '程序组件' in s7.replace('\\', '/'),
        '' if not s7 else ('是' if '程序组件' in s7 else '× 只有系统装的（不满足零依赖）'))
    chk('依赖体检通过', not D.missing_required(), '、'.join(D.missing_required()) or '无缺失')
finally:
    _restore(saved, KEYS, B)
    shutil.rmtree(empty, ignore_errors=True)

print('\n--- 2) 真的用随包引擎解一个 .7z（中文名）---')
tmp = tempfile.mkdtemp(prefix='7z_')
try:
    name = '简体测试书  第01册'
    book = os.path.join(tmp, 'src', name)
    os.makedirs(book)
    for fn in ('000001.pdg', 'cov001.pdg'):
        open(os.path.join(book, fn), 'wb').write(b'PDGDATA' * 8)

    sevenz = B.find_7z()
    arc = os.path.join(tmp, '测试包.7z')
    subprocess.run([sevenz, 'a', arc, book, '-bso0', '-bsp0'], check=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    chk('造出 .7z 测试包', os.path.isfile(arc))

    dest = os.path.join(tmp, 'out')
    ok, pw, note = B.extract_archive(arc, dest, [], log=lambda *a: None)
    chk('.7z 解压成功', ok, note)
    got = sorted(os.listdir(dest)) if ok and os.path.isdir(dest) else []
    chk('中文目录名正确', got == [name], str(got))
    inner = sorted(os.listdir(os.path.join(dest, name))) if len(got) == 1 else []
    chk('里面的文件在', inner == ['000001.pdg', 'cov001.pdg'], str(inner))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('\n--- 3) 引擎彻底不在时，报错要说人话 ---')
tmp2 = tempfile.mkdtemp(prefix='no7z_')
_real_app_dir = B.app_dir
_B_ad = D._app_dir
saved2 = {k: os.environ.get(k) for k in KEYS}
try:
    B.app_dir = lambda: tmp2          # 指向一个光秃秃的目录
    D._app_dir = lambda: tmp2
    B._7Z_CACHE['done'] = False
    os.environ['PATH'] = tmp2
    os.environ['ProgramFiles'] = tmp2
    os.environ['ProgramFiles(x86)'] = tmp2
    chk('find_7z 返回 None', B.find_7z() is None, str(B.find_7z()))
    chk('提示可读', '7-Zip' in B.sevenz_missing_hint(), B.sevenz_missing_hint()[:40] + '…')
    rows = D.check()
    row = [r for r in rows if r['name'] == '7z 解压引擎'][0]
    chk('体检表标出来', not row['ok'] and bool(row['fix']), row['fix'][:40] + '…')
finally:
    B.app_dir = _real_app_dir
    D._app_dir = _B_ad
    _restore(saved2, KEYS, B)
    shutil.rmtree(tmp2, ignore_errors=True)

print('\n--- 4) zip 路线不依赖任何外部引擎 ---')
tmp3 = tempfile.mkdtemp(prefix='ziponly_')
try:
    import zipfile
    # zipfile 写盘时非 ASCII 一律走 UTF-8 并置标志位，造不出「GBK 裸名」的包，
    # 临时改掉它的编码钩子：条目名按原始字节落盘，且不设 UTF-8 标志位。
    _ORIG_ENC = zipfile.ZipInfo._encodeFilenameFlags
    zipfile.ZipInfo._encodeFilenameFlags = lambda self: (
        self.filename.encode('latin-1'), self.flag_bits & ~0x800)

    def _zi(raw):
        zi = zipfile.ZipInfo(raw.decode('latin-1'))
        zi.orig_filename = raw
        return zi

    name = '民国史料丛刊  587'
    zp = os.path.join(tmp3, 't.zip')
    with zipfile.ZipFile(zp, 'w') as z:
        z.writestr(_zi((name + '/').encode('gbk')), b'')
        for fn in ('000001.pdg',):
            z.writestr(_zi((name + '/' + fn).encode('gbk')), b'PDGDATA')
    zipfile.ZipInfo._encodeFilenameFlags = _ORIG_ENC
    B._7Z_CACHE['done'] = False
    _real_find = B.find_7z
    B.find_7z = lambda *a, **k: None      # 彻底掐掉外部引擎
    dest = os.path.join(tmp3, 'out')
    ok, pw, note = B.extract_archive(zp, dest, [], log=lambda *a: None)
    chk('没有 7z 也能解 zip', ok, note)
    chk('中文名照常正确', os.listdir(dest) == [name] if ok else False,
        str(os.listdir(dest)) if ok else '')
finally:
    B.find_7z = _real_find
    B._7Z_CACHE['done'] = False
    shutil.rmtree(tmp3, ignore_errors=True)

print()
print('=' * 60)
print('  %s  %s' % ('全部通过' if not fails else '有失败项', '；'.join(fails) or '（共 %d 项）' % 0))
print('=' * 60)
sys.exit(0 if not fails else 1)
