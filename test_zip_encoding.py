# -*- coding: utf-8 -*-
"""验证 CathayPDG 的压缩包中文名解码。"""
import os
import sys
import shutil
import tempfile
import zipfile

SRC = os.path.dirname(os.path.abspath(__file__))   # 跟源码放一起，拷到哪都能跑
sys.path.insert(0, SRC)
import pdg_batch as B

ok_all = True


def chk(label, got, want):
    global ok_all
    good = got == want
    ok_all = ok_all and good
    print('%s %s' % ('OK ' if good else 'FAIL', label))
    if not good:
        print('     got : %r' % got)
        print('     want: %r' % want)


print('--- 1) decode_zip_name 直接解码 ---')
gbk = '民国史料丛刊  587  经济·工业_12421659'.encode('gbk')
chk('GBK 裸名（无标志位）', B.decode_zip_name(gbk, 0), '民国史料丛刊  587  经济·工业_12421659')
utf8 = '简体中文测试册'.encode('utf-8')
chk('UTF-8 名（有标志位）', B.decode_zip_name(utf8, 0x800), '简体中文测试册')
big5 = '繁體中文測試冊'.encode('big5')
chk('Big5 裸名', B.decode_zip_name(big5, 0), '繁體中文測試冊')
chk('纯 ASCII', B.decode_zip_name(b'catalog/000001.pdg', 0), 'catalog/000001.pdg')

print('\n--- 2) 乱码名识别与还原 ---')
bad = gbk.decode('cp437', errors='replace')
print('     乱码样本: %r' % bad)
chk('判定为乱码', B._looks_mojibake(bad), True)
chk('还原回中文', B._unmojibake(bad), '民国史料丛刊  587  经济·工业_12421659')
chk('正常名不乱判', B._looks_mojibake('民国史料丛刊'), False)

print('\n--- 3) 真包落盘（GBK / UTF-8 / Big5 三种造包） ---')
# zipfile 写盘时非 ASCII 一律走 UTF-8 并置标志位，造不出「GBK 裸名」的包，
# 所以临时改掉它的编码钩子，让条目名按原始字节落盘、且不设 UTF-8 标志位。
def _raw_info(raw):
    zi = zipfile.ZipInfo(raw.decode('latin-1'))
    zi.orig_filename = raw
    return zi


def _enc_hook(self):
    return self.filename.encode('latin-1'), self.flag_bits & ~0x800


_ORIG_ENC = zipfile.ZipInfo._encodeFilenameFlags

tmp = tempfile.mkdtemp(prefix='zipenc_')
for tag, enc in (('gbk', 'gbk'), ('utf8', 'utf-8'), ('utf8_noflag', 'utf-8'),
                 ('big5', 'big5')):
    name = {'gbk': '简体测试书  第01册', 'utf8': '简体测试书  第02册',
            'utf8_noflag': '简体测试书  第04册', 'big5': '繁體測試書  第03冊'}[tag]
    zp = os.path.join(tmp, tag + '.zip')
    with zipfile.ZipFile(zp, 'w') as z:
        if tag == 'utf8':                        # 规范做法：UTF-8 + 置标志位
            zipfile.ZipInfo._encodeFilenameFlags = _ORIG_ENC
            z.writestr(name + '/', b'')
            for fn in ('000001.pdg', 'cov001.pdg'):
                z.writestr(name + '/' + fn, b'PDGDATA')
        else:                                    # 裸名：原始字节 + 不置标志位
            zipfile.ZipInfo._encodeFilenameFlags = _enc_hook
            z.writestr(_raw_info((name + '/').encode(enc)), b'')
            for fn in ('000001.pdg', 'cov001.pdg'):
                z.writestr(_raw_info((name + '/' + fn).encode(enc)), b'PDGDATA')
    dest = os.path.join(tmp, 'out_' + tag)
    good = B._try_zip(zp, dest, None)
    got = os.listdir(dest) if good and os.path.isdir(dest) else []
    chk('%s 包解压出的目录名' % tag, got, [name])
    if got:
        inner = os.listdir(os.path.join(dest, name))
        chk('%s 包内文件名' % tag, sorted(inner), ['000001.pdg', 'cov001.pdg'])
zipfile.ZipInfo._encodeFilenameFlags = _ORIG_ENC

print('\n--- 4) fix_mojibake_names 兜底（模拟 7z 出来的乱码目录） ---')
root = os.path.join(tmp, 'moji')
os.makedirs(os.path.join(root, bad), exist_ok=True)
open(os.path.join(root, bad, '000001.pdg'), 'wb').write(b'x')
badfile = '经济·工业'.encode('gbk').decode('cp437', errors='replace')
open(os.path.join(root, badfile + '.pdg'), 'wb').write(b'x')
n = B.fix_mojibake_names(root)
chk('修回条数', n, 2)
chk('目录已改回', os.listdir(root),
    ['民国史料丛刊  587  经济·工业_12421659', '经济·工业.pdg'])

print('\n--- 5) 目录穿越防护 ---')
chk('../ 被挡住', B._safe_join(tmp, '../../evil.pdg'), os.path.join(tmp, 'evil.pdg'))

shutil.rmtree(tmp, ignore_errors=True)
print('\n==== %s ====' % ('全部通过' if ok_all else '有失败项'))
sys.exit(0 if ok_all else 1)
