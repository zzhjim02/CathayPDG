# -*- coding: utf-8 -*-
"""
CathayPDG 图形界面（tkinter）：拖入目录 → 批量转换 → 进度/日志/报告。

用法：py -3 gui.py        或双击 启动.bat
自检：py -3 gui.py --selftest
"""
import io
import json
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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

# tkinterdnd2（可选：拖放）
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    DND_FILES, TkinterDnD, HAS_DND = None, None, False

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pdg_batch as B
import pdg_core as C
import pdg_external as X

APP_TITLE = 'CathayPDG · 超星 PDG 批量转换工具'
APP_VERSION = 'v0.1.9'
SPIN = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'      # 处理中转圈的那一下，告诉用户没卡死
COLS = [('src', '来源 / 书名', 300), ('pages', '页数', 60), ('mode', '方式', 70),
        ('ok', '结果', 60), ('secs', '耗时', 70), ('note', '备注', 420)]


def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return HERE


def res_dir():
    return getattr(sys, '_MEIPASS', None) or app_dir()


def icon_path():
    for p in (os.path.join(res_dir(), 'app.ico'), os.path.join(app_dir(), 'app.ico')):
        if os.path.exists(p):
            return p
    return ''


def settings_path():
    return os.path.join(app_dir(), 'cathaypdg_settings.json')


def load_settings():
    d = {'in_dir': '', 'out_dir': '', 'pw': os.path.join(app_dir(), 'config', 'passwords.txt'),
         'archive': True, 'force': False, 'keep_unpacked': True, 'pdg2pic': '',
         'popup_done': False}
    try:
        d.update(json.load(open(settings_path(), encoding='utf-8')))
    except Exception:
        pass
    if not os.path.exists(d['pw']):
        d['pw'] = os.path.join(res_dir(), 'config', 'passwords.txt')
    return d


