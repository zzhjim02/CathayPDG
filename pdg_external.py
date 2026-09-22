# -*- coding: utf-8 -*-
"""
CathayPDG 引擎（第二块）：调用 Pdg2Pic 处理自己解不了的书。

要点
  · 全程只用窗口消息（WM_COMMAND / WM_DROPFILES），不移动鼠标、不抢焦点；
    选目录用「把文件夹拖进它窗口」的办法（老对话框跨 32/64 位不可靠）；
  · 绝不改它的 ini 配置（只在需要时读，不改用户设置）；
  · 完成判定以「弹窗」为主（处理完成会弹窗；出错会问是否打开错误报告 → 一律按「否」并把日志读回来）；
  · 产出 PDF 之后再重排成 A4。

自检：py -3 pdg_external.py --selftest
用法：py -3 pdg_external.py --run <书目录> <输出目录> [--exe 路径] [--keep] [--no-a4]
"""
import ctypes
import io
import os
import shutil
import subprocess
import sys
import time

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

import pdg_core as C

DEFAULT_EXE = r'D:\Program Files\Pdg2Pic\Pdg2Pic.exe'
WM_COMMAND = 0x0111
WM_SETTEXT = 0x000C
WM_CLOSE = 0x0010
BN_CLICKED = 0
SW_SHOWMINNOACTIVE = 7
MAKEWPARAM = lambda lo, hi: (lo & 0xFFFF) | ((hi & 0xFFFF) << 16)

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]


# ---------------------------------------------------------------- win32 小工具
def enum_windows():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 2)
            u32.GetWindowTextW(hwnd, buf, n + 2)
            cls = ctypes.create_unicode_buffer(64)
            u32.GetClassNameW(hwnd, cls, 64)
            if buf.value:
                out.append((hwnd, cls.value, buf.value))
        return True

    u32.EnumWindows(cb, 0)
    return out


def find_window(title_sub, cls_sub='#32770', timeout=60, exclude=()):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for hwnd, cls, ttl in enum_windows():
            if cls_sub in cls and title_sub in ttl and hwnd not in exclude:
                return hwnd, cls, ttl
        time.sleep(0.3)
    return None, None, None


def child_windows(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        cls = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(h, cls, 64)
        n = u32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 2)
        u32.GetWindowTextW(h, buf, n + 2)
        out.append((h, cls.value, buf.value))
        return True

    u32.EnumChildWindows(hwnd, cb, 0)
    return out


def child_by_id(hwnd, cid):
    h = u32.GetDlgItem(hwnd, cid)
    return h or None


def post_click(hwnd, cid):
    """给子控件发点击（不阻塞）。"""
    u32.PostMessageW(hwnd, WM_COMMAND, MAKEWPARAM(cid, BN_CLICKED), ctypes.c_void_p(child_by_id(hwnd, cid) or 0))


def set_text(hwnd, cid, text):
    h = child_by_id(hwnd, cid)
    if h:
        u32.SendMessageW(h, WM_SETTEXT, 0, ctypes.c_wchar_p(text))
    return bool(h)


def get_text(hwnd, cid):
    h = child_by_id(hwnd, cid)
    if not h:
        return ''
    n = u32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 2)
    u32.GetWindowTextW(h, b, n + 2)
    return b.value


def keep_foreground(pid):
    """把前台还给原来的窗口（它启动时会抢一下）。"""
    try:
        fg = u32.GetForegroundWindow()
        t = k32.GetWindowThreadProcessId(fg, None)
        me = k32.GetCurrentThreadId()
        tgt = u32.GetWindowThreadProcessId(u32.FindWindowW(None, None), None)
        u32.AttachThreadInput(me, u32.GetWindowThreadProcessId(fg, None), True)
        u32.SetForegroundWindow(fg)
        u32.AttachThreadInput(me, u32.GetWindowThreadProcessId(fg, None), False)
    except Exception:
        pass


