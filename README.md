<div align="center">

# 🧩 CathayPDG

**超星 / 读秀 PDG 批量转换工具 —— 把压缩包里的 PDG 变成能看的 PDF**

![license](https://img.shields.io/badge/license-GPL--3.0-blue)
![platform](https://img.shields.io/badge/platform-Windows%2010%2B-lightgrey)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)

</div>

## 🔗 Cathay 人文社科工具链

> 🧭 主线一句话：**CathayIndex 建本地库 → CathayFinder 查书 → CathayPDG 把查到的书（读秀/超星 PDG）转成 PDF → CathayOCR 识别 → CathayShelf 著录归架 → CathayReader 双栏校勘。**

| 步骤 | 工具 | 功能 | 状态 |
|:---:|---|---|---|
| ① | [CathayIndex](https://github.com/zzhjim02/CathayIndex) | v1.0.0 | 把本地文件夹建成可检索的「本地文件库」 |
| ② | [CathayFinder](https://github.com/zzhjim02/CathayFinder) | v1.0.0 | 综合性图书检索引擎：11 个渠道精准查书（找 SSID / 找路径） |
| ③ | **CathayPDG（你在这里）** | v0.1.5 | 读秀/超星 **PDG 批量转 PDF**：解压解密、横竖排分柜（把查到的书变成 PDF） |
| ④ | [CathayOCR](https://github.com/zzhjim02/CathayOCR) | v1.2.4 | 扫描件 OCR，产出可搜索文字层 PDF |
| ⑤ | [CathayShelf](https://github.com/zzhjim02/CathayShelf) | v0.4.5 | 图书著录自动化整理（一 PDF 一夹、命名规范化） |
| ⑥ | [CathayReader](https://github.com/zzhjim02/CathayReader) | v1.0.0 | 双栏校勘阅读器 |

**备用软件（四个，按需取用）**

| 工具 | 什么时候用 |
|---|---|
| [CathayRepair](https://github.com/zzhjim02/CathayRepair) | ④ OCR 前：PDF 目录结构坏了先修一下 |
| [CathayRestore](https://github.com/zzhjim02/CathayRestore) | ④ 之后：把 OCR 的 TXT 写回成竖排可搜索文字层 |
| [CathayExtract](https://github.com/zzhjim02/CathayExtract) | ④ 的替代入口：已经有字层的双层 PDF，直接抽 TXT |
| [CathaySimplify](https://github.com/zzhjim02/CathaySimplify) | 繁简转换 / 编码规范化（功能已并入 ⑤ CathayShelf） |

## 📦 下载

| 方式 | 说明 |
|---|---|
| ✅ **GitHub Releases** | [CathayPDG v0.1.5](https://github.com/zzhjim02/CathayPDG/releases/tag/v0.1.5)（Assets 里直接下 exe） |
| 📥 百度网盘（密码 2026） | https://pan.baidu.com/s/1s59XzQ7UjXnD246YDX0ckQ?pwd=2026 |

包内包含：**主程序 exe** + `程序组件\`（Pdg2Pic 引擎、密码本、便携运行库、源码）。换电脑整个文件夹拷过去即可。

## ✨ 它做什么

读秀 / 超星的电子书常以 `.uvz` / `.zip` / `.rar` 打包，里面是 `.pdg` 页图。本工具把这一套流水线一次干完：

1. **找**：扫输入目录，认出压缩包和已解开的书目录（含嵌套 `书A\书A\001.pdg`）
2. **解**：`zip/uvz` 用 zipfile→pyzipper（支持 AES），`7z/rar` 调 7-Zip；密码本 308 条逐个试（只验前 3 页），单包失败不中断整批
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

**Q：换电脑？**
A：整个文件夹拷过去。Pdg2Pic 路径可在界面上重选（默认会去 `程序组件\` 和常见安装位置找）。

## 📄 许可

GPL-3.0。Pdg2Pic 为老马（stronghorse）开发的免费工具，随包仅作调用，版权归原作者。
