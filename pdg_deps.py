# -*- coding: utf-8 -*-
"""pdg_deps —— 跑之前先体检：缺什么、用处是什么、怎么补。

分两类东西：

① Python 包（pillow / pymupdf / pyzipper / pycryptodome / tkinterdnd2）
   用打包好的 exe 时已经全部封在里面，用户什么都不用装。
   只有改源码、拿自己的 Python 跑的人才需要装 —— requirements.txt 里有清单，
   或者直接跑 安装依赖.bat。

② 外部程序（7z 解压引擎 / Pdg2Pic 转换引擎）
   这俩没法封进单个 exe，所以随包放在 程序组件\\ 里带上。
   无论用 exe 还是源码都要检查，因为用户可能把 exe 单独拷走了。

用法：
    python pdg_deps.py            打印体检表
    from pdg_deps import check    拿结构化结果
"""

import os
import shutil
import subprocess
import sys

# (导入名, pip 包名, 用途, 是否必需)
PKG_SPECS = (
    ('PIL', 'pillow', '看图、放大、合成封面', True),
    ('fitz', 'pymupdf', '读写 PDF', True),
    ('pyzipper', 'pyzipper', '解 AES 加密压缩包（读秀加密包要靠它）', True),
    ('Crypto', 'pycryptodome', 'pyzipper 的加密后端', True),
    ('tkinterdnd2', 'tkinterdnd2', '把文件拖到窗口上（不影响正常使用）', False),
)

MISSING_INSTALL = '装依赖：pip install -r requirements.txt（或双击 安装依赖.bat）'


def _app_dir():
    """程序所在目录：冻结时是 exe 旁边，源码时是脚本目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def frozen():
    """是否跑在打包好的 exe 里（是的话 Python 包已封装，无需用户操心）。"""
    return bool(getattr(sys, 'frozen', False))


def _probe_pkg(mod):
    """试着导入一个包，返回 (是否可用, 版本串)。"""
    try:
        m = __import__(mod)
    except Exception:
        return False, ''
    v = getattr(m, '__version__', '')
    if not v:
        v = getattr(m, '__VERSION__', '')
    return True, str(v)


def _find_7z():
    ad = _app_dir()
    up1, up2 = os.path.dirname(ad), os.path.dirname(os.path.dirname(ad))
    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    # 从近到远找「程序组件\7-Zip\」：exe 在包根目录、exe 在子目录、源码开发模式三种摆法都覆盖
    for c in (os.path.join(ad, '程序组件', '7-Zip', '7z.exe'),
              os.path.join(ad, '程序组件', '7-Zip', '7za.exe'),
              os.path.join(up1, '程序组件', '7-Zip', '7z.exe'),
              os.path.join(up2, '程序组件', '7-Zip', '7z.exe'),
              os.path.join(ad, '程序组件', '7za.exe'),
              os.path.join(ad, '7z.exe'),
              os.path.join(pf, '7-Zip', '7z.exe'),
              os.path.join(pf86, '7-Zip', '7z.exe')):
        if os.path.isfile(c):
            return c
    for name in ('7z', '7za'):
        w = shutil.which(name)
        if w:
            return w
    return None


def _find_pdg2pic():
    ad = _app_dir()
    up1, up2 = os.path.dirname(ad), os.path.dirname(os.path.dirname(ad))
    for c in (os.path.join(ad, '程序组件', 'Pdg2Pic', 'Pdg2Pic.exe'),
              os.path.join(up1, '程序组件', 'Pdg2Pic', 'Pdg2Pic.exe'),
              os.path.join(up2, '程序组件', 'Pdg2Pic', 'Pdg2Pic.exe'),
              os.path.join(ad, '程序组件', 'Pdg2Pic.exe'),
              os.path.join(ad, 'Pdg2Pic.exe'),
              r'C:\Program Files\Pdg2Pic\Pdg2Pic.exe',
              r'D:\Program Files\Pdg2Pic\Pdg2Pic.exe'):
        if os.path.isfile(c):
            return c
    return None


def check():
    """全面体检。返回 list[dict]：每项含 name / role / ok / detail / fix。"""
    rows = []
    if frozen():
        rows.append({'kind': 'runtime', 'name': 'Python 运行环境', 'role': '打包版自带',
                     'ok': True, 'detail': '单文件 exe，已封装', 'fix': ''})
    else:
        try:
            import tkinter  # noqa: F401
            tk_ok = True
        except Exception:
            tk_ok = False
        rows.append({'kind': 'pkg', 'name': 'tkinter', 'role': '图形界面（Python 自带）',
                     'ok': tk_ok, 'detail': sys.version.split()[0],
                     'fix': '' if tk_ok else '重装 Python 时勾选 "tcl/tk and IDLE"'})
        for mod, pip, role, req in PKG_SPECS:
            ok, v = _probe_pkg(mod)
            rows.append({'kind': 'pkg', 'name': pip, 'role': role, 'ok': ok,
                         'detail': ('v' + v) if v else ('缺' if not ok else ''),
                         'fix': '' if ok else MISSING_INSTALL, 'required': req})

    s7 = _find_7z()
    rows.append({'kind': 'tool', 'name': '7z 解压引擎', 'role': '.7z / .rar 包要用',
                 'ok': bool(s7), 'detail': s7 or '没找到',
                 'fix': '' if s7 else '把整个文件夹解压出来用（包里自带 程序组件\\7-Zip\\），'
                                      '或装 7-Zip：https://www.7-zip.org/'})

    pdp = _find_pdg2pic()
    rows.append({'kind': 'tool', 'name': 'Pdg2Pic 转换引擎',
                 'role': '加密/特殊版式的 PDG 页要靠它转', 'ok': bool(pdp),
                 'detail': pdp or '没找到',
                 'fix': '' if pdp else '程序组件\\Pdg2Pic\\ 里有一份，别把 exe 单独拷出来'})
    return rows


def missing_required():
    """缺的必需项名字列表。空列表＝可以正常干活。"""
    out = []
    if not frozen():
        try:
            import tkinter  # noqa: F401
        except Exception:
            out.append('tkinter')
        for mod, pip, _role, req in PKG_SPECS:
            if not req:
                continue
            ok, _ = _probe_pkg(mod)
            if not ok:
                out.append(pip)
    return out


def _dw(s):
    """终端显示宽度：中日韩全角字符占两格，%-Ns 按字符数算会让表格歪掉。"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def _pad(s, n):
    return s + ' ' * max(0, n - _dw(s))


