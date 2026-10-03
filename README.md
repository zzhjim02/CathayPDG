<div align="center">

# 🧩 CathayPDG

**超星 / 读秀 PDG 批量转换工具 —— 把压缩包里的 PDG 变成能看的 PDF**

![license](https://img.shields.io/badge/license-GPL--3.0-blue)
![platform](https://img.shields.io/badge/platform-Windows%2010%2B-lightgrey)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)

</div>

## 🔗 Cathay 人文社科工具链

| 步骤 | 工具 | 功能 | 状态 |
|:---:|---|---|---|
| **⓪** | **CathayPDG（你在这里）** | 读秀/超星 **PDG 批量转 PDF**：解压、解密、PDG→PDF、横竖排分柜 | v0.1.6 |
| ① | [CathayIndex](https://github.com/zzhjim02/CathayIndex) | 把本地文件夹建成可检索的「本地文件库」 | v1.0.0 |
| ② | [CathayFinder](https://github.com/zzhjim02/CathayFinder) | 综合性图书检索引擎：11 个渠道精准查书（找 SSID / 找路径） | v1.0.0 |
| ③ | [CathayOCR](https://github.com/zzhjim02/CathayOCR) | 扫描件 OCR，产出可搜索文字层 PDF | v1.2.4 |
| ④ | [CathayShelf](https://github.com/zzhjim02/CathayShelf) | 图书著录自动化整理（一 PDF 一夹、命名规范化） | v0.4.5 |
| ⑤ | [CathayReader](https://github.com/zzhjim02/CathayReader) | 双栏校勘阅读器 | v1.0.0 |

> 🧭 主线一句话：**CathayPDG 先把读秀/超星的 PDG 包变成 PDF → 再交给后面几步检索、识别、著录、校勘。**

**备用软件（四个，按需取用）**

| 工具 | 什么时候用 |
|---|---|
| [CathayRepair](https://github.com/zzhjim02/CathayRepair) | ③ OCR 前：PDF 目录结构坏了先修一下 |
| [CathayRestore](https://github.com/zzhjim02/CathayRestore) | ③ 之后：把 OCR 的 TXT 写回成竖排可搜索文字层 |
| [CathayExtract](https://github.com/zzhjim02/CathayExtract) | ③ 的替代入口：已经是有字层的双层 PDF，直接抽 TXT |
| [CathaySimplify](https://github.com/zzhjim02/CathaySimplify) | 繁简转换 / 编码规范化（功能已并入 ④ CathayShelf） |

## 📦 下载

| 方式 | 说明 |
|---|---|
| ✅ **完整便携包**（推荐，零依赖） | GitHub Releases 里的 `CathayPDG-v0.1.6-portable.zip` —— exe + 两个引擎 + 密码本，解压即用 |
| ✅ **只要主程序** | GitHub Releases 里的 `CathayPDG-v0.1.6.exe`（但要把它放进 Release 的便携包里用，见下） |
| 📥 百度网盘（密码 2026） | <待填：百度网盘分享链接> |

包内包含：**主程序 exe** + `程序组件\`（Pdg2Pic 引擎、7-Zip 解压引擎、密码本、便携运行库、源码）。换电脑整个文件夹拷过去即可。

## 📦 依赖 —— 新机器上什么都不用装

用 exe 的话**不需要装任何东西**：Python、依赖包、7-Zip 解压引擎全都跟包带着。

| 东西 | 用在哪 | 怎么解决的 |
|---|---|---|
| Python 运行环境 | 跑程序 | ⬛ 封进 exe（单文件） |
| `pillow` / `pymupdf` / `pyzipper` / `pycryptodome` | 看图、写 PDF、解 AES 加密 zip | ⬛ 封进 exe；源码模式用包里的便携 runtime（已装好） |
| `tkinterdnd2` | 把文件拖到窗口上 | ⬛ 同上（可选，缺了只是不能拖） |
| 7-Zip 解压引擎 | 解 `.7z` / `.rar` | ⬛ 随包 `程序组件\7-Zip\`（7-Zip 官方 LGPL 版） |
| Pdg2Pic 引擎 | 强加密 PDG 页 | ⬛ 随包 `程序组件\Pdg2Pic\` |
| 密码本 | 试压缩包密码 | ⬛ 随包 `程序组件\config\` |

> ⚠️ **别把 exe 单独拷走。** 它是单文件没错，但两个引擎（`7-Zip\`、`Pdg2Pic\`）是外面的文件夹 —— 只拎走 exe 的话，`.7z`/`.rar` 和强加密页就转不了了。整个文件夹一起拷。

### 想改源码 / 用自己的 Python？

- **省事**：双击 `启动.bat` —— 它会自动用包里的便携 runtime，依赖已经装在里面
- **用自己的 Python**：双击 `安装依赖.bat`（内部就是 `pip install -r requirements.txt`），需要 Python 3.10+
- **体检**：`gui.py --check-deps`，或双击 `pdg_deps.py` —— 列出缺什么、干什么用的、怎么补

```bash
pip install -r requirements.txt      # 四个包 + 可选拖放，几十 MB
python pdg_deps.py                   # 体检表：√ 齐全 / × 必需 / · 可选
```

## ✨ 它做什么

读秀 / 超星的电子书常以 `.uvz` / `.zip` / `.rar` 打包，里面是 `.pdg` 页图。本工具把这一套流水线一次干完：

1. **找**：扫输入目录，认出压缩包和已解开的书目录（含嵌套 `书A\书A\001.pdg`）
2. **解**：`zip/uvz` 用 zipfile→pyzipper（支持 AES），`7z/rar` 调 7-Zip；密码本 308 条逐个试（只验前 3 页），单包失败不中断整批。中文压缩包**自动识别文件名编码**（GBK / Big5 / UTF-8 / 日文 / 韩文，见下方 FAQ）
3. **转**：
   - 页是标准图片（JPG/PNG/BMP/GIF/TIFF/WebP，或带 `HH` 头的 PDG 容器）→ **自己合成 PDF**
   - `00H` 的 CCITT G4 黑白扫描 → 包成 TIFF 自解
   - 解不开的强加密（`AAH`/`AxH`/`6xH` 等）→ **整本交给 Pdg2Pic**（纯窗口消息驱动，**不抢鼠标键盘**，可照常干别的）
4. **排**：按投影法抽样投票判 **横排 / 竖排 / 横竖待识别**，成品 PDF 分开放
5. **归档**：成功的原件与中间产物进 `已处理\`，失败的进 `处理失败\`，并出一份「转换报告」CSV/MD

## 📖 输出布局

```
输入目录\（输出留空时就是这里）
├─ 横排\             判定为横排的成品 PDF
├─ 竖排\             判定为竖排的成品 PDF
├─ 横竖待识别\       成品有，但横竖判不出来
├─ 已处理\           这批成功的原始文件 + 中间产物
├─ 处理失败\         失败的源文件 + 中间产物
└─ 转换报告_日期.csv / .md
```

## 🚀 怎么用

1. 双击 `CathayPDG 超星PDG批量转换工具 x.y.z.exe`
2. 「输入」选压缩包或书目录（**可多选文件/文件夹，也可直接拖进窗口**）；「输出目录」**留空 = 成品放回输入目录**
3. 点「开始」

命令行（可选）：`CathayPDG.exe --cli <目录或文件>`

## ⚙️ 实现要点

- **页序**不是按文件名排的：`cov001 → bok001 → leg001 → fow001 → !00001 → 000001… → cov002`（封面→书名页→版权页→前言→目录→正文→封底），与 Pdg2Pic 成品逐页指纹比对验证过
- **清晰度**：源扫描件本身就是 300 DPI（如 2008×3000 px）；排 A4 后有效分辨率 ≥200 DPI 就**原样嵌入、零重编码**，只有 <200 DPI 才 Lanczos 放大（上限 5×）
- 强加密页的判定：`HH` 头 + 第 16 字节（0x0F）编码类；`00H` 未加密可直接解，`AAH` 等必须交厂商控件
- 全程 **不联网、不用 AI**

## ❓ FAQ

**Q：为什么有的书要调 Pdg2Pic，而且很慢？**
A：`AAH`/`AxH`/`6xH` 是超星定制强加密，公开资料没有可用密钥，只能由自带厂商控件的 Pdg2Pic 解。慢是它的锅（一本 200–350 页约 15–20 秒），我们在旁边等，不耽误你用键盘鼠标。

**Q：密码失败/文损坏怎么办？**
A：单本失败不影响整批；失败的源文件和中间产物都在 `处理失败\` 里，报告里有原因。密码本可自己加：`程序组件\config\passwords.txt`。

**Q：中文压缩包解压后名字是乱码（老版本留下的）怎么办？**
A：v0.1.6 起会**自动识别并修回**。zip 里只标了「是不是 UTF-8」，没标具体编码，大陆包多是 GBK、港澳台多是 Big5，以前一律按 cp437 解就成了乱码。现在按「UTF-8 标志位 → 窄字库锁定 → 严格 UTF-8 → GBK/Big5/日文/韩文打分择优」逐条判定；解压后还会再扫一遍，把已有的乱码名改回来。以前转坏的 PDF，再跑一次就能修。

**Q：`.7z` / `.rar` 解不开？**
A：以前要求你自己装 7-Zip（而且路径写死在 `C:\Program Files\7-Zip\7z.exe`，装在别处就哑火）。v0.1.6 起**包里自带**了一份解压引擎（`程序组件\7-Zip\`，7-Zip 官方 LGPL 版），不再要求你装任何东西。查找顺序：随包 → 系统装的 7-Zip → PATH。
RAR 只能解压、不能打包（格式限制），读秀常见的 zip/uvz 压根不用它。

**Q：换电脑？**
A：整个文件夹拷过去。Pdg2Pic 路径可在界面上重选（默认会去 `程序组件\` 和常见安装位置找）。**建议把设置里的 Pdg2Pic 路径留空**，这样它每次按 exe 所在目录自动找，挪过目录也不会失效。

**Q：怎么确认我这台机器缺不缺东西？**
A：双击 `pdg_deps.py`，或命令行 `gui.py --check-deps`。会列一张表：每个依赖的用途、是不是必需、缺了怎么补。用 exe 的话基本都是 √。

**Q：看不懂报错，咋回事？**
A：常见三类，都在报告里写明白了：
- `没找到可用的解压引擎…` → 你只拷走了 exe，把 `程序组件\` 一起拷过来（或直接下便携包）
- `Pdg2Pic.exe 找不到：…` → 同上
- `解压失败（密码本未命中…）` → 密码没试出来，往 `程序组件\config\passwords.txt` 里加一条再跑

## 📝 更新日志

### v0.1.6

**零依赖**：一台干净的机器上不需要装任何东西就能跑

- **随包内置 7-Zip 解压引擎**（`程序组件\7-Zip\`，官方 LGPL 版）：以前 `SEVENZ` 写死 `C:\Program Files\7-Zip\7z.exe`，装机在这儿之外就静默失败 —— 现在改成「随包 → 系统装的 → PATH」三级探测，`.7z`/`.rar` 不再依赖用户预装任何东西
- **依赖自检**：新增 `pdg_deps.py`（`gui.py --check-deps`），一张表列出依赖用途/是否必需/怎么补；源码模式启动时先体检，缺必需项直接弹提示而不是白屏
- **修好 `启动.bat` 的便携 runtime 路径**：它在 `开发\runtime` 找，实际在 `程序组件\runtime`（上一级）—— 没装 Python 的机器上双击它就废了
- **新增 `安装依赖.bat`**：给想用自己的 Python 跑源码的人（判 Python→补 pip→装 requirement→跑体检）
- **7z/rar 失败不再静默**：报可读原因（缺引擎 vs 密码没命中），并给出怎么补

**中文压缩包文件名多编码识别**：UTF-8 标志位 → 窄字库（gb2312/big5）锁定 → 严格 UTF-8 → GBK/Big5/cp932/euc_kr 按「常用字率」打分择优；修了 `orig_filename` 二次编码和 CP936 间隔号差异
- **乱码名兜底修复**：解压后自动扫描，把 cp437 乱码的目录/文件改名回中文（只动含特征字符且能解出汉字的名字）
- **Pdg2Pic 路径自愈**：设置里的 exe 不存在时自动重新探测；真找不到报可读提示，不再是 `FileNotFoundError`
- **解压安全**：逐项落盘替代 `extractall`，加目录穿越（`../`）防护
- **修好自检**：`pdg_batch --selftest` 按真实输出路径定位 PDF（原来硬找 `out\甲书.pdf`，但成品已按横竖排分柜）、归档目录改用常量、异常不再吞掉已跑出的结果
- **打包脚本**：`fab.py` / `CathayPDG.spec` / `打包EXE.bat` 的密码本路径修正为 `程序组件\config`，补 `fab.py` 缺失的 `import io`

### v0.1.5

- 首个发布版：解压解密、PDG→PDF、横竖排分柜、转换报告

## 📄 许可

GPL-3.0。

随包分发的第三方二进制，各自保持原许可（均为自由/开源软件，允许再分发）：

- **Pdg2Pic** —— 老马（stronghorse）开发的免费工具，随包仅作调用，版权归原作者
- **7-Zip**（`程序组件\7-Zip\`）—— Igor Pavlov，LGPL-2.1+；此处仅以官方原封版调用，许可全文见 `程序组件\7-Zip\LICENSE-7-Zip.txt`。注意：7-Zip 的 RAR **解压**模块有不得用于制作 RAR 打包器的附加条款，本项目只解压、不打包，符合该条款

Python 侧的依赖（pillow / pymupdf / pyzipper / pycryptodome / tkinterdnd2）在打包时按各自许可证一并封装，源码模式的清单见 `requirements.txt`。
