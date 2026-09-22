# -*- coding: utf-8 -*-
"""
CathayPDG 引擎（第三块）：批量 —— 解压 → 判定 → 自建 / 交外挂 → 出 A4 PDF + 报告。

流程（对应需求文档"功能一"）：
  1. 扫输入目录，找压缩包（zip/uvz/7z/rar）和已解开的书目录（含 .pdg 的最内层目录）；
  2. 压缩包先解压：zip/uvz 用 zipfile（不支持 AES 时转 pyzipper），7z/rar 调 7z.exe；
     密码按密码本逐条试，只校验前 3 个非目录项；单个失败不中断整批；
  3. 嵌套展开：书目录里只有一层同名子目录 → 自动下钻；
  4. 判定类型：全可自解 → 自建 A4 PDF；含 AAH 等 → 交 pdg_external（Pdg2Pic）；
  5. 输出 <书目录名>.pdf（A4/不强求）到源文件夹，重名自动加序号；已存在同名 PDF 视为已处理（智能跳过，可关）；
  6. 原始压缩包可移入 输入目录\\_已处理（默认开）；
  7. 出报告 CSV + Markdown（含失败清单和外挂错误日志摘要）。

自检：py -3 pdg_batch.py --selftest
用法：py -3 pdg_batch.py --run <输入目录> [输出目录] [--no-archive] [--force] [--keep-unpacked]
    （输出目录留空 = 成品 PDF 直接放回输入目录）
"""
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import time
import zipfile

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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pdg_core as C
import pdg_external as X

APP_TITLE = 'CathayPDG · 超星 PDG 批量转换工具'
APP_VERSION = 'v0.1.5'
SEVENZ = r'C:\Program Files\7-Zip\7z.exe'
PDG2PIC = X.DEFAULT_EXE
PW_FILE = os.path.join(HERE, 'config', 'passwords.txt')
ARCHIVE_EXT = ('.zip', '.uvz', '.7z', '.rar', '.zipx')


