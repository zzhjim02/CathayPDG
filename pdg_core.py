# -*- coding: utf-8 -*-
"""
CathayPDG 引擎（第一块）：PDG 类型判定 / 页序 / 自建 PDF。

设计要点
  1. 先判类型：能自己解的就自己出 PDF；解不了（AAH 等）→ 整本交外部程序，本模块不拼接；
  2. 页尺寸：**不强求 A4** ——
       · 常规竖版页（长宽比接近 A4）→ 排成 A4；
       · 比 A4 大、或横着、或长宽比偏得多的页 → 保持自己的比例（长边对齐 A4 长边；面积明显大于 A4 时按原物理尺寸）；
       · 头里有「300 DPI 目标像素尺寸」声明时，按它折算出物理尺寸参与判断；
  3. 图太小（分辨率不够 OCR）→ 用 Lanczos 放大到「目标 DPI」（默认 300，上限 5 倍），够大就原样嵌入（零损失）；
  4. 页序按 Pdg2Pic 成品反推的规则：cov → bok → leg → fow → 目录(!) → 正文数字 → 末尾（封底等）。

自检：py -3 pdg_core.py --selftest
用法：--classify <书目录> ／ --make <书目录> <输出.pdf> [--no-a4] [--no-up]
"""
import io
import math
import os
import re
import struct
import sys