# ---------------------------------------------------------------- 主流程
def stage_book(book_dir, log=print):
    """把书拷到一个又短又纯 ASCII 的临时目录。

    Pdg2Pic 是 2000 年代的 MFC 程序：路径太长/含中文、全角括号、空格时，
    它的选目录对话框容易报「您所指定的文件夹无效」。所以先搬到短路径再交给它。
    """
    import random
    import string
    import tempfile
    root = os.path.join(tempfile.gettempdir(), 'pdgw')
    os.makedirs(root, exist_ok=True)
    while True:
        dst = os.path.join(root, 'b' + ''.join(random.choice(string.ascii_lowercase + string.digits)
                                               for _ in range(8)))
        if not os.path.exists(dst):
            break
    shutil.copytree(book_dir, dst)
    n = sum(1 for f in os.listdir(dst) if f.lower().endswith('.pdg'))
    log('暂存：%s（%d 个 .pdg，路径长 %d）' % (dst, n, len(dst)))
    return dst, n


def _same_path(a, b):
    try:
        return os.path.normcase(os.path.abspath(a.strip().rstrip('\\'))) == \
               os.path.normcase(os.path.abspath(b))
    except Exception:
        return False


WM_DROPFILES = 0x0233
GWL_EXSTYLE = -20
WS_EX_ACCEPTFILES = 0x00000010


def _mk_hdrop(path):
    """造一个 HDROP 内存块（句柄式，32/64 位都能跨进程传）。"""
    import struct
    data = struct.pack('<IiiII', 20, 0, 0, 0, 1) + path.encode('utf-16-le') + b'\x00\x00\x00\x00'
    h = k32.GlobalAlloc(0x0002, len(data))          # GMEM_MOVEABLE
    p = k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    return h


def _drop_folder(hwnd, folder, log):
    """把文件夹「拖」进 Pdg2Pic 主窗口 —— 相当于第一步的手工选目录，但不用开对话框。

    为什么不用它自己的「选择文件夹」对话框：那是老式 MFC 控件，跨进程带指针的消息
    （WM_SETTEXT/WM_GETTEXT）在 32 位程序 ↔ 64 位 Python 之间根本传不过去，
    时灵时不灵（就是那句「您所指定的文件夹无效」的由来）。拖放走的是句柄，稳。
    """
    if not (u32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_ACCEPTFILES):
        return False
    for i in range(1, 6):
        u32.PostMessageW(hwnd, WM_DROPFILES, ctypes.c_void_p(_mk_hdrop(folder)), 0)
        time.sleep(0.9)
        shown = get_text(hwnd, 1011)
        if shown and _same_path(shown, folder):
            log('目录已设上（拖入第 %d 次）：%s' % (i, shown))
            return True
        log('拖入第 %d 次后显示 %r' % (i, shown))
    return False