def app_dir():
    """程序自己所在的目录：冻结时是 exe 旁边，源码时是脚本目录。

    注意不能用 __file__ —— 打包成单文件后它指向 _MEI 临时目录，
    那样用户就改不到自己那份密码本了。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def passwords(extra=None):
    # 优先用「程序所在目录」里的密码本（用户能自己改、自己加）
    ad = app_dir()
    for cand in (os.path.join(ad, '程序组件', 'config', 'passwords.txt'),
                 os.path.join(ad, 'config', 'passwords.txt'),
                 os.path.join(os.path.dirname(ad), '程序组件', 'config', 'passwords.txt'),
                 os.path.join(os.path.dirname(ad), 'config', 'passwords.txt')):
        if os.path.isfile(cand) and os.path.abspath(cand) != os.path.abspath(PW_FILE):
            try:
                out0 = [l.strip() for l in open(cand, encoding='utf-8',
                                                errors='replace').read().splitlines()
                        if l.strip() and not l.startswith('#')]
                if out0:
                    return sorted(set(out0) | set(extra or []))
            except Exception:
                pass
    out = []
    if os.path.exists(PW_FILE):
        for l in open(PW_FILE, encoding='utf-8', errors='replace').read().splitlines():
            l = l.strip()
            if l and l not in out:
                out.append(l)
    for p in (extra or []):
        if p and p not in out:
            out.append(p)
    return out


# ---------------------------------------------------------------- 解压
def _has_pdg(d):
    try:
        return any(f.lower().endswith(C.PAGE_EXTS) for f in os.listdir(d))
    except OSError:
        return False


def find_books(root):
    """返回 (书目录列表, 压缩包列表)。书目录 = 含 .pdg 的最内层目录。"""
    books, arcs = [], []
    for dp, dns, fns in os.walk(root):
        if os.path.basename(dp) in CABINETS:
            dns[:] = []
            continue
        keep = []
        for d in dns:
            if _has_pdg(os.path.join(dp, d)):
                books.append(os.path.join(dp, d))
            else:
                keep.append(d)
        dns[:] = keep
        if _has_pdg(dp):
            books.append(dp)
        for f in fns:
            if f.lower().endswith(ARCHIVE_EXT):
                arcs.append(os.path.join(dp, f))
    # 去掉被包含的子目录（父即书目录时不再列子）
    books = sorted(set(books))
    return books, sorted(set(arcs))


def flatten_book(d):
    """嵌套展开：只有一层同名子目录时下钻。"""
    cur = d
    for _ in range(8):
        try:
            items = os.listdir(cur)
        except OSError:
            break
        subs = [i for i in items if os.path.isdir(os.path.join(cur, i))]
        files = [i for i in items if os.path.isfile(os.path.join(cur, i))]
        if len(subs) == 1 and not files and not _has_pdg(cur):
            cur = os.path.join(cur, subs[0])
        else:
            break
    return cur


def _try_zip(path, dest, pw):
    """zipfile 先（ZipCrypto）；AES 交给 pyzipper。返回 True/False。"""
    try:
        with zipfile.ZipFile(path) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            if not infos:
                return False
            sample = [i for i in infos[:3]]
            for i in sample:
                z.open(i, pwd=pw.encode('utf-8') if pw else None).read(64)
            z.extractall(dest, pwd=pw.encode('utf-8') if pw else None)
        return True
    except Exception:
        pass
    try:
        import pyzipper
        with pyzipper.AESZipFile(path) as z:
            infos = [i for i in z.infolist() if not i.filename.endswith('/')]
            if not infos:
                return False
            for i in infos[:3]:
                with z.open(i, pwd=pw.encode('utf-8') if pw else None) as fh:
                    fh.read(64)
            z.extractall(dest, pwd=pw.encode('utf-8') if pw else None)
        return True
    except Exception:
        return False


def _try_7z(path, dest, pw=None):
    if not os.path.exists(SEVENZ):
        return False
    cmd = [SEVENZ, 'x', path, '-o' + dest, '-y', '-bso0', '-bsp0']
    if pw is not None:
        cmd.append('-p' + pw)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=1800,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.returncode == 0
    except Exception:
        return False


def extract_archive(path, dest, pws, log=print):
    """解压一个压缩包（自动试密码）。返回 (ok, 用到的密码, 说明)。"""
    os.makedirs(dest, exist_ok=True)
    low = path.lower()
    tries = [None] + list(pws) if not low.endswith(('.7z', '.rar')) else list(pws) + [None]
    if low.endswith(('.zip', '.uvz', '.zipx')):
        for pw in tries:
            if _try_zip(path, dest, pw):
                return True, pw, 'zip'
        # 兜底：有些"zip"其实是 7z/rar 换名
        for pw in tries:
            if _try_7z(path, dest, pw):
                return True, pw, '7z(兜底)'
        return False, None, '解压失败（密码本未命中或包损坏）'
    for pw in tries:
        if _try_7z(path, dest, pw):
            return True, pw, '7z'
    return False, None, '解压失败'


# ---------------------------------------------------------------- 目录约定
DIR_H = '横排'          # 处理完成、判定为横排
DIR_V = '竖排'          # 处理完成、判定为竖排
DIR_UNK = '横竖待识别'   # 处理完成、但横竖判不出来
DIR_DONE = '已处理'      # 成功那批的原始文件 + 中间产物
DIR_FAIL = '处理失败'    # 失败那批的源文件 + 中间产物
CABINETS = (DIR_H, DIR_V, DIR_UNK, DIR_DONE, DIR_FAIL)


# ---------------------------------------------------------------- 单本处理
def _process_book_one(book, out_dir, exe=PDG2PIC, log=print, force=False, control=None):
    """处理一本：能自建就自建，否则交外挂。返回记录 dict。"""
    book = flatten_book(book)
    name = os.path.basename(os.path.normpath(book))
    try:
        info = C.scan_book(book)
    except Exception as e:
        return {'book': name, 'pages': '', 'mode': '失败', 'out': '', 'ok': False,
                'secs': 0.0, 'orient': '', 'orient_note': '',
                'note': '这本读不出来（不是标准 PDG 或文件损坏）：%s' % e}
    out_pdf = os.path.join(out_dir, name + '.pdf')
    if os.path.exists(out_pdf) and not force:
        return {'book': name, 'pages': info['total'], 'mode': '跳过', 'out': out_pdf,
                'ok': True, 'note': '同名 PDF 已存在（智能跳过）', 'secs': 0.0}
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    if info['can_self']:
        st = C.assemble_pdf(book, out_pdf, mode='auto', ocr_up=True)
        return {'book': name, 'pages': st['pages'], 'mode': '自建',
                'out': st['out'], 'ok': True, 'secs': time.time() - t0,
                'note': '放大 %d 页' % st['upscaled'] if st['upscaled'] else ''}
    res = X.convert_book(book, out_dir, exe=exe, a4=True, log=log)
    if res.get('a4'):
        # 用 A4 版替换直出版本名，直出版本删掉
        try:
            os.replace(res['a4'], out_pdf)
        except Exception:
            pass
        try:
            if os.path.exists(res['pdf']) and os.path.abspath(res['pdf']) != os.path.abspath(out_pdf):
                os.remove(res['pdf'])
        except Exception:
            pass
    note = '结束判定：%s' % res.get('done_by', '')
    if res.get('dir_error'):
        note = 'Pdg2Pic 报「%s」 ｜ ' % res['dir_error'] + note
    if res.get('popups'):
        note += ' ｜ 弹窗：' + ' / '.join(res['popups'])[:120]
    if res.get('error_log'):
        tail = [l for l in res['error_log'].splitlines() if l.strip()][-3:]
        if tail:
            note += ' ｜ 日志：' + ' / '.join(tail)[:200]
    return {'book': name, 'pages': res.get('pages'), 'mode': '外挂',
            'out': out_pdf, 'ok': bool(res.get('pdf')), 'secs': time.time() - t0, 'note': note}


def process_book(book, out_dir, exe=PDG2PIC, log=print, force=False, control=None,
                 orient_dir=True):
    """单本 → 成品 PDF；顺手判横竖排，并放进 横排/竖排/横竖待识别 子目录。"""
    r = _process_book_one(book, out_dir, exe=exe, log=log, force=force, control=control)
    r.setdefault('orient', '')
    r.setdefault('orient_note', '')
    if r.get('ok') and r.get('out') and os.path.exists(r['out']):
        try:
            lab, conf, det = C.detect_orientation_pdf(r['out'], log=log)
        except Exception as e:
            lab, conf, det = '未知', 0.0, '判定出错：%s' % e
        r['orient'], r['orient_conf'], r['orient_note'] = lab, conf, det
        log('横竖排判定：%s（置信 %.2f ｜ %s）' % (lab, conf, det))
        if orient_dir:
            sub = DIR_UNK if lab not in ('横排', '竖排') else (DIR_H if lab == '横排' else DIR_V)
            try:
                dst = os.path.join(out_dir, sub)
                os.makedirs(dst, exist_ok=True)
                tgt = os.path.join(dst, os.path.basename(r['out']))
                if os.path.abspath(r['out']) != os.path.abspath(tgt):
                    os.replace(r['out'], tgt)
                r['out'] = tgt
            except Exception as e:
                log('放进「%s」失败：%s' % (sub, e))
    else:
        r['orient'], r['orient_conf'] = '', 0.0
    return r


# ---------------------------------------------------------------- 批量
def run_many(paths, out_dir=None, **kw):
    """支持一次给多个文件/文件夹。

    文件夹 → 处理这个文件夹；单个文件（压缩包）→ 只处理它自己，输出仍放它所在目录。
    最后把全部记录合成一份报告。
    """
    allrecs, tot = [], {'total': 0, 'ok': 0, 'fail': 0, 'self': 0, 'external': 0, 'skip': 0}
    outp = out_dir or (os.path.abspath(paths[0]) if paths and os.path.isdir(paths[0])
                       else os.path.dirname(os.path.abspath(paths[0])))
    for i, p in enumerate(paths, 1):
        p = os.path.abspath(p)
        root = p if os.path.isdir(p) else os.path.dirname(p)
        kw['log'](('\n===== [%d/%d] %s =====' % (i, len(paths), p)))
        recs, summ = run(root, out_dir or root, only=([p] if os.path.isfile(p) else None),
                         report=False, **kw)
        allrecs.extend(recs)
        for k in tot:
            tot[k] += summ.get(k, 0)
    if allrecs:
        write_report(allrecs, tot, outp)
    return allrecs, tot


def run(root, out_dir=None, exe=PDG2PIC, archive=True, force=False, workdir=None,
        log=print, progress=None, control=None, only=None, report=True):
    """批量处理整棵目录。返回 (records, summary)。

    out_dir 留空（None）＝直接把成品 PDF 放回源文件夹（输入目录）本身。
    解压临时目录默认放到系统临时区，不在源文件夹里堆东西。
    """
    import tempfile
    out_dir = out_dir or root
    workdir = workdir or os.path.join(tempfile.gettempdir(), 'pdgu_' +
                                     hashlib.md5(root.encode('utf-8')).hexdigest()[:8])
    pws = passwords()
    recs = []
    log('输入：%s\n输出：%s\n密码本：%d 条' % (root, out_dir, len(pws)))

    if root and os.path.isfile(root):            # 输入是「文件」→ 用它的目录，且只处理它
        _f = os.path.abspath(root)
        root = os.path.dirname(_f)
        if not only:
            only = [_f]                      # 必须是绝对路径（过滤按 abspath 比）
    if out_dir and os.path.isfile(out_dir):      # 输出是文件 → 取它所在目录
        out_dir = os.path.dirname(os.path.abspath(out_dir))
    out_dir = out_dir or root
    books, arcs = find_books(root)
    if only:                      # 只处理指定的这几个（拖入单个文件时用）
        oabs = {os.path.abspath(p) for p in only}
        arcs = [a for a in arcs if os.path.abspath(a) in oabs]
        books = [b for b in books
                 if os.path.abspath(b) in oabs
                 or any(os.path.abspath(b).startswith(o + os.sep) for o in oabs)]
        log('限定范围：%s' % ', '.join(os.path.basename(p) for p in only))
    log('发现：已解开的书 %d 本，压缩包 %d 个' % (len(books), len(arcs)))

    for i, a in enumerate(arcs):
        if control is not None and control.get('stop'):
            break
        if control is not None:
            while control.get('pause') and not control.get('stop'):
                time.sleep(0.3)
        dest = os.path.join(workdir, os.path.splitext(os.path.basename(a))[0])
        t0 = time.time()
        ok, pw, how = extract_archive(a, dest, pws, log=log)
        log('[%d/%d] 解压 %s → %s（%s%s）' % (i + 1, len(arcs), os.path.basename(a),
                                            '成功' if ok else '失败', how,
                                            '' if pw is None else '，密码 %s' % pw))
        recs.append({'book': os.path.basename(a), 'pages': '', 'mode': '解压',
                     'out': dest if ok else '', 'ok': ok, 'secs': time.time() - t0,
                     'note': '%s%s' % (how, '' if pw is None else ' 密码 %s' % pw)})
        if ok:
            books.extend([b for b in find_books(dest)[0]])

    books = sorted(set(flatten_book(b) for b in books))
    log('待处理书目录：%d 本' % len(books))
    for i, b in enumerate(books):
        if control is not None and control.get('stop'):
            break
        if control is not None:
            while control.get('pause') and not control.get('stop'):
                time.sleep(0.3)
        if progress:
            progress(i + 1, len(books), os.path.basename(b))
        try:
            r = process_book(b, out_dir, exe=exe, log=log, force=force, control=control)
        except Exception as e:
            r = {'book': os.path.basename(b), 'pages': '', 'mode': '失败', 'out': '',
                 'ok': False, 'secs': 0.0, 'note': '%s: %s' % (type(e).__name__, e)}
        recs.append(r)
        log('[%d/%d] %s ｜ %s ｜ %s 页 ｜ %.1fs ｜ %s'
            % (i + 1, len(books), r['book'], r['mode'], r.get('pages'), r['secs'],
               'OK' if r['ok'] else 'FAIL ' + str(r.get('note'))[:80]))

    if archive:
        for cab in (DIR_DONE, DIR_FAIL):
            os.makedirs(os.path.join(root, cab), exist_ok=True)

        def _cab_of(stem):
            """这本书整体算成功还是失败（多卷/多目录取全部成功才算成功）。"""
            rs = [r for r in recs if r['book'].startswith(stem) and r['mode'] != '解压']
            okk = bool(rs) and all(r['ok'] for r in rs)
            return os.path.join(root, DIR_DONE if okk else DIR_FAIL)

        moved = 0
        # a) 压缩包 + 它解压出来的中间目录（中间产物）
        for a in arcs:
            stem = os.path.splitext(os.path.basename(a))[0]
            cabdir = _cab_of(stem)
            for srcp in (a, os.path.join(workdir, stem)):
                if os.path.exists(srcp):
                    try:
                        shutil.move(srcp, os.path.join(cabdir, os.path.basename(srcp)))
                        moved += 1
                    except Exception as e:
                        log('归档失败：%s (%s)' % (os.path.basename(srcp), e))
        # b) 本来就摆在根目录里的书目录
        for b in books:
            bp = os.path.abspath(b)
            if not os.path.isdir(bp) or os.path.dirname(bp) != os.path.abspath(root):
                continue
            r = next((x for x in recs if x['book'] == os.path.basename(b)), None)
            if not r:
                continue
            cabdir = os.path.join(root, DIR_DONE if r['ok'] else DIR_FAIL)
            try:
                shutil.move(bp, os.path.join(cabdir, os.path.basename(b)))
                moved += 1
            except Exception as e:
                log('归档失败：%s (%s)' % (os.path.basename(b), e))
        log('归档 %d 项：成功 → %s\\%s ｜ 失败 → %s\\%s'
            % (moved, os.path.basename(root), DIR_DONE, os.path.basename(root), DIR_FAIL))

    okn = sum(1 for r in recs if r['ok'])
    summary = {'total': len(recs), 'ok': okn, 'fail': len(recs) - okn,
               'self': sum(1 for r in recs if r['mode'] == '自建' and r['ok']),
               'external': sum(1 for r in recs if r['mode'] == '外挂' and r['ok']),
               'skip': sum(1 for r in recs if r['mode'] == '跳过')}
    if report:
        write_report(recs, summary, out_dir)
    return recs, summary


def write_report(recs, summary, out_dir, stamp=None):
    stamp = stamp or time.strftime('%Y%m%d_%H%M%S')
    csv_p = os.path.join(out_dir, '转换报告_%s.csv' % stamp)
    md_p = os.path.join(out_dir, '转换报告_%s.md' % stamp)
    cols = ['book', 'pages', 'mode', 'orient', 'ok', 'secs', 'out', 'note']
    cols_cn = ['来源/书名', '页数', '处理方式', '横竖排', '成功', '耗时(秒)', '输出', '备注']
    with open(csv_p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(cols_cn)
        for r in recs:
            w.writerow(['%s' % r.get(c, '') for c in cols[:4]] + ['%s' % r.get('ok', '')] +
                       ['%.1f' % r.get('secs', 0), '%s' % r.get('out', ''),
                        '%s' % r.get('note', '')])
    L = ['# CathayPDG 转换报告', '',
         '共 %d 项 ｜ 成功 %d ｜ 失败 %d ｜ 自建 %d ｜ 外挂 %d ｜ 跳过 %d'
         % (summary['total'], summary['ok'], summary['fail'], summary['self'],
            summary['external'], summary['skip']), '',
         '| 来源/书名 | 页数 | 处理方式 | 横竖排 | 结果 | 耗时 | 备注 |',
         '|---|---|---|---|---|---|---|']
    for r in recs:
        L.append('| %s | %s | %s | %s | %s | %.1fs | %s |'
                 % (r.get('book', ''), r.get('pages', ''), r.get('mode', ''),
                    r.get('orient', '') or '—', '✅' if r['ok'] else '❌', r.get('secs', 0),
                    str(r.get('note', '')).replace('|', '/')))
    open(md_p, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return csv_p, md_p


# ---------------------------------------------------------------- 自检
def _selftest():
    import tempfile
    lines = ['%s %s' % (APP_TITLE, APP_VERSION)]
    ok = True

    def chk(label, cond, extra=''):
        nonlocal ok
        lines.append('%s：%s%s' % (label, 'OK' if cond else 'FAIL', (' ' + str(extra)) if extra else ''))
        ok = ok and bool(cond)

    chk('密码本', len(passwords()) >= 300, '%d 条' % len(passwords()))

    tmp = tempfile.mkdtemp(prefix='pdgbatch_')
    try:
        # 造一本「可自解」的书 + 一个加密 zip（含一本可自解的书）
        b1 = os.path.join(tmp, 'in', '甲书')
        os.makedirs(b1)
        from PIL import Image
        for nm, col in (('cov001.pdg', (200, 40, 40)), ('!00001.pdg', (40, 160, 60)),
                        ('000001.pdg', (40, 60, 200)), ('cov002.pdg', (90, 90, 90))):
            Image.new('L', (2008, 3000), 200).save(os.path.join(b1, nm), 'JPEG', quality=80)
        # 嵌套：乙书/乙书/...
        b2 = os.path.join(tmp, 'in', '乙书', '乙书')
        os.makedirs(b2)
        Image.new('L', (2008, 3000), 210).save(os.path.join(b2, '000001.pdg'), 'JPEG', quality=80)
        # 打包
        zp = os.path.join(tmp, 'in', '丙书.zip')
        import pyzipper
        with pyzipper.AESZipFile(zp, 'w', compression=zipfile.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as z:
            z.setpassword(b'52gv')
            data = open(os.path.join(b1, '000001.pdg'), 'rb').read()
            z.writestr('丙书/000001.pdg', data)
        pws = passwords(['52gv'])
        books, arcs = find_books(os.path.join(tmp, 'in'))
        chk('发现书目录/压缩包', len(books) == 2 and len(arcs) == 1, (books, arcs))
        chk('嵌套展开', os.path.basename(flatten_book(os.path.join(tmp, 'in', '乙书'))) == '乙书')
        okx, pw, how = extract_archive(zp, os.path.join(tmp, 'un', '丙书'), pws)
        chk('AES 加密 zip 解压（密码 52gv）', okx and pw == '52gv', '%s %s' % (pw, how))
        recs, summ = run(os.path.join(tmp, 'in'), os.path.join(tmp, 'out'),
                         archive=True, log=lambda *a, **k: None)
        chk('批量：全部成功', summ['fail'] == 0 and summ['ok'] == summ['total'], summ)
        chk('批量：自建 %d 本' % summ['self'], summ['self'] >= 3, summ)
        chk('归档 _已处理', os.path.exists(os.path.join(tmp, 'in', '_已处理', '丙书.zip')))
        outs = sorted(os.listdir(os.path.join(tmp, 'out')))
        pdfs = [o for o in outs if o.endswith('.pdf')]
        chk('产出 PDF', len(pdfs) >= 3, outs)
        chk('报告文件', any(o.startswith('转换报告_') for o in outs), outs)
        import fitz
        d = fitz.open(os.path.join(tmp, 'out', '甲书.pdf'))
        chk('甲书 A4/页序', d.page_count == 4 and round(d[0].rect.width) == 595, d.page_count)
        d.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.append('result = %s' % ('OK' if ok else 'FAIL'))
    txt = '\n'.join(lines)
    open(os.path.join(HERE, '_selftest_batch.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    return 0 if ok else 1


def main(argv):
    if '--selftest' in argv:
        return _selftest()
    if '--run' in argv:
        i = argv.index('--run')
        root, outd = argv[i + 1], argv[i + 2]
        recs, summ = run(root, outd, archive=('--no-archive' not in argv),
                         force=('--force' in argv))
        print('完成：%s' % summ)
        return 0 if summ['fail'] == 0 else 1
    print(__doc__)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