def _fix_stdout():
    """pythonw / PyInstaller --windowed 下 sys.stdout 可能是 None，不能直接包装。"""
    s = sys.stdout
    if s is None:
        return
    try:
        s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(s.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass


_fix_stdout()

APP_TITLE = 'CathayPDG · 超星 PDG 批量转换工具'
APP_VERSION = 'v0.1.5'

A4_W, A4_H = 595.276, 841.89          # A4（pt）
A4_AR = A4_W / A4_H                   # 0.7071
AR_TOL = 0.15                         # 长宽比在 A4 ±15% 内 → 当成常规页排 A4
BIG_AREA = 1.30                       # 物理面积 > 1.3 倍 A4 → 不强求，按原尺寸
TARGET_DPI = 300.0                    # 图太小时放大到的目标分辨率
MIN_DPI = 200.0                       # 低于这个有效分辨率才放大（>=200 就原样嵌入，零损失）
MAX_UPSCALE = 5.0                     # 最多放大 5 倍（避免爆体积）
JPG_QUALITY = 90

IMG_SIGS = [
    (b'\xff\xd8\xff', 'jpg'), (b'\x89PNG\r\n\x1a\n', 'png'), (b'II*\x00', 'tif'),
    (b'MM\x00*', 'tif'), (b'BM', 'bmp'), (b'GIF87a', 'gif'), (b'GIF89a', 'gif'),
    (b'AT&T', 'djvu'),
]

TYPE_MEAN = {
    0x00: '00H 未加密', 0x02: '02H 弱加密', 0x03: '03H 弱加密', 0x04: '04H 弱加密(JPG)',
    0x05: '05H 弱加密(DjVu)', 0x10: '10H 加密', 0x11: '11H 加密', 0x28: '28H 增强灰度',
    0x64: '64H 本机加密', 0x66: '66H 本机加密', 0xAA: 'AAH 强加密', 0xAC: 'ACH 强加密',
    0xFF: 'FFH 已损坏',
}
SELF_TYPES = {0x00, 0x02, 0x03, 0x04, 0x05}


# ---------------------------------------------------------------- CCITT G4（00H 黑白扫描）
_G4_CACHE = {}


def tiff_g4(payload, w, h, photometric=0):
    """把 CCITT G4（T.6）位流包成一个最小 TIFF（单 strip），交给 Pillow/libtiff 解。"""
    import struct as S
    ents = []
    for tag, typ, cnt, val in (
            (256, 4, 1, w), (257, 4, 1, h), (258, 3, 1, 1), (259, 3, 1, 4),
            (262, 3, 1, photometric), (266, 3, 1, 1), (277, 3, 1, 1), (278, 4, 1, h),
            (284, 3, 1, 1), (296, 3, 1, 2)):
        ents.append(S.pack('<HHII', tag, typ, cnt, val))
    ifd = 8
    n = len(ents) + 4
    extras = ifd + 2 + n * 12 + 4
    rat_off, strip_off = extras, extras + 16
    ents.append(S.pack('<HHII', 273, 4, 1, strip_off))     # StripOffsets
    ents.append(S.pack('<HHII', 279, 4, 1, len(payload)))  # StripByteCounts
    ents.append(S.pack('<HHII', 282, 5, 1, rat_off))       # XResolution
    ents.append(S.pack('<HHII', 283, 5, 1, rat_off + 8))   # YResolution
    ents.sort(key=lambda b: S.unpack_from('<H', b, 0)[0])
    out = [b'II', S.pack('<H', 42), S.pack('<I', ifd), S.pack('<H', n)]
    out += ents
    out.append(S.pack('<I', 0))
    out.append(S.pack('<II', 300, 1) + S.pack('<II', 300, 1))
    out.append(payload)
    return b''.join(out)


def ccitt_to_png(payload, w, h):
    """CCITT G4 位流 → PNG 字节（解不出或结果离谱就返回 None）。"""
    from PIL import Image
    if not payload or w < 8 or h < 8 or w > 30000 or h > 30000:
        return None
    for photo in (0, 1):
        try:
            im = Image.open(io.BytesIO(tiff_g4(payload, w, h, photo)))
            im.load()
        except Exception:
            continue
        g = im.convert('L')
        hist = g.histogram()
        tot = float(sum(hist)) or 1.0
        dark = sum(hist[:128]) / tot
        if 0.0005 <= dark <= 0.9:            # 全是黑/全是白 → 多半是解歪了
            buf = io.BytesIO()
            g.save(buf, 'PNG')
            return buf.getvalue()
    return None


def sniff_image(buf, off=0):
    for sig, ext in IMG_SIGS:
        if buf[off:off + len(sig)] == sig:
            return ext
    return None


def classify(path):
    with open(path, 'rb') as f:
        head = f.read(160)
        f.seek(0)
        whole = f.read(4096)
    r = {'name': os.path.basename(path), 'size': os.path.getsize(path),
         'code': head[15] if len(head) > 15 else -1}
    ext = sniff_image(whole)
    if ext:
        r.update(kind='image', subtype=ext, self_ok=True)
        return r
    if head[:2] == b'HH':
        r.update(kind='huff', subtype=TYPE_MEAN.get(r['code'], '?'),
                 self_ok=(r['code'] in SELF_TYPES))
        if len(head) >= 0x20:
            r['data_off'] = struct.unpack_from('<I', head, 0x18)[0]
            r['data_size'] = struct.unpack_from('<I', head, 0x1C)[0]
        if len(head) >= 0x14:
            dw = struct.unpack_from('<H', head, 0x10)[0]
            dh = struct.unpack_from('<H', head, 0x12)[0]
            if 50 <= dw <= 20000 and 50 <= dh <= 20000:
                r['declared'] = (dw, dh)          # 300 DPI 下的目标像素尺寸
        # 能不能自解，以「正文里是否真有标准图片」为准（不必猜编码代号）
        if r['self_ok']:
            with open(path, 'rb') as f2:
                f2.seek(r.get('data_off', 0))
                pay = f2.read(24)
            if sniff_image(pay):
                r['payload_ext'] = sniff_image(pay)
            elif head[3] == 0x00 and r.get('declared'):     # 00H = CCITT G4 黑白扫描
                r['ccitt'] = r['declared']
                r['subtype'] += '（CCITT G4）'
            else:
                r['self_ok'] = False
                r['subtype'] += '（正文非标准图片→交外挂）'
        return r
    r.update(kind='unknown', subtype='?', self_ok=False)
    return r


PAGE_EXTS = ('.pdg', '.jpg', '.jpeg', '.jfif', '.png', '.bmp', '.gif',
             '.tif', '.tiff', '.webp')


def scan_book(book_dir):
    files = sorted(f for f in os.listdir(book_dir) if f.lower().endswith(PAGE_EXTS))
    pages = [classify(os.path.join(book_dir, f)) for f in files]
    cc = [p for p in pages if p.get('ccitt')]
    if cc and all(pp['self_ok'] for pp in pages):
        blob = g4_page(os.path.join(book_dir, cc[0]['name']))
        if blob:                                  # 抽样解通了 → 整本按可自解
            for pp in cc:
                pp['g4_ok'] = True
        else:
            for pp in cc:                         # 解不通 → 整本老实交外挂
                pp['self_ok'] = False
                pp['subtype'] += '（G4 自解失败→交外挂）'
    self_cnt = sum(1 for p in pages if p['self_ok'])
    return {'dir': book_dir, 'pages': pages, 'total': len(pages), 'self_count': self_cnt,
            'need_external': [p['name'] for p in pages if not p['self_ok']],
            'can_self': self_cnt == len(pages) and bool(pages),
            'declared': declared_size(pages)}


def declared_size(pages):
    """从 HH 页里取最常见的「300 DPI 目标像素尺寸」当全书的物理尺寸依据。"""
    from collections import Counter
    c = Counter(p['declared'] for p in pages if p.get('declared'))
    return c.most_common(1)[0][0] if c else None


# ---------------------------------------------------------------- 页序（反推自 Pdg2Pic 成品）
GROUP = {'cov': 0, 'bok': 1, 'leg': 2, 'fow': 3, '!': 4}
BACK_NUM = {'cov', 'leg', 'bok'}


def order_key(name):
    stem = os.path.splitext(name)[0]
    m = re.match(r'^([A-Za-z!]+)(\d+)$', stem)
    if not m:
        if stem.isdigit():
            return (6, int(stem), '')
        return (9, 0, stem)
    pre, num = m.group(1), int(m.group(2))
    if pre in GROUP:
        if num > 1 and pre in BACK_NUM:
            return (8, num, '')
        return (GROUP[pre], num, '')
    return (7, num, stem)


def order_pages(pages):
    return sorted(pages, key=lambda p: order_key(p['name']))


# ---------------------------------------------------------------- 页尺寸策略（不强求 A4）
def page_box(iw, ih, declared=None):
    """返回 (box_w, box_h)（pt）。规则见模块说明。"""
    ar = iw / float(ih)
    if declared:
        pw, ph = declared[0] * 72.0 / TARGET_DPI, declared[1] * 72.0 / TARGET_DPI
        par = pw / ph
        if abs(par - ar) < 0.02:                       # 声明比例与图一致 → 以声明为准
            ar = par
        if pw * ph > BIG_AREA * A4_W * A4_H:           # 明显比 A4 大 → 保持原物理尺寸
            return pw, ph
        if abs(ar - A4_AR) <= AR_TOL:
            return A4_W, A4_H
    else:
        if abs(ar - A4_AR) <= AR_TOL:
            return A4_W, A4_H
    # 不强求：长边对齐 A4 长边，另一边按比例（横的也照此，不会被硬塞进 A4）
    long_side = A4_H
    if ar >= 1.0:
        return long_side, long_side / ar
    return long_side * ar, long_side


def _prepare_image(path, box_w, box_h, target_dpi=TARGET_DPI, max_up=MAX_UPSCALE,
                   min_dpi=MIN_DPI):
    """图太小（在目标页盒上的有效 DPI 低于 min_dpi）才放大；够大就原样嵌入（零损失）。
    返回 (bytes 或 None, ext, 放大倍数)。"""
    from PIL import Image
    blob0, ext0 = page_image_bytes(path)
    embed0 = None if ext0 is None else blob0    # HH 页必须交正文；普通图片交路径更快
    with Image.open(io.BytesIO(blob0)) as im:
        iw, ih = im.size                       # 真实像素（别用 fitz 的 page rect，它按 DPI 报点数）
        eff = min(iw / (box_w / 72.0), ih / (box_h / 72.0))
        if eff >= min_dpi:                     # 已经够清楚 → 原样嵌入，不重编码
            return embed0, (im.format or 'JPEG').lower(), 1.0
        need_w = box_w / 72.0 * target_dpi
        need_h = box_h / 72.0 * target_dpi
        k = min(need_w / iw, need_h / ih, max_up)
        k = max(k, 1.0)
        im2 = im.convert('RGB') if im.mode not in ('RGB', 'L') else im
        im2 = im2.resize((max(1, int(round(iw * k))), max(1, int(round(ih * k)))), Image.LANCZOS)
        buf = io.BytesIO()
        im2.save(buf, 'JPEG', quality=JPG_QUALITY, subsampling=0, optimize=True)
        return buf.getvalue(), 'jpg', k


def g4_page(path, head=None, blob=None):
    """CCITT G4 页 → PNG 字节（带缓存）；解不出返回 None。"""
    key = (path, os.path.getmtime(path) if os.path.exists(path) else 0)
    if key in _G4_CACHE:
        return _G4_CACHE[key]
    try:
        if head is None or blob is None:
            with open(path, 'rb') as f:
                head = f.read(160)
                do = struct.unpack_from('<I', head, 0x18)[0]
                ds = struct.unpack_from('<I', head, 0x1C)[0]
                f.seek(do)
                blob = f.read(ds if ds else None)
        w = struct.unpack_from('<H', head, 0x10)[0]
        h = struct.unpack_from('<H', head, 0x12)[0]
        png = ccitt_to_png(blob, w, h)
    except Exception:
        png = None
    _G4_CACHE[key] = png
    return png


def page_image_bytes(path):
    """这张页的「图片本体」字节。

    普通图片 = 整份文件；HH 头（超星 PDG 容器）= 按 0x18 偏移/0x1C 长度切出来的正文
    —— 正文才是真正的 JPEG/PNG，不能连 140 字节头一起丢给解码器。
    """
    with open(path, 'rb') as f:
        head = f.read(160)
        if head[:2] != b'HH' or len(head) < 0x20:
            f.seek(0)
            return f.read(), None
        do = struct.unpack_from('<I', head, 0x18)[0]
        ds = struct.unpack_from('<I', head, 0x1C)[0]
        f.seek(do)
        blob = f.read(ds if ds else None)
        ext1 = sniff_image(blob, 0)
        if ext1:
            return blob, ext1
        if head[3] == 0x00:                      # CCITT G4
            png = g4_page(path, head=head, blob=blob)
            if png:
                return png, 'png'
        return blob, None


def image_size(path):
    import fitz
    blob, ext0 = page_image_bytes(path)
    d = fitz.open(stream=blob, filetype=ext0 or sniff_image(blob, 0) or 'jpeg')
    r = d[0].rect
    d.close()
    return r.width, r.height


def assemble_pdf(book_dir, out_pdf, mode='auto', ocr_up=True, target_dpi=TARGET_DPI,
                 progress=None):
    """把一本全可自解的书合 PDF。mode: auto=A4(不强求) / native=原始像素尺寸。"""
    import fitz
    info = scan_book(book_dir)
    if not info['can_self']:
        raise RuntimeError('有 %d 页需要外部程序，不能自建：%s'
                           % (len(info['need_external']), info['need_external'][:3]))
    pages = order_pages(info['pages'])
    decl = info['declared']
    doc = fitz.open()
    stats = {'upscaled': 0, 'max_k': 1.0, 'sizes': set()}
    for i, p in enumerate(pages):
        path = os.path.join(book_dir, p['name'])
        iw, ih = image_size(path)
        if mode == 'native':
            bw, bh = iw, ih
        else:
            bw, bh = page_box(iw, ih, decl)
        stream = None
        if ocr_up:
            stream, ext, k = _prepare_image(path, bw, bh, target_dpi)
            if k > 1.02:
                stats['upscaled'] += 1
                stats['max_k'] = max(stats['max_k'], k)
        pg = doc.new_page(width=bw, height=bh)
        if stream:
            pg.insert_image(fitz.Rect(0, 0, bw, bh), stream=stream)
        else:
            pg.insert_image(fitz.Rect(0, 0, bw, bh), filename=path)
        stats['sizes'].add((round(bw), round(bh)))
        if progress:
            progress(i + 1, len(pages), p['name'])
    doc.save(out_pdf, deflate=True, garbage=3)
    doc.close()
    stats.update({'pages': len(pages), 'out': out_pdf, 'size': os.path.getsize(out_pdf),
                  'order': [p['name'] for p in pages], 'declared': decl})
    return stats


def relayout(src_pdf, out_pdf, mode='auto', ocr_up=False, target_dpi=TARGET_DPI):
    """把已有 PDF（外部程序成品）逐页按同一套尺寸策略重排；图太小可选放大。"""
    import fitz
    src = fitz.open(src_pdf)
    doc = fitz.open()
    stats = {'upscaled': 0, 'sizes': set()}
    for i in range(src.page_count):
        r = src[i].rect
        bw, bh = (r.width, r.height) if mode == 'native' else page_box(r.width, r.height)
        pg = doc.new_page(width=bw, height=bh)
        pg.show_pdf_page(fitz.Rect(0, 0, bw, bh), src, i)
        stats['sizes'].add((round(bw), round(bh)))
    doc.save(out_pdf, deflate=True, garbage=3)
    n = doc.page_count
    doc.close()
    src.close()
    stats.update({'pages': n, 'out': out_pdf, 'size': os.path.getsize(out_pdf)})
    return stats


# ---------------------------------------------------------------- CLI / 自检
def _selftest():
    import tempfile
    import shutil
    from PIL import Image
    lines = ['%s %s' % (APP_TITLE, APP_VERSION)]
    ok = True

    def chk(label, cond, extra=''):
        nonlocal ok
        lines.append('%s：%s%s' % (label, 'OK' if cond else 'FAIL', (' ' + str(extra)) if extra else ''))
        ok = ok and bool(cond)

    # 1) 页序
    names = ['cov002.pdg', '000010.pdg', '!00001.pdg', 'cov001.pdg', 'bok001.pdg',
             'leg001.pdg', 'fow001.pdg', '000001.pdg', '000002.pdg']
    got = [p['name'] for p in order_pages([{'name': n} for n in names])]
    want = ['cov001.pdg', 'bok001.pdg', 'leg001.pdg', 'fow001.pdg', '!00001.pdg',
            '000001.pdg', '000002.pdg', '000010.pdg', 'cov002.pdg']
    chk('页序规则', got == want, got if got != want else '')

    # 2) 尺寸策略
    cases = [
        ('常规竖版(接近A4)', (378, 567), None, (595, 842)),
        ('横版页', (1200, 800), None, None),
        ('细长竖版', (600, 1800), None, None),
        ('比A4大(A3)', (2000, 2828), None, None),
        ('头有声明(1625x2362)', (378, 567), (1625, 2362), (595, 842)),
        ('头声明很大(3000x4000)', (1000, 1333), (3000, 4000), (720, 960)),
    ]
    for label, (iw, ih), decl, exp in cases:
        bw, bh = page_box(iw, ih, decl)
        if exp:
            chk('尺寸策略·%s' % label, abs(bw - exp[0]) < 2 and abs(bh - exp[1]) < 2, (round(bw), round(bh)))
        else:
            # 不强求 A4：比例要保住、长边=842、不超 A4 宽
            ar_ok = abs((bw / bh) - (iw / ih)) < 0.02
            chk('尺寸策略·%s' % label, ar_ok and abs(max(bw, bh) - A4_H) < 2, (round(bw), round(bh)))

    tmp = tempfile.mkdtemp(prefix='pdgself_')
    try:
        Image.new('RGB', (200, 300), (180, 60, 60)).save(os.path.join(tmp, 'cov001.pdg'), 'JPEG', quality=92)
        Image.new('RGB', (378, 567), (40, 160, 60)).save(os.path.join(tmp, '!00001.pdg'), 'JPEG', quality=92)
        Image.new('RGB', (378, 567), (40, 60, 200)).save(os.path.join(tmp, '000001.pdg'), 'JPEG', quality=92)
        Image.new('RGB', (1200, 800), (120, 120, 120)).save(os.path.join(tmp, '000002.pdg'), 'JPEG', quality=92)
        st = assemble_pdf(tmp, os.path.join(tmp, 'out.pdf'))
        d = __import__('fitz').open(st['out'])
        szs = sorted(set((round(p.rect.width), round(p.rect.height)) for p in d))
        order_ok = st['order'] == ['cov001.pdg', '!00001.pdg', '000001.pdg', '000002.pdg']
        a4_ok = (595, 842) in szs
        land_ok = any(w > h for w, h in szs)
        d.close()
        chk('自建PDF·页序', order_ok, st['order'])
        chk('自建PDF·常规页=A4 且横版页保持横版', a4_ok and land_ok, szs)
        chk('自建PDF·小图放大到目标DPI', st['upscaled'] >= 3, '放大 %d 页, 最多 %.2f 倍'
            % (st['upscaled'], st['max_k']))
        # 放大后实际像素核对
        d = __import__('fitz').open(st['out'])
        im = d.extract_image(d[1].get_images(full=True)[0][0])
        d.close()
        chk('放大后像素（目标DPI 的 5 倍上限内尽量放大）',
            im['width'] >= 1800 and im['width'] / 595.276 * 72 >= 200,
            '%dx%d ≈ %.0f DPI' % (im['width'], im['height'], im['width'] / 595.276 * 72))
        # 重排
        st2 = relayout(st['out'], os.path.join(tmp, 're.pdf'))
        d2 = __import__('fitz').open(st2['out'])
        chk('重排·页数一致', st2['pages'] == st['pages'], st2['pages'])
        d2.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.append('result = %s' % ('OK' if ok else 'FAIL'))
    txt = '\n'.join(lines)
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_selftest.txt'),
         'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    return 0 if ok else 1


def main(argv):
    if '--selftest' in argv:
        return _selftest()
    if '--classify' in argv:
        d = argv[argv.index('--classify') + 1]
        info = scan_book(d)
        print('目录：%s' % d)
        print('总页数 %d ｜ 可自解 %d ｜ 需外部程序 %d' % (info['total'], info['self_count'],
                                                     len(info['need_external'])))
        print('判定：%s' % ('整本可自建 PDF' if info['can_self'] else '需交给外部程序'))
        print('头里声明的目标像素：%s（折合物理尺寸 %s mm）'
              % (info['declared'], None if not info['declared'] else
                 tuple(round(v * 25.4 / TARGET_DPI) for v in info['declared'])))
        from collections import Counter
        print('构成：%s' % Counter(p['subtype'] for p in info['pages']).most_common())
        return 0
    if '--make' in argv:
        d = argv[argv.index('--make') + 1]
        out = argv[argv.index('--make') + 2]
        st = assemble_pdf(d, out, mode=('native' if '--native' in argv else 'auto'),
                          ocr_up=('--no-up' not in argv))
        print('完成：%d 页 → %s（%.1f MB）｜ 放大 %d 页(最多 %.2f 倍) ｜ 页尺寸 %s'
              % (st['pages'], st['out'], st['size'] / 1e6, st['upscaled'], st['max_k'],
                 sorted(st['sizes'])[:4]))
        return 0
    print(__doc__)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

# ---------------------------------------------------------------- 横竖排判定
def _page_scores(im):
    """单页：(行起伏, 列起伏) 归一化标准差。横排文字→行起伏大；竖排→列起伏大。"""
    import numpy as np
    g = im.convert('L')
    w, h = g.size
    k = max(1, int(max(w, h) / 900))
    if k > 1:
        g = g.resize((max(1, w // k), max(1, h // k)))
    a = np.asarray(g, dtype=np.float32)
    ink = (a < 128).astype(np.float32)
    m = ink.mean()
    if m < 0.006 or m > 0.5:          # 空白页 / 满版插图页：跳过
        return None
    rows = ink.sum(axis=1)
    cols = ink.sum(axis=0)
    return (float(rows.std() / (rows.mean() + 1e-6)),
            float(cols.std() / (cols.mean() + 1e-6)))


def _sample_indices(n):
    """抽样页：<10 页就逐页；否则第 5 页 + 20/40/60/80/90%。"""
    if n < 10:
        return list(range(n))
    idx = {4}
    for p in (0.2, 0.4, 0.6, 0.8, 0.9):
        idx.add(min(n - 1, int(n * p)))
    return sorted(idx)


def detect_orientation_pdf(pdf_path, scan_dir=None, log=None, ratio=1.12, vote=1.5):
    """判一本的横竖排。返回 (标签, 置信度, 说明)。

    投影法：把页面二值化，算「行投影」和「列投影」的起伏。横排文字的行方向
    有字/无字交替（行起伏大）；竖排文字则列方向交替（列起伏大）。采样多页投票，
    空白页/插图页跳过，混排取多数，票数咬得紧就报「未知」。
    """
    import fitz
    from PIL import Image
    doc = fitz.open(pdf_path)
    n = doc.page_count
    hs = vs = skipped = 0
    pages = _sample_indices(n)
    for i in pages:
        pm = doc[i].get_pixmap(matrix=fitz.Matrix(1.6, 1.6), colorspace=fitz.csGRAY)
        im = Image.frombytes('L', (pm.width, pm.height), pm.samples)
        s = _page_scores(im)
        if not s:
            skipped += 1
            continue
        rs, cs = s
        if rs > cs * ratio:
            hs += 1
        elif cs > rs * ratio:
            vs += 1
    doc.close()
    tot = hs + vs
    if tot == 0:
        return '未知', 0.0, '没有可判定的正文页（跳过 %d）' % skipped
    if hs > vs * vote:
        return '横排', round(hs / tot, 2), '%d/%d 页判为横排（跳过 %d）' % (hs, tot, skipped)
    if vs > hs * vote:
        return '竖排', round(vs / tot, 2), '%d/%d 页判为竖排（跳过 %d）' % (vs, tot, skipped)
    return '未知', round(max(hs, vs) / tot, 2), '横竖混排：横 %d / 竖 %d（跳过 %d）' % (hs, vs, skipped)