def _wait_child(hwnd, cid, timeout=15):
    """等某个子控件出现（Pdg2Pic 刚启动时控件还没建好）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = child_by_id(hwnd, cid)
        if h and u32.IsWindowVisible(h) and u32.IsWindowEnabled(h):
            return h
        time.sleep(0.25)
    return child_by_id(hwnd, cid)


def _set_text_typed(hwnd, cid, text):
    """逐字输入（模拟人打字）：比 WM_SETTEXT 对老对话框更管用。"""
    h = child_by_id(hwnd, cid)
    if not h:
        return False
    u32.SendMessageW(h, 0x0007, 0, 0)                   # WM_SETFOCUS
    u32.SendMessageW(h, 0x000B, 0, 0)                   # WM_SETREDRAW off，少闪烁
    u32.SendMessageW(h, 0x00B1, 0, -1)                  # EM_SETSEL 0,-1 全选
    u32.SendMessageW(h, 0x00C2, 0, 0)                   # EM_REPLACESEL 清空
    for ch in text:
        u32.SendMessageW(h, 0x0102, ord(ch), 0)         # WM_CHAR
    u32.SendMessageW(h, 0x000B, 1, 0)                   # WM_SETREDRAW on
    u32.SendMessageW(h, 0x00F5, 0, 0)                   # 让控件刷新（无效消息也行）
    return get_text(hwnd, cid).strip() == text


def _set_text_clip(hwnd, cid, text):
    """剪贴板粘贴（第三种保险）。"""
    h = child_by_id(hwnd, cid)
    if not h:
        return False
    try:
        if not u32.OpenClipboard(h):
            return False
        try:
            u32.EmptyClipboard()
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            n = (len(text) + 1) * 2
            k32.GlobalAlloc.restype = ctypes.c_void_p
            k32.GlobalLock.restype = ctypes.c_void_p
            hm = k32.GlobalAlloc(GMEM_MOVEABLE, n)
            if not hm:
                return False
            ptr = k32.GlobalLock(hm)
            ctypes.memmove(ptr, ctypes.create_unicode_buffer(text), n)
            k32.GlobalUnlock(hm)
            u32.SetClipboardData(CF_UNICODETEXT, ctypes.c_void_p(hm))
        finally:
            u32.CloseClipboard()
        u32.SendMessageW(h, 0x0007, 0, 0)               # WM_SETFOCUS
        u32.SendMessageW(h, 0x00B1, 0, -1)              # EM_SETSEL 全选
        u32.SendMessageW(h, 0x0302, 0, 0)               # WM_PASTE
        return get_text(hwnd, cid).strip() == text
    except Exception:
        return False


def _fill_dialog(dlg, src, log, tries=16):
    """把路径填进「选择文件夹」对话框的输入框。

    老 MFC 对话框很挑：有时候 WM_SETTEXT 根本不生效。所以三种写法轮着试
    （直接设文本 / 逐字输入 / 剪贴板粘贴），每次都读回来核对；确认填进去了、
    且「确定」可点，才点确定。
    """
    methods = (('WM_SETTEXT', lambda: (u32.SendMessageW(child_by_id(dlg, 14148) or dlg, WM_SETTEXT, 0,
                                                         ctypes.c_wchar_p(src)),
                                       get_text(dlg, 14148).strip() == src)[1]),
               ('逐字输入', lambda: _set_text_typed(dlg, 14148, src)),
               ('剪贴板粘贴', lambda: _set_text_clip(dlg, 14148, src)))
    for i in range(tries):
        if not u32.IsWindow(dlg):
            return False
        if child_by_id(dlg, 14148):
            for name, fn in methods:
                if not u32.IsWindow(dlg):
                    return False
                try:
                    if fn():
                        okb = child_by_id(dlg, 1)
                        if (okb and u32.IsWindowEnabled(okb)) or i >= 6:
                            post_click(dlg, 1)
                            log('  （用「%s」把路径填进去了）' % name)
                            return True
                except Exception:
                    pass
        time.sleep(0.35)
    return False


def _ensure_folder(hwnd, src, log, attempts=4):
    """把「已选目录」设成 src；每次都读回来核对。"""
    for a in range(1, attempts + 1):
        post_click(hwnd, 1000)
        dlg, _, _ = find_window('选择存放PDG文件的文件夹', timeout=15)
        if not dlg:
            log('第 %d 次：浏览对话框没出来，等 1 秒再来' % a)
            time.sleep(1.0)
            continue
        filled = _fill_dialog(dlg, src, log)
        t0 = time.time()
        while time.time() - t0 < 6:
            if not u32.IsWindow(dlg):
                break
            time.sleep(0.2)
        if u32.IsWindow(dlg):
            post_click(dlg, 2)                        # 取消，重来
            time.sleep(0.5)
        shown = get_text(hwnd, 1011)
        if shown and _same_path(shown, src):
            log('第 %d 次：目录已设上（%s）' % (a, shown))
            return True
        log('第 %d 次：目录没设上（显示 %r ｜ 填入成功=%s）' % (a, shown, filled))
    return False



def _dismiss_all(before, hwnd, log=None):
    """把新冒出来的对话框统统按掉（完成提示 / 错误提示）。"""
    n = 0
    for h, c, t in enum_windows():
        if c != '#32770' or t in before or t in ('Pdg2Pic',) or h == hwnd:
            continue
        btns = child_windows(h)
        target = None
        for key in ('确定', 'OK', '是'):
            for b in btns:
                if b[1] == 'Button' and key in b[2]:
                    target = b
                    break
            if target:
                break
        if target is None:
            for b in btns:
                if b[1] == 'Button':
                    target = b
                    break
        if target:
            u32.PostMessageW(target[0], 0x00F5, 0, 0)      # BM_CLICK
            n += 1
            if log:
                log('  → 清掉弹窗「%s」（按 %s）' % (t, target[2]))
    return n


def convert_book(book_dir, out_dir, exe=DEFAULT_EXE, a4=True, log=print, timeout=3600,
                 extra_launch_wait=2.5, keep=False):
    """把一本书交给 Pdg2Pic 转 PDF；返回 dict。不修改任何 ini。

    选目录不成功时会关掉 Pdg2Pic 重开再试（最多 3 轮）——它在"刚启动"那几秒最不稳。
    """
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.basename(os.path.normpath(book_dir))
    src, npdg = stage_book(book_dir, log=log)
    if npdg == 0:
        raise RuntimeError('这本的书目录里没有 .pdg 文件：%s' % book_dir)
    work = os.path.dirname(src)          # Pdg2Pic 把 PDF 写在书目录的上一级
    made_copy = True
    last_err = ''

    for relaunch in range(1, 4):
        if relaunch > 1:
            log('第 %d 轮：关掉 Pdg2Pic 重开再试' % relaunch)
        before = set(t for _, _, t in enum_windows())
        prev_fg = u32.GetForegroundWindow()
        proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        time.sleep(extra_launch_wait)
        try:
            if prev_fg:
                u32.SetForegroundWindow(prev_fg)
        except Exception:
            pass

        hwnd, _, ttl = find_window('Pdg2Pic', timeout=30)
        if not hwnd:
            last_err = '找不到 Pdg2Pic 主窗口'
            try:
                proc.kill()
            except Exception:
                pass
            continue
        log('主窗口：%s' % ttl)
        keep_foreground(proc.pid)
        try:
            if prev_fg:
                u32.SetForegroundWindow(prev_fg)
        except Exception:
            pass
        _wait_child(hwnd, 1000, timeout=15)            # 等「浏览」按钮可用

        # 1) 设目录：优先「拖进去」（稳、不抢焦点），不行才走它的对话框
        if not (_drop_folder(hwnd, src, log) or _ensure_folder(hwnd, src, log)):
            last_err = '选不上目录'
            try:
                u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                time.sleep(0.8)
                if u32.IsWindow(hwnd):
                    proc.kill()
            except Exception:
                pass
            time.sleep(1.0)
            continue
        post_click(hwnd, 1)                            # 2) 开始转换
        log('已发「开始转换」')

        # 3) 等完成：弹窗优先，兜底看产物大小稳定
        pdf = os.path.join(work, os.path.basename(src) + '.pdf')
        done_by, dir_error = '', ''
        seen_titles = set()
        t0 = time.time()
        last_size, last_t = -1, time.time()
        while time.time() - t0 < timeout:
            for h, c, t in enum_windows():
                if c == '#32770' and t not in before and t not in ('Pdg2Pic',) and h != hwnd:
                    if t not in seen_titles:
                        seen_titles.add(t)
                        log('弹窗：「%s」' % t)
                        if any(k in t for k in ('无效', '错误', '失败', '不存在')):
                            dir_error = t
                    yes = [b for b in child_windows(h)
                           if b[1] == 'Button' and ('否' in b[2] or 'No' in b[2] or '取消' in b[2])]
                    okb = [b for b in child_windows(h) if b[1] == 'Button'
                           and ('确定' in b[2] or '是' in b[2] or 'OK' in b[2])]
                    if '错误' in t or '报告' in t:
                        if yes:
                            u32.PostMessageW(yes[0][0], 0x00F5, 0, 0)
                            log('  → 按了「%s」（不看报告）' % yes[0][2])
                        elif okb:
                            u32.PostMessageW(okb[0][0], 0x00F5, 0, 0)
                    else:
                        if okb:
                            u32.PostMessageW(okb[0][0], 0x00F5, 0, 0)
                            log('  → 按了「%s」' % okb[0][2])
                        elif yes:
                            u32.PostMessageW(yes[0][0], 0x00F5, 0, 0)
                    time.sleep(0.5)
            st = get_text(hwnd, 1003)
            if os.path.exists(pdf):
                s = os.path.getsize(pdf)
                if s != last_size:
                    last_size, last_t = s, time.time()
                elif s > 0 and time.time() - last_t > 6:
                    done_by = '产物大小稳定（状态：%s）' % st
                    break
            if dir_error:                              # 它直接报目录无效 → 关掉重来
                break
            time.sleep(0.6)
        log('结束判定：%s%s' % (done_by or '未完成', ('｜' + dir_error) if dir_error else ''))

        # 4) 关窗口：先把弹窗清干净，再温和关闭，1.5 秒还不走就强杀
        #    （之前只发 WM_CLOSE：若是模态"转换完毕"弹窗挂着，它能挂很久不动）
        for _ in range(3):
            _dismiss_all(before, hwnd, log)
            time.sleep(0.3)
        try:
            u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
        t0 = time.time()
        while time.time() - t0 < 1.5:
            if not u32.IsWindow(hwnd):
                break
            time.sleep(0.2)
        if u32.IsWindow(hwnd):
            _dismiss_all(before, hwnd, None)
            try:
                proc.kill()
            except Exception:
                pass
        time.sleep(0.2)

        if dir_error and not os.path.exists(pdf):
            last_err = '它报「%s」' % dir_error
            time.sleep(1.0)
            continue                                    # 重开再试一轮

        # 5) 读它的错误日志
        err = ''
        lg = os.path.join(os.path.dirname(exe), 'Pdg2Pic_log.txt')
        if os.path.exists(lg):
            try:
                raw = open(lg, 'rb').read()
                for enc in ('utf-16', 'utf-8', 'gbk'):
                    try:
                        err = raw.decode(enc)
                        break
                    except Exception:
                        continue
            except Exception:
                pass

        res = {'pdf': pdf if os.path.exists(pdf) else None, 'log': err[-4000:], 'dir': src,
               'done_by': done_by, 'error_log': err, 'dir_error': dir_error,
               'popups': sorted(seen_titles)}
        if not res['pdf'] and dir_error:
            res['note'] = 'Pdg2Pic 报「%s」' % dir_error
        if res['pdf']:
            import fitz
            d = fitz.open(res['pdf'])
            res['pages'] = d.page_count
            res['page_size'] = (round(d[0].rect.width), round(d[0].rect.height))
            d.close()
            final = os.path.join(out_dir, base + '.pdf')
            if os.path.abspath(res['pdf']) != os.path.abspath(final):
                shutil.move(res['pdf'], final)
                res['pdf'] = final
            if a4:
                a4out = final[:-4] + '_A4.pdf'
                st = C.relayout(final, a4out, mode='auto')
                res['a4'] = st['out']
                res['a4_size'] = st['size']
                res['a4_sizes'] = sorted(st['sizes'])[:3]
        if made_copy and not keep:
            shutil.rmtree(work, ignore_errors=True)
        if res['pdf']:
            return res
        last_err = last_err or '没产出 PDF'
    shutil.rmtree(work, ignore_errors=True)
    if made_copy and keep:
        pass
    raise RuntimeError('Pdg2Pic 试了 3 轮都没成功（%s）。若反复出现，请把书放到短路径再试。'
                       % (last_err or '未知原因'))


def _selftest():
    """不真的启动外部程序，只做纯逻辑自检。"""
    ok = True
    lines = ['CathayPDG 外挂模块自检']
    # 选书目录：优先「需外部」的样本
    cands = []
    for top in sorted(os.listdir('D:\\_pdg_test')):
        p = os.path.join('D:\\_pdg_test', top)
        if not os.path.isdir(p):
            continue
        for dp, dns, fns in os.walk(p):
            if any(f.lower().endswith('.pdg') for f in fns):
                cands.append(dp)
                dns[:] = []
    need = [c for c in cands if not C.scan_book(c)['can_self']]
    lines.append('存在需外部的样本：%s' % bool(need))
    # 按钮/控件编号约定（来自实测控件表）
    lines.append('控件约定：浏览=1000 确定=1 目录显示=1011 状态=1003 选择框Edit=14148')
    txt = '\n'.join(lines)
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_selftest_external.txt'),
         'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    return 0


def main(argv):
    if '--selftest' in argv:
        return _selftest()
    if '--run' in argv:
        i = argv.index('--run')
        book, outd = argv[i + 1], argv[i + 2]
        exe = argv[argv.index('--exe') + 1] if '--exe' in argv else DEFAULT_EXE
        res = convert_book(book, outd, exe=exe, a4=('--no-a4' not in argv))
        print('PDF: %s' % res['pdf'])
        print('页数: %s ｜ 页尺寸: %s' % (res.get('pages'), res.get('page_size')))
        print('A4: %s (%.1f MB)' % (res.get('a4'), (res.get('a4_size') or 0) / 1e6))
        print('结束判定: %s' % res['done_by'])
        if res.get('error_log'):
            print('它的日志尾部:\n%s' % res['error_log'][-1200:])
        return 0 if res['pdf'] else 1
    print(__doc__)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