def save_settings(d):
    try:
        json.dump(d, open(settings_path(), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception:
        pass


def split_drop(data):
    """解析 tkdnd 拖放串（支持 {带空格的路径}）。"""
    out, cur, ine = [], '', False
    for ch in str(data):
        if ch == '{':
            ine = True
        elif ch == '}':
            ine = False
            if cur:
                out.append(cur)
            cur = ''
        elif ch == ' ' and not ine:
            if cur:
                out.append(cur)
            cur = ''
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------- 任务栏提醒（不抢焦点）
def _flash(hwnd, flags):
    """Windows：让任务栏图标闪；flags=0 表示停止。失败就静默跳过。"""
    if sys.platform != 'win32' or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('hwnd', wintypes.HWND),
                        ('dwFlags', wintypes.DWORD), ('uCount', wintypes.UINT),
                        ('dwTimeout', wintypes.DWORD)]

        fi = FLASHWINFO()
        fi.cbSize = ctypes.sizeof(fi)
        fi.hwnd = wintypes.HWND(hwnd)
        fi.dwFlags = flags
        fi.uCount = 0
        fi.dwTimeout = 0
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
        return True
    except Exception:
        return False


FLASH_TRAY = 0x00000002          # 只闪任务栏图标
FLASH_TIMERNOFG = 0x0000000C     # 一直闪到窗口回到前台
FLASH_STOP = 0x00000000


def flash_taskbar(root):
    """转换完了：任务栏闪 + 标题加标记，**不弹窗、不抢焦点**。"""
    try:
        root.update_idletasks()
        hwnd = int(root.winfo_id(), 0) if str(root.winfo_id()).startswith('0x') \
            else int(root.winfo_id())
        if not _flash(hwnd, FLASH_TRAY | FLASH_TIMERNOFG):
            _flash(hwnd, FLASH_TRAY)
    except Exception:
        pass


def stop_flash(root):
    try:
        hwnd = int(root.winfo_id(), 0) if str(root.winfo_id()).startswith('0x') \
            else int(root.winfo_id())
        _flash(hwnd, FLASH_STOP)
    except Exception:
        pass


def find_pdg2pic():
    """找 Pdg2Pic.exe：先看配套目录，再扫常见位置。"""
    # 新版打包：配套程序都收在 程序组件\ 里
    for cand in (os.path.join(app_dir(), '程序组件', 'Pdg2Pic', 'Pdg2Pic.exe'),
                 os.path.join(app_dir(), '程序组件', 'Pdg2Pic.exe')):
        if os.path.isfile(cand):
            return cand
    import glob
    cands = [X.DEFAULT_EXE,
             r'C:\Program Files\Pdg2Pic\Pdg2Pic.exe',
             r'D:\Program Files\Pdg2Pic\Pdg2Pic.exe']
    for c in cands:
        if os.path.exists(c):
            return c
    for pat in (r'?:\Program Files*\*Pdg2Pic*\Pdg2Pic.exe',
                r'?:\*Pdg2Pic*\Pdg2Pic.exe'):
        g = glob.glob(pat)
        if g:
            return g[0]
    return X.DEFAULT_EXE


class App:
    def __init__(self):
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.base_title = '%s %s' % (APP_TITLE, APP_VERSION)
        self.root.title(self.base_title)
        try:
            if icon_path():
                self.root.iconbitmap(icon_path())
        except Exception:
            pass
        st = load_settings()
        self.in_dir = tk.StringVar(value=st['in_dir'])
        self.inputs = list(st.get('inputs') or [])
        if not self.inputs and st['in_dir']:
            self.inputs = [st['in_dir']]
        self.out_dir = tk.StringVar(value=st['out_dir'])
        self.pw = tk.StringVar(value=st['pw'])
        self.v_archive = tk.BooleanVar(value=bool(st['archive']))
        self.v_force = tk.BooleanVar(value=bool(st['force']))
        self.v_keep = tk.BooleanVar(value=bool(st['keep_unpacked']))
        # 默认 False：转完不弹窗，只在窗口里提示 + 任务栏闪，不打断你手头的事
        self.v_popup = tk.BooleanVar(value=bool(st.get('popup_done', False)))
        _exe = st.get('pdg2pic') or ''
        if _exe and not os.path.isfile(_exe):
            _exe = ''                     # 存的是旧路径（软件挪过位置）→ 重新探测
        self.pdg2pic = tk.StringVar(value=_exe or find_pdg2pic())
        self.q = queue.Queue()
        self.control = {'pause': False, 'stop': False}
        self.running = False
        self.recs = []
        # 处理中实时状态：第几本 / 共几本 / 书名 / 当前这一步在干嘛 / 这本起跑时刻
        self.busy = {'i': 0, 'n': 0, 'name': '', 'stage': '', 't0': 0.0}
        self.spin = 0
        self.build()
        if HAS_DND:
            for w in (self.root,):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind('<<Drop>>', self.on_drop)
                except Exception:
                    pass
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.root.bind('<FocusIn>', self.on_focus_in)
        self.root.after(120, self.pump)

    def on_focus_in(self, _e=None):
        """窗口回到前台：撤掉完成标记和任务栏闪烁。"""
        if getattr(self, '_done_mark', ''):
            self._done_mark = ''
            self.root.title(self.base_title)
            stop_flash(self.root)

    # ---------------------------------------------------------------- 界面
    def build(self):
        pad = dict(padx=6, pady=3)
        top = ttk.LabelFrame(self.root, text='① 目录（可直接把文件夹拖进窗口）')
        top.pack(fill='x', **pad)
        r = ttk.Frame(top)
        r.pack(fill='x', padx=4, pady=2)
        ttk.Label(r, text='输入', width=8).pack(side='left')
        ttk.Entry(r, textvariable=self.in_dir).pack(side='left', fill='x', expand=True)
        ttk.Button(r, text='选文件…', width=8, command=self.pick_files).pack(side='left', padx=2)
        ttk.Button(r, text='选文件夹…', width=10, command=self.pick_dirs).pack(side='left', padx=2)
        ttk.Button(r, text='清空', width=6, command=self.clear_inputs).pack(side='left', padx=2)
        ttk.Label(top, text='可一次选多个文件 / 多个文件夹，也可以把它们一起拖进窗口。',
                  foreground='#666').pack(anchor='w', padx=12)
        r = ttk.Frame(top)
        r.pack(fill='x', padx=4, pady=2)
        ttk.Label(r, text='输出目录', width=8).pack(side='left')
        ttk.Label(r, text='（留空＝成品直接放回输入目录）', foreground='#666').pack(side='left')
        ttk.Entry(r, textvariable=self.out_dir).pack(side='left', fill='x', expand=True)
        ttk.Button(r, text='选择…', width=8, command=lambda: self.pick('out')).pack(side='left', padx=3)
        ttk.Button(r, text='清空', width=6, command=self.clear_out).pack(side='left')
        r = ttk.Frame(top)
        r.pack(fill='x', padx=4, pady=2)
        ttk.Label(r, text='密码本', width=8).pack(side='left')
        ttk.Entry(r, textvariable=self.pw).pack(side='left', fill='x', expand=True)
        ttk.Button(r, text='选择…', width=8, command=lambda: self.pick('pw')).pack(side='left', padx=3)
        r = ttk.Frame(top)
        r.pack(fill='x', padx=4, pady=2)
        ttk.Label(r, text='Pdg2Pic', width=8).pack(side='left')
        ttk.Entry(r, textvariable=self.pdg2pic).pack(side='left', fill='x', expand=True)
        ttk.Button(r, text='选择…', width=8,
                   command=self.pick_exe).pack(side='left', padx=3)
        r = ttk.Frame(top)
        r.pack(fill='x', padx=4, pady=2)
        ttk.Checkbutton(r, text='处理完归档：成功的进 已处理\\，失败的进 处理失败\\', variable=self.v_archive).pack(side='left')
        ttk.Checkbutton(r, text='强制重转（忽略已有同名 PDF）', variable=self.v_force).pack(side='left', padx=10)
        ttk.Checkbutton(r, text='保留解压目录', variable=self.v_keep).pack(side='left', padx=10)
        ttk.Checkbutton(r, text='转完弹窗提醒（默认不弹，只在窗口里提示 + 任务栏闪）',
                        variable=self.v_popup).pack(side='left', padx=10)

        bar = ttk.Frame(self.root)
        bar.pack(fill='x', **pad)
        self.b_run = ttk.Button(bar, text='▶ 开始转换', command=self.start)
        self.b_run.pack(side='left')
        self.b_pause = ttk.Button(bar, text='暂停', command=self.toggle_pause, state='disabled')
        self.b_pause.pack(side='left', padx=4)
        self.b_stop = ttk.Button(bar, text='停止', command=self.stop, state='disabled')
        self.b_stop.pack(side='left', padx=4)
        ttk.Button(bar, text='打开输出目录', command=self.open_out).pack(side='left', padx=10)
        ttk.Button(bar, text='环境体检', command=self.show_deps).pack(side='left')
        # 两条进度条：长的是「第几本/共几本」，短的一直在动 —— 表示后台确实在干活
        self.pb = ttk.Progressbar(bar, mode='determinate', length=240)
        self.pb.pack(side='right', padx=6)
        self.pb2 = ttk.Progressbar(bar, mode='indeterminate', length=80)
        self.pb2.pack(side='right', padx=2)
        self.lb_stat = ttk.Label(self.root, text='就绪 ｜ 密码本 %d 条 ｜ %s'
                                 % (len(B.passwords()), '支持拖放' if HAS_DND else '装 tkinterdnd2 可拖放'))
        self.lb_stat.pack(fill='x', padx=8)
        self.lb_cur = ttk.Label(self.root, text='', foreground='#0b6')
        self.lb_cur.pack(fill='x', padx=8)

        mid = ttk.Frame(self.root)
        mid.pack(fill='both', expand=True, **pad)
        self.tree = ttk.Treeview(mid, columns=[c[0] for c in COLS], show='headings', height=12)
        for k, t, w in COLS:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor='w')
        self.tree.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(mid, orient='vertical', command=self.tree.yview)
        sb.pack(side='left', fill='y')
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure('bad', foreground='#b00')
        self.tree.tag_configure('skip', foreground='#888')

        logf = ttk.LabelFrame(self.root, text='日志')
        logf.pack(fill='both', expand=True, **pad)
        self.txt = tk.Text(logf, height=8, wrap='none')
        self.txt.pack(side='left', fill='both', expand=True)
        sb2 = ttk.Scrollbar(logf, orient='vertical', command=self.txt.yview)
        sb2.pack(side='left', fill='y')
        self.txt.configure(yscrollcommand=sb2.set)

    # ---------------------------------------------------------------- 事件
    def show_deps(self):
        """弹一张依赖体检表：缺什么、干什么用的、怎么补。"""
        import pdg_deps
        buf = io.StringIO()
        try:
            ok = pdg_deps.report(file=buf)
        except Exception as e:
            messagebox.showerror(APP_TITLE, '体检没跑起来：%s' % e)
            return
        txt = buf.getvalue()
        self.log(txt)
        win = tk.Toplevel(self.root)
        win.title('%s ｜ 环境体检' % (APP_TITLE + ' ' + APP_VERSION))
        win.geometry('760x420')
        try:
            win.iconbitmap(icon_path())
        except Exception:
            pass
        t = tk.Text(win, wrap='none', font=('Consolas', 10))
        t.pack(fill='both', expand=True, padx=8, pady=(8, 0))
        sb = ttk.Scrollbar(t)
        sb.pack(side='right', fill='y')
        t.configure(yscrollcommand=sb.set)
        sb.configure(command=t.yview)
        t.insert('1.0', txt)
        t.configure(state='disabled')
        tag = '√ 齐全，可以直接用。' if ok else '× 有必需项缺失，照上面的办法补一下。'
        ttk.Label(win, text=tag,
                  foreground='#060' if ok else '#b00').pack(pady=(2, 4))
        ttk.Button(win, text='复制全文', command=lambda: self._copy_text(txt)).pack(pady=(0, 8))

    @staticmethod
    def _copy_text(s):
        try:
            root_win = tk._default_root
            if root_win:
                root_win.clipboard_clear()
                root_win.clipboard_append(s)
        except Exception:
            pass

    def _sync_inputs(self):
        """把 inputs 列表写进输入框（太长就显示『共 N 项』）。"""
        if len(self.inputs) == 1:
            self.in_dir.set(self.inputs[0])
        elif self.inputs:
            self.in_dir.set('共 %d 项：%s …' % (len(self.inputs), os.path.basename(self.inputs[0])))
        else:
            self.in_dir.set('')
        self.sync_pw()

    def add_inputs(self, paths):
        n0 = len(self.inputs)
        for p in paths:
            p = os.path.abspath(p)
            if p not in self.inputs and (os.path.isdir(p) or os.path.isfile(p)):
                self.inputs.append(p)
        self._sync_inputs()
        if hasattr(self, 'sync_pw'):
            self.sync_pw()
        if len(self.inputs) > n0:
            self.log('加入 %d 项，共 %d 项' % (len(self.inputs) - n0, len(self.inputs)))

    def pick_files(self):
        ps = filedialog.askopenfilenames(title='选压缩包（可多选）',
                                         filetypes=[('压缩包', '*.zip *.uvz *.7z *.rar'),
                                                    ('全部', '*.*')])
        if ps:
            self.add_inputs(list(ps))

    def pick_dirs(self):
        ps = filedialog.askdirectory(title='选择一个文件夹（可重复添加多个）')
        if ps:
            self.add_inputs([ps])

    def clear_inputs(self):
        self.inputs = []
        self._sync_inputs()

    def clear_out(self):
        """清空输出目录：留空＝成品直接放回输入目录。"""
        self.out_dir.set('')
        try:
            self.lb_stat.configure(text='输出目录已清空：成品会直接放回输入目录')
        except Exception:
            pass

    def pick(self, kind):
        if kind == 'in':
            p = filedialog.askdirectory(title='选择输入目录（放压缩包或书目录）')
            if p:
                self.add_inputs([p])
        elif kind == 'out':
            p = filedialog.askdirectory(title='选择输出目录')
            if p:
                self.out_dir.set(p)
        else:
            p = filedialog.askopenfilename(title='选择密码本（每行一个密码）',
                                           filetypes=[('文本', '*.txt'), ('全部', '*.*')])
            if p:
                self.pw.set(p)

    def pick_exe(self):
        p = filedialog.askopenfilename(title='选择 Pdg2Pic.exe',
                                       filetypes=[('程序', '*.exe'), ('全部', '*.*')])
        if p:
            self.pdg2pic.set(p)

    def on_drop(self, ev):
        paths = split_drop(ev.data)
        if paths:
            self.add_inputs(paths)
        self.log('拖入：%s' % paths)

    def log(self, msg):
        self.q.put(('log', msg))

    def toggle_pause(self):
        self.control['pause'] = not self.control['pause']
        self.b_pause.configure(text='继续' if self.control['pause'] else '暂停')

    def stop(self):
        self.control['stop'] = True
        self.control['pause'] = False
        self.b_pause.configure(text='暂停')
        self.log('已请求停止（当前这本做完就停）')

    def on_close(self):
        if self.running:
            if not messagebox.askyesno('退出', '还在转换中，确定要退出吗？'):
                return
            self.control['stop'] = True
        save_settings({'in_dir': (self.inputs[0] if self.inputs else ''),
                       'inputs': self.inputs, 'out_dir': self.out_dir.get(),
                       'pw': self.pw.get(), 'archive': self.v_archive.get(),
                       'force': self.v_force.get(), 'keep_unpacked': self.v_keep.get(),
                       'pdg2pic': self.pdg2pic.get(), 'popup_done': self.v_popup.get()})
        self.root.destroy()

    def open_out(self):
        p = self.out_dir.get().strip()
        if not p and self.inputs:                 # 留空＝成品就在输入目录里
            p = self.inputs[0]
            p = p if os.path.isdir(p) else os.path.dirname(p)
        if p and os.path.isdir(p):
            os.startfile(p)
        else:
            messagebox.showinfo('提示', '输出目录还不存在（留空时成品就放在输入目录里）')

    # ---------------------------------------------------------------- 跑
    def start(self):
        if self.running:
            return
        inds = [p for p in (self.inputs or []) if os.path.exists(p)]
        if not inds:
            messagebox.showwarning('缺少输入', '请先选输入（可多选文件/文件夹，或直接拖进窗口）')
            return
        ind = inds[0]
        outd = self.out_dir.get().strip()
        if outd and os.path.isfile(outd):      # 误填成文件 → 用它的目录
            outd = os.path.dirname(outd)
            self.out_dir.set(outd)
        # 留空＝各回各家：成品直接放回各自的输入目录。不回填输入框，免得下次还带着旧值

        if outd and os.path.abspath(outd).startswith(os.path.abspath(ind)) and \
                os.path.basename(outd) in ('_已处理',):
            messagebox.showwarning('目录不对', '输出目录不能是 _已处理')
            return
        # 密码本先用起来
        if os.path.exists(self.pw.get()):
            B.PW_FILE = self.pw.get()
        self.control = {'pause': False, 'stop': False}
        self.running = True
        self.b_run.configure(state='disabled', text='处理中…')
        self.b_pause.configure(state='normal', text='暂停')
        self.b_stop.configure(state='normal')
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.recs = []
        self.pb.configure(value=0, maximum=100)
        self._done_mark = ''                    # 新一轮开始：撤掉上次的完成标记
        self.root.title(self.base_title)
        stop_flash(self.root)
        self.lb_stat.configure(foreground='')
        self.lb_cur.configure(text='', foreground='#0b6')
        self.pb2.start(12)                      # 短条一直动：后台在干活的视觉信号
        self.busy = {'i': 0, 'n': 0, 'name': '准备…', 'stage': '正在清点', 't0': time.time()}
        self.log('=' * 60)
        self.log('开始：%s → %s' % (ind, outd or '各输入目录（原地生成）'))
        threading.Thread(target=self.worker, args=(inds, outd), daemon=True).start()

    def worker(self, inds, outd):
        try:
            recs, summ = B.run_many(inds, outd or None, exe=self.pdg2pic.get() or X.DEFAULT_EXE,
                               archive=self.v_archive.get(),
                               force=self.v_force.get(), log=self.log,
                               progress=lambda i, n, nm: self.q.put(('cur', (i, n, nm))),
                               tick=lambda s: self.q.put(('tick', s)),
                               control=self.control)
            self.q.put(('done', (recs, summ, outd)))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.q.put(('fail', '%s: %s' % (type(e).__name__, e)))

    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == 'log':
                    self.txt.insert('end', str(payload) + '\n')
                    self.txt.see('end')
                elif kind == 'cur':
                    i, n, nm = payload
                    self.pb.configure(maximum=max(1, n), value=i)
                    self.busy.update({'i': i, 'n': n, 'name': str(nm)[:40],
                                      'stage': '开始', 't0': time.time()})
                elif kind == 'tick':
                    self.busy['stage'] = str(payload)[:60]
                elif kind == 'done':
                    self.finish(*payload)
                elif kind == 'fail':
                    # 同样不弹窗：写日志 + 状态栏红字 + 任务栏闪，你自己切回来看
                    self.log('出错：%s' % payload)
                    self.lb_stat.configure(text='出错：%s' % payload, foreground='#b00')
                    self.lb_cur.configure(text='❌ 出错了，详情看上面的日志', foreground='#b00')
                    self._done_mark = '❌ 出错了'
                    self.root.title('❌ 出错了 · %s' % self.base_title)
                    flash_taskbar(self.root)
                    self.reset()
        except queue.Empty:
            pass
        if self.running:
            self.beat()
        self.root.after(120, self.pump)

    def beat(self):
        """处理中每 120ms 刷一次状态行。

        一本要转几十秒，界面一直不动，用户会以为卡死 —— 这里给出
        「第几本 / 书名 / 正在做什么 / 这本已用多少秒」，并让短进度条一直跑。
        """
        b = self.busy
        self.spin = (self.spin + 1) % len(SPIN)
        parts = []
        if b['n']:
            parts.append('[%d/%d]' % (b['i'], b['n']))
        if b['name']:
            parts.append(b['name'])
        if b['stage']:
            parts.append(b['stage'])
        els = time.time() - b['t0'] if b['t0'] else 0.0
        self.lb_cur.configure(text='%s 正在处理 %s ｜ 这本已用 %.0f 秒'
                                   % (SPIN[self.spin], ' · '.join(parts) or '…', els))

    def finish(self, recs, summ, outd):
        self.recs = recs
        outd_show = outd or '各输入目录（成品原地生成）'
        for r in recs:
            tag = 'bad' if not r['ok'] else ('skip' if r.get('mode') == '跳过' else '')
            self.tree.insert('', 'end', values=(
                r.get('book', ''), r.get('pages', ''), r.get('mode', ''),
                '✅' if r['ok'] else '❌', '%.1fs' % r.get('secs', 0),
                str(r.get('note', ''))[:200]), tags=(tag,) if tag else ())
        bad = summ['fail']
        self.lb_stat.configure(
            text='完成：共 %d ｜ 成功 %d ｜ 失败 %d ｜ 自建 %d ｜ 外挂 %d ｜ 跳过 %d'
                 % (summ['total'], summ['ok'], bad, summ['self'], summ['external'], summ['skip']),
            foreground=('#b00' if bad else '#0a0'))

        # 结论写进日志 + 单独一行大字，不弹窗、不抢焦点
        self.log('=' * 60)
        if bad:
            self.log('转换结束：成功 %d 本，失败 %d 本' % (summ['ok'], bad))
            for r in recs:
                if not r['ok']:
                    self.log('  ✗ %s —— %s' % (r.get('book', ''), str(r.get('note', ''))[:120]))
            self.log('输出位置：%s' % outd_show)
            self.log('（失败的明细在上面的表格里，红字那几行）')
            self.lb_cur.configure(text='⚠️ 完成但有 %d 本失败 ｜ 成功 %d 本 ｜ 输出位置：%s'
                                       % (bad, summ['ok'], outd_show), foreground='#b60')
            mark = '⚠️ 完成（%d 本失败）' % bad
        else:
            self.log('转换结束：全部成功，共 %d 本' % summ['ok'])
            self.log('输出位置：%s' % outd_show)
            self.lb_cur.configure(text='✅ 全部完成：共 %d 本 ｜ 输出位置：%s'
                                       % (summ['ok'], outd_show), foreground='#0a0')
            mark = '✅ 转换完成（%d 本）' % summ['ok']
        self.reset()

        # 后台提醒：任务栏闪 + 标题加标记，等你切回来再看
        self._done_mark = mark
        self.root.title('%s · %s' % (mark, self.base_title))
        flash_taskbar(self.root)
        if self.v_popup.get():                       # 自己开了「弹窗提醒」才弹
            self.root.after(200, lambda: messagebox.showinfo(
                '转换完成', ('成功 %d 本，失败 %d 本。\n\n输出位置：%s'
                             % (summ['ok'], bad, outd_show))))

    def reset(self):
        self.running = False
        self.b_run.configure(state='normal', text='▶ 开始转换')
        self.b_pause.configure(state='disabled', text='暂停')
        self.b_stop.configure(state='disabled')
        try:
            self.pb2.stop()
        except Exception:
            pass