def report(file=None):
    """打印体检表到 file（默认 stdout）。返回是否全部通过。"""
    f = file or sys.stdout
    rows = check()
    miss_req = missing_required()

    def w(s=''):
        try:
            f.write(s + '\n')
        except Exception:
            pass

    w('=' * 62)
    w('  CathayPDG 运行环境体检')
    w('=' * 62)
    w('  Python : %s' % sys.version.split()[0])
    w('  模式   : %s' % ('打包 exe（依赖已封装）' if frozen() else '源码运行'))
    def _short(p):
        """路径太长会撑破表格，优先显示相对当前程序目录的写法。"""
        if len(p) <= 46:
            return p
        ad = _app_dir()
        try:
            rp = os.path.relpath(p, ad)
            if not rp.startswith('..'):
                return rp
        except Exception:
            pass
        return '…' + p[-45:]

    w('-' * 62)
    for r in rows:
        mark = '√' if r['ok'] else ('×' if r.get('required', True) else '·')
        detail = ('　' + _short(r['detail'])) if r['detail'] else ''
        w('  %-4s %s%s' % (mark, _pad(r['name'], 18), r['role'] + detail))
    bad = [r for r in rows if not r['ok']]
    if bad:
        w('-' * 62)
        w('  缺的 / 待处理：')
        for r in bad:
            who = '（必需）' if r.get('required', True) else '（可选，不影响转换）'
            w('    ● %s %s' % (r['name'], who))
            if r.get('fix'):
                w('      → %s' % r['fix'])
    w('=' * 62)
    if miss_req:
        w('  结论：缺必需项 %s，现在跑会出问题。' % '、'.join(miss_req))
    elif bad:
        w('  结论：能干活，上面标 ● 的是锦上添花的部分。')
    else:
        w('  结论：依赖齐全，可以直接用。')
    w('')
    return not miss_req


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ok = report()
    if os.name == 'nt' and not sys.argv[1:]:
        try:
            input('按回车关闭…')
        except Exception:
            pass
    sys.exit(0 if ok else 1)