# ---------------------------------------------------------------- 自检
def selftest():
    os.environ.setdefault('QT_QPA_PLATFORM', '')      # 无（tkinter 不需要）
    lines = ['%s %s' % (APP_TITLE, APP_VERSION)]
    ok = True

    def chk(label, cond, extra=''):
        nonlocal ok
        lines.append('%s：%s%s' % (label, 'OK' if cond else 'FAIL', (' ' + str(extra)) if extra else ''))
        ok = ok and bool(cond)

    import tempfile
    from PIL import Image

    import pdg_deps
    miss = pdg_deps.missing_required()
    chk('依赖体检', not miss, '齐全' if not miss else ('缺：' + '、'.join(miss)))
    s7 = pdg_deps._find_7z()
    chk('7z 引擎（解 .7z/.rar 用）', bool(s7), s7 or B.sevenz_missing_hint())
    chk('Pdg2Pic 引擎', bool(pdg_deps._find_pdg2pic()),
        pdg_deps._find_pdg2pic() or '没找到')

    # 自检里所有弹窗改成桩（否则会等人点）
    _mb = (messagebox.askyesno, messagebox.showinfo, messagebox.showwarning, messagebox.showerror)
    pop = {'n': 0}

    def _count(*a, **k):
        pop['n'] += 1
        return None

    messagebox.askyesno = lambda *a, **k: False
    messagebox.showinfo = _count
    messagebox.showwarning = _count
    messagebox.showerror = _count
    tmp = tempfile.mkdtemp(prefix='pdggui_')
    try:
        bk = os.path.join(tmp, 'in', '样书')
        os.makedirs(bk)
        for nm in ('cov001.pdg', '000001.pdg', '000002.pdg'):
            Image.new('L', (2008, 3000), 205).save(os.path.join(bk, nm), 'JPEG', quality=80)
        app = App()
        app.root.withdraw()
        chk('界面构建', hasattr(app, 'tree') and hasattr(app, 'pb'))
        chk('拖放', True, 'tkinterdnd2 %s' % ('可用' if HAS_DND else '未装（可点选择）'))
        app.control = {'pause': False, 'stop': False}
        recs, summ = B.run(os.path.join(tmp, 'in'), os.path.join(tmp, 'out'),
                           archive=False, log=lambda *a, **k: None)
        chk('引擎批量', summ['fail'] == 0 and summ['ok'] >= 1, summ)
        app.recs = recs
        app.finish(recs, summ, os.path.join(tmp, 'out'))
        chk('表格填充', len(app.tree.get_children()) == len(recs), len(recs))
        chk('完成不弹窗（只后台提示）', pop['n'] == 0, '弹窗 %d 次' % pop['n'])
        chk('默认不开弹窗提醒', app.v_popup.get() is False)
        chk('完成标记落在标题栏', app._done_mark.startswith(('✅', '⚠️')), app._done_mark)
        chk('图标', bool(icon_path()), icon_path() or '缺失')
        chk('Pdg2Pic 路径', bool(app.pdg2pic.get()), app.pdg2pic.get())
        chk('密码本', len(B.passwords()) >= 300, '%d 条' % len(B.passwords()))
        chk('弹窗桩（不阻塞）', True, '自检里 askyesno 已换成 False')
        app.root.destroy()
    finally:
        (messagebox.askyesno, messagebox.showinfo, messagebox.showwarning,
         messagebox.showerror) = _mb
        shutil.rmtree(tmp, ignore_errors=True)

    lines.append('result = %s' % ('OK' if ok else 'FAIL'))
    txt = '\n'.join(lines)
    out = os.path.join(app_dir() if getattr(sys, 'frozen', False) else HERE, '_selftest_gui.txt')
    open(out, 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    return 0 if ok else 1


def cli(argv):
    """隐藏命令行：--cli <输入目录> [输出目录] [--force] [--no-archive]。

    输出目录可省：省了就＝直接放回输入目录（和界面上的默认一致）。
    """
    i = argv.index('--cli')
    ind = argv[i + 1]
    outd = None
    for k in range(i + 2, len(argv)):
        if not argv[k].startswith('--'):
            outd = argv[k]
            break
    logf = open(os.path.join(app_dir(), '_cli.log'), 'w', encoding='utf-8')

    def log(m):
        logf.write(str(m) + '\n')
        logf.flush()

    import tkinter  # noqa: F401  （有的环境需要先初始化）
    recs, summ = B.run(ind, outd, archive=('--no-archive' not in argv),
                       force=('--force' in argv), log=log)
    log('汇总：%s' % summ)
    logf.close()
    return 0 if summ['fail'] == 0 else 1


def main():
    if '--selftest' in sys.argv:
        return selftest()
    if '--check-deps' in sys.argv:
        import pdg_deps
        buf = io.StringIO()
        ok = pdg_deps.report(file=buf)
        txt = buf.getvalue()
        # 窗口版 exe 没有控制台，print 出去用户看不见 —— 落到 exe 旁边
        if getattr(sys, 'frozen', False) or sys.stdout is None:
            p = os.path.join(app_dir(), '_deps_check.txt')
            try:
                open(p, 'w', encoding='utf-8').write(txt)
                try:
                    messagebox.showinfo(APP_TITLE + ' ' + APP_VERSION,
                                        '体检报告已写到：\n%s' % p)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            sys.stdout.write(txt)
        return 0 if ok else 1
    if '--cli' in sys.argv:
        return cli(sys.argv)

    # 源码模式下可能连包都没装，先体检：缺必需项就说清楚，别让用户对着起不来的窗口发呆
    import pdg_deps
    try:
        miss = pdg_deps.missing_required()
    except Exception:
        miss = []
    if miss:
        msg = ('这几个必需的东西没装上，程序跑不起来：\n\n  %s\n\n%s\n\n'
               '用打包好的 exe 版不需要装这些（已经封在里面了）。'
               % ('\n  '.join(miss), pdg_deps.MISSING_INSTALL))
        try:
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showerror(APP_TITLE + ' ' + APP_VERSION, msg)
            _r.destroy()
        except Exception:
            try:
                sys.stderr.write(msg + '\n')
            except Exception:
                pass
        return 1

    app = App()
    app.root.geometry('1280x820')
    app.root.minsize(980, 620)
    app.root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
