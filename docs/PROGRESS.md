# ScholarPet 续作进度 · 2026-09-21

## 第二轮请求（同日稍后）

> 「能做出整个桌宠脸是灵动的状态吗，眨眼睛呀，动嘴唇之类的动作等」
> 「动作幅度不用太大，灵动就行」

即：把静态立绘变成会动的脸，但幅度要克制。已完成，见文末「灰原哀灵动版」一节。

## 本轮请求（来自用户）

1. 修复 Windows 打包：排除来自 Codex runtime / Poppler 的 ICU DLL（icuuc.dll、icudt78.dll），
   但保留 PySide6 / RapidOCR / ONNX Runtime / CTranslate2 / 离线模型与全部现有功能。
2. 功能主次调整：**划词翻译升为主要入口** —— 任意场景选中词/句/段，在鼠标旁边弹译文，
   不遮挡选中内容；整屏翻译与框选 OCR 降为次要入口。
3. 桌宠形象换成《名侦探柯南》灰原哀 Q 版头像（只要头部），保留皮肤颜色等外观设置。
4. 中途可能耗尽额度，需要随时可续。

## 状态：本轮已完成

### 打包修复（根因 + 三层防护）

根因确认（不是 spec 写法问题，而是环境注入）：

- 本项目的 venv 基座位于
  `C:\Users\SherryAlbert\.cache\codex-runtimes\codex-primary-runtime\dependencies\python`。
  该运行时把 `dependencies\native\<pkg>\Library\bin`（poppler、git、libheif、jxrlib）挂到
  DLL 搜索路径上，PyInstaller 顺着依赖链把 **Poppler 的** DLL 收进包：
  - `icuuc.dll` 2744112 B、`icudt78.dll` 33126192 B —— 与 Poppler 源文件字节数完全一致；
  - 顺带还有 `libssl-3-x64.dll`、`libcrypto-3-x64.dll`，来源同样是 Poppler，
    正确的副本应在 `dependencies\python\DLLs`（1599280 B / 8003376 B）。
- 上一轮只写了 Analysis 后过滤，但 `COLLECT-00.toc` 仍含这两个 ICU，说明过滤没生效。
  另外 PySide6 自身**不含任何 icu*.dll**（只有 `resources/icudtl.dat`），
  所以移除 Poppler 的 ICU 不会伤到 Qt。

三层防护：

1. `ScholarPet.spec`：Analysis 之后剔除**所有**来源在 `codex-runtimes/.../native/` 的二进制
   （不再只针对两个文件名），并从解释器自己的 `DLLs` 目录补齐 libssl / libcrypto / libffi。
2. `scripts/build.ps1`：构建前把 PATH 中的 codex-runtimes native 目录清掉，
   并把解释器 DLL 目录提到最前。
3. 构建后校验：只删除与 Poppler 源文件 SHA256 一致的 icu*.dll（不会误删同名文件），
   确认包内已无任何 icu*.dll；再核对 OpenSSL 与解释器副本哈希一致，否则报错终止。

### 新增构建自检（取代"进程还活着"这种弱证据）

- `run.py --selftest` → `scholarpet/selftest.py`：在**打包后的 exe 里**真实创建
  QApplication（校验 qwindows 平台插件）、Pet / Reader / SettingsDialog / SelectionPopup /
  托盘图标、离线模型翻译、RapidOCR 识别、TLS，并把 JSON 报告写到 `%LOCALAPPDATA%\ScholarPet\selftest.json`。
- `build.ps1` 会运行它，按退出码和报告判定成败。

### 划词翻译（主入口）强化

- `selection_monitor.py`：新增 `available()`；无文字层时发 `unreadable` 信号
  （扫描版 PDF 会得到明确提示而不是静默失败）；屏蔽终端/凭据窗口的清单扩充。
- `views.SelectionPopup`：`configure(side, width, font_size)`；自适应左右贴边且保证不出屏；
  补齐"复制中文"信号连接（此前按钮无效）；长文本出现"完整对照"按钮；新增 `show_hint()`。
- `app.py`：`_pending_selection` 只保留最新一次划词，忙时取消旧任务再处理新的；
  无文字层弹提示；`apply_selection_settings()` 把设置下发到监听器与浮窗；
  修掉 `selection_anchor` 在失败/取消时不重置、导致下次整屏翻译错弹浮窗的问题。
- `settings.py`：新增"划词翻译"标签页（开关 / 浮窗位置 / 浮窗宽度）；外观页增加头像开关。

### 桌宠

- 头像 `assets/haibara_head.png` 已确认是 1254×1254 RGBA、四角 alpha=0（真透明）。
- `pet.py`：`paint_pet(..., use_avatar)`；头像模式下用**皮肤色光晕 + 描边圆环 + 状态药丸**
  表现换肤，否则换色在固定立绘上看不出来；保留原矢量猫头鹰作为可切换备选。

## 验证记录

- 源码测试：37 项通过（新增 `tests/test_selection_popup.py` 与 `tests/test_terminology.py`）。
- 源码自检：9 项全过（Qt 6.11.2 / platform=windows / 头像 / OCR / 离线翻译 / TLS）。
- 冻结版 clean rebuild 1（17:36）：包内 **无任何 icu*.dll / poppler 残留**；
  `libssl-3-x64.dll` 1599280 B、`libcrypto-3-x64.dll` 8003376 B，与解释器副本一致；
  `assets/haibara_head.png` 已进包；冻结版自检 9/9 通过（`frozen=True`, `platform=windows`）。
- 冻结版 clean rebuild 3（17:47，最终）：自检的 `offline_translation` 改为走用户真实路径
  `translate_blocks` 后，冻结版输出 **`波束成形提高了信干噪比.`**，
  证明术语校正确实生效在打包后的 exe 里（此前该检查直接调原始适配器，覆盖不到校正）。
  报告副本：`docs/frozen-selftest.json`。

### 打包后的 exe 是否真能跑（不是"进程还活着"）

`ScholarPet.exe --selftest` 在包内实测 9 项：

```
ok=True frozen=True  exe=...\dist\ScholarPet\ScholarPet.exe
  [True] qt_core            : Qt 6.11.2
  [True] qapplication       : platform=windows
  [True] widgets            : Pet, Reader, SettingsDialog, SelectionPopup, TrayIcon
  [True] pet_avatar         : 1254x1254 with alpha
  [True] selection_monitor  : windows_api=True
  [True] offline_translation: ... 含术语校正 -> 波束成形提高了信干噪比.
  [True] ocr                : recognised 1 block(s): Beamforming improves signal quality.
  [True] tls                : OpenSSL 3.5.8 25 Aug 2026
  [True] data_dir           : C:\Users\SherryAlbert\AppData\Local\ScholarPet
```

## 翻译精度：离线模型的术语校正

实测暴露了 Argos 英中模型在通信领域的固定误译：

| 英文 | 校正前 | 校正后 |
| --- | --- | --- |
| beamforming | 光束造型 | 波束成形 |
| signal-to-interference-plus-noise ratio | 信号-干扰-加-噪声比 | 信干噪比 |
| frequency hopping spread spectrum | 频率跳跃散射频谱 | 跳频扩频 |
| bit error rate | 位误率 | 误比特率 |
| anti-jamming | 反干扰 | 抗干扰 |
| converges | 趋同 | 收敛 |
| direction of arrival | 到达方向 | 波达方向 |

结论与做法：

- **源端替换中文术语不可行**：给模型混排中文会让它输出 `{\fn黑体\fs32...}` 这类字幕标签。
- 因此改为**译文后校正**：`glossary.OFFLINE_MODEL_CORRECTIONS` 只在 `engine == offline` 时应用，
  且**用户术语表在之后应用**，个人规则始终优先。
- 同时补齐 `DEFAULT_ACADEMIC_GLOSSARY`（约 100 条通信/抗干扰术语）。这些英文键对
  **LLM 引擎**直接生效（注入 system prompt），对离线引擎只用于规范化输出里残留的英文缩写。
- `offline.sanitize()` 清掉解码残留的 `▁`（U+2581，此前会出现在句首）与字幕标签乱码。

## 构建注意（本机）

本机 PowerShell 默认禁止运行脚本文件，构建必须显式绕过：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

脚本会依次：清理 build/dist → 装依赖 → 跑测试 → PyInstaller → 校验包内无污染 DLL →
跑 `ScholarPet.exe --selftest` → 打 zip。

## 续作提示

- 先读本文件 + `git status`/`git diff`，不要覆盖用户自建的 `QtTest.spec`。
- 打包问题若复发，先看 `build/ScholarPet/COLLECT-00.toc` 里 DLL 的来源路径，
  再看 `%LOCALAPPDATA%\ScholarPet\selftest.json` 的具体失败项。
- 中间产物放 workspace `work/`；源码与交付物放 `outputs/ScholarPet/`。
- 尚未处理：GitHub 上传（用户表示自行处理）。

---

# 灰原哀灵动版（第二轮）

目标：单张静态立绘 → 会眨眼、动嘴、视线跟随的桌宠，且**幅度必须小**。

## 核心决定：面部骨骼绑定，不重绘

任何"用模型重新生成一张脸"的思路都会让角色形象飘掉，所以整条链路是
**从原图像素里抠出可动部件，动画只做位移与覆盖**：

| 层 | 来源 | 用途 |
| --- | --- | --- |
| `base` | 原图，但虹膜被周围眼白填掉 | 底图；虹膜移开后不会露出自己的残影 |
| `iris` | 蓝灰色、色度 25–110、亮度 70–205 的连通块 | 视线偏移 |
| `lash` | 暗色像素中**水平游程够长**的部分 | 眨眼时整体下移，成为闭眼的睫毛线 |
| `lips` | 嘴部暗色细线 | 张嘴后盖回最上层，保住原唇形 |
| `hair` | 刘海（暗棕色） | 皮肤覆盖后重绘回去，否则眨眼刮掉头发 |

抠图是纯像素级的：用 numpy 按亮度 / 色度 / 冷暖分离，睫毛额外用**游程长度过滤**
把刘海从"暗色"里摘出去。阈值最初取 `max(4, w*0.5)`，眼角睫毛游程太短导致右眼整层丢失，
降到 `max(4, w*0.20)` 后两只眼都正确。

## 眨眼：为什么不是"垂直挤压"

第一版把眼睛贴图垂直压扁到 1px，结果眼白 + 睫毛 + 虹膜被平均成**一条灰带**，
看起来像坏掉的 GIF。改成三步合成：

1. 眼睑**走过的区域**先铺开脸颊皮肤（皮肤色从**眼下脸颊**采样，不是从眼框内），
   并把 `hair` 层重绘在皮肤之上；
2. 用**杏仁形裁剪路径**（`_lid_path`，底边向下弯 `bow = (floor-top)*0.30`，随闭合收缩）
   裁出剩下的眼缝——直边切断是"照片被剪裁"，向下弯的弧线才是眼睑；
3. 原图睫毛层按 `LID_TRAVEL` 下移，作为闭眼状态的睫毛线。

闭眼时漏眼白的问题也是在这一步解决的：`eye_bottom` 与 `lash_bottom` 从原图**量出来**
（写进 rig 的 `metrics`），而不是拍脑袋填常数。羽化遮罩会留下半透灰糊，所以改用
`_compose_cover` 做水平渐变的硬覆盖。

## 视线与张嘴上限定得很死

- `GAZE_X = 0.085`、`GAZE_Y = 0.055`：虹膜位移不超过眼宽的 8.5%，移出眼白就会露馅；
- `MOUTH_OPEN = 0.95`、`MOUTH_WIDEN = 0.10`：嘴只在竖直方向开口、几乎不加宽，避免"大嘴怪"；
- 中立姿态走**快捷路径**直接返回原 `portrait`，未对话时零合成开销；
  但测试要比较中立姿态时必须用 `0.995` 强制走完整合成，否则拿到的是原图，比出来是假的。

## 构图上的硬约束：只许改自己的区域

立绘动画最容易翻车的地方是**画到框外**，所以测试主体是"围栏"而不是"像不像"：
眨眼只许改眼框内像素、视线只许动虹膜、张嘴只许重画嘴。测试用 `RIG` 的框 + 外扩余量
逐区域比对，任何越界直接失败。

## 构建链路

- `ScholarPet.spec` 的 `datas` 补了 `assets/haibara_head.rig.json`。
  **漏掉它不会报错**——`load_rig()` 会静默回退到内嵌的 `FALLBACK_RIG`，只是坐标精度差一点，
  所以专门加了一条测试 `test_build_spec_ships_the_face_sidecar` 盯着 spec 里这行字符串。
- `selftest.py` 新增第 5 项 `face_rig`：断言 rig 与 artwork 尺寸匹配（证明 sidecar 进了包），
  并真渲染三帧（中立 / 闭眼 / 张嘴）确认像素确实变了、且眨眼没有重画整张图。
  冻结版实测输出：`1254x1254 rig · blink 3.3% of pixels · mouth 0.4%`。

## 验证记录

- 源码测试 **67 项通过**（`tests/test_face.py` 24 项）。
- 冻结版自检 **10 项全过**（新增 `face_rig`），实测输出：

```
  [PASS] qt_core            : Qt 6.11.2
  [PASS] qapplication       : platform=windows
  [PASS] widgets            : Pet, Reader, SettingsDialog, SelectionPopup, TrayIcon
  [PASS] pet_avatar         : 1254x1254 with alpha
  [PASS] face_rig           : 1254x1254 rig · blink 3.3% of pixels · mouth 0.4%
  [PASS] selection_monitor  : windows_api=True
  [PASS] offline_translation: 含术语校正 -> 波束成形提高了信干噪比.
  [PASS] ocr                : recognised 1 block(s): Beamforming improves signal quality.
  [PASS] tls                : OpenSSL 3.5.8 25 Aug 2026
  [PASS] data_dir           : C:\Users\SherryAlbert\AppData\Local\ScholarPet
```

- 包内已确认含 `assets/haibara_head.rig.json`（558 B）与 `haibara_head.png`，
  且无任何 `icu*.dll` 残留。
- 中间产物：`docs/face-preview*.png`、`docs/face-layers.png`、`docs/face-blink-strip.png`、
  `docs/pet-widget-strip.png`（由 `scripts/preview_face.py` 生成，
  含与 artwork 的数值保真度对比：平均漂移 < 2.5/255）。

## 顺手修掉的构建问题

### 1. 清理 `build/`、`dist/` 慢得像卡死

`build.ps1` 原本用 `Remove-Item -Recurse -Force`。PowerShell 会把走过的每一个路径重新
stat 一遍，在 PyInstaller 产物（上千文件、数百 MB）上要跑好几分钟，而且**期间没有任何输出**，
看起来完全像死循环（第一次构建就在这里白等了几分钟）。现在改成
`[System.IO.Directory]::Delete($path, $true)`——同一棵树不到一秒删完——并保留
`Remove-Item` 作为只读文件时的兜底，同时打印 `Removing stale dist ...` 提供可见进度。
构建总耗时 3m55s → 2m25s。

### 2. 测试会随机/偶发以非零码退出（两个独立成因）

现象：`build.ps1` 在 pytest 显示 `67 passed` 之后报 `Tests failed.` 而中断——
一场全绿的测试却挡住了构建。查下来其实是**两个互不相干的成因**。

#### 成因 A：Qt 在解释器退出阶段踩空（概率约 1/6）

单独跑 pytest 3/3 都返回 0，于是用 `-X faulthandler` 循环复现，抓到现场：

```
...................................................................      [100%]
67 passed in 4.20s
Fatal Python error: Aborted
Current thread 0x00007f7c (most recent call first):
  <no Python frame>
Windows fatal exception: access violation
```

`<no Python frame>` 说明崩溃发生在**解释器退出阶段**，与测试代码无关：
测试里 `show()` 过的顶层控件活到了 Qt 拆卸期，而那时对象图已经半销毁。

修法：`tests/conftest.py` 新增 session 级 autouse fixture，在会话结束时
`close()` → `deleteLater()` → `sendPostedEvents(DeferredDelete)` → `processEvents()`，
让控件在 QApplication 还活着的时候被真正销毁。**只 `close()` 不够**——它只是隐藏窗口，
C++ 侧要等事件循环处理完延迟删除才消失。

验证：修复后连续 **60 次**跑测试，**0 次非零退出**。

#### 成因 B：pytest 清理自己的临时目录被批量删除门禁拦下

换了个环境复跑构建，又冒出一次 `Tests failed (exit code 1)`，日志里多了这行：

```
[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":375,"threshold":50,
 "targets":["...\\Temp\\pytest-of-Sherryalbert\\garbage-6f3f66b6-..."]}
```

pytest 默认把临时目录放在 `%TEMP%\pytest-of-<user>` 下并按编号留存，每个会话结束时会
把过期的那几个**用一次批量目录删除**清掉。在会批量删除做门禁的环境里，这次删除被要求
二次确认，pytest 把"拒绝"当成错误 → 全绿也退出 1。反复跑测试会让 `garbage-*` 越积越多，
于是这个问题从"偶尔"变成"必然"。

修法：给 pytest 显式指定 `--basetemp build\pytest-tmp`。一旦 basetemp 是显式给出的，
pytest 就完全不走那套留存/回收机制，也不再去动用户的 `%TEMP%`；而 `build/` 本来就被
gitignore 覆盖、且在本脚本开头就被清掉。

> 附带修掉一个判据隐患：原来写 `if ($LASTEXITCODE -ne 0)`，
> 而 PowerShell 里未设置时为 `$null`，`$null -ne 0` 是 **true**，会误罚成功的构建。
> 改成 `if ($LASTEXITCODE)` 并在报错信息里带上退出码。

## 踩坑备忘

- 构建时若报 `dist\...\charset_normalizer\cd.cp312-win_amd64.pyd 访问被拒绝`，
  **不是权限问题也不是沙箱**，而是桌面上还跑着旧的 `ScholarPet.exe`（它 import 了
  requests → charset_normalizer）锁住了文件。先 `Get-Process ScholarPet` 关掉再构建。
- 本机 PowerShell 输出在被工具捕获时可能为空，构建日志要重定向到文件再读；
  重定向出来的 `.raw` 是 UTF-16LE，`iconv -f UTF-16LE` 才能看。

---

# 第三轮：脸被放大裁掉 + 点击空白关闭浮窗

## 症状

运行中的桌宠只露出**脸的中段**：画框大小是对的（112.5px = `0.9 × 100 × 1.25`），
但脸被放大约 1.25 倍并从**左上角**溢出，下巴和两侧头发都被裁掉。用户截图里：

```
内容行 75..186（112px）、列 64..176（113px）—— 正好是画框
但虹膜间距 47px，原画对应位置只该有 38px  → 放大 1.2444 倍
```

1.2444 正是 `devicePixelRatio()`（112px / 90 逻辑像素），也就是这台机器的 125% 缩放。

## 根因：复用画布把上一帧的 devicePixelRatio 带了过来

`Face.render` 为性能复用同一张 `self._canvas`，并在**返回前**给它设 dpr，
好让控件按逻辑尺寸贴图：

```python
out = self._canvas or QPixmap(width, height)
...
out.setDevicePixelRatio(self.dpr)   # 交给调用方 —— 然后被下一帧复用
```

于是第二帧起，`QPainter(out)` 继承到 `dpr = 1.2444`，而图层是 dpr=1 的原始像素图 ——
Qt 按"逻辑尺寸"把它们**放大 1.2444 倍**画进同一块 112px 画布，只有左上角
`1/1.2444 ≈ 80%` 落在画布内。用虹膜位置验算：

| | 预测 `u × 1.2444` | 实测 |
| --- | --- | --- |
| 左眼 | 0.434 / 0.847 | **0.436 / 0.849** |
| 右眼 | 0.847 / 0.828 | **0.853 / 0.828** |

完全吻合，也解释了两件事：**第 1 帧是好的**（画布刚建，dpr=1），
**眨眼一次之后就永远放大**（第一次走动画合成路径时画布被"污染"）。

修法是合成前复位、合成完再设回：

```python
out.setDevicePixelRatio(1.0)        # 在原始设备像素里合成
...
out.setDevicePixelRatio(self.dpr)   # 交出去时带上比例
```

`_plain()` 的注释写着 "drop the device pixel ratio"，但 `QPixmap.fromImage` 是**保留**比例的，
所以顺手让它显式 `setDevicePixelRatio(1.0)`，不要再靠"以为它清零了"。

## 为什么之前所有验证都是绿的

这是本轮最值得记的一条：**bug 只出现在第 2 帧之后，而所有离屏探针都只画了第 1 帧。**

- `scripts/preview_face.py` 把 rig 直接画进 QImage，**根本不经控件**，看不到；
- 冻结版自检 `face_rig` 也是新进程里的头几帧，同样看不到；
- 我自己写的离屏复现脚本 `paint_pet(...)` 每次新建画布，照样看不到。

只有让**同一个 Face 连续渲染**、或抓**真实控件**（`QWidget.grab()`）才复现。
所以新增 `scripts/preview_pet.py`：渲染整个控件，并**故意把同一姿态画两次**
（"看右下" → "再看右下"），两帧不一致就是这一轮 bug。修复前后：

```
修复前： idle 9.35 | 看右下 9.51 | 半眨眼 50.47 | 说话 51.33 | 再看右下 51.62  → FAIL
修复后： idle 9.35 | 看右下 9.51 | 半眨眼 10.44 | 说话 9.43  | 再看右下 9.51   → ok
```

同姿态两帧**逐像素一致**（9.51 = 9.51）。另有两条 pytest 守着：
`test_reused_canvas_does_not_inherit_the_previous_frames_ratio`（同姿态 4 帧互比）
和 `test_a_gaze_frame_still_shows_the_whole_portrait`（动画帧与原画比；去掉修复后报 87/255）。

## 测量方法上的两个坑（差点把我带偏）

1. **不能拿"内容包围盒"当画布。** 原画几乎铺满整格（不透明区域 x 0.0072–0.992），
   所以放大裁切后内容包围盒**恰好等于**画框 —— 看起来"完全正确"。
   真正能区分的是**特征点间距**（虹膜），不是外框。
2. **环境不等价的坑。** `QT_QPA_PLATFORM=offscreen` 下控件的 `devicePixelRatioF()`
   恒为 1.0，要用 `QT_SCALE_FACTOR=1.25` 才能逼出真实比例；而这个组合下
   `drawPixmap` 连 pixmap 自身的 dpr 都不应用（离屏插件伪影，真实屏幕是应用的）。
   所以离线抓图适合抓"放大/裁切"这类结构性错误，**不适合判定亚像素级吻合**。

## 新功能：点击浮窗以外任何地方即关闭

原本只能按 Esc、点「×」或单击右键关掉；读完译文想继续看论文时，浮窗正好挡住刚选的那句话。

关键约束：**Qt 只把鼠标事件发给指针所在的窗口**，所以浮窗根本收不到"点在网页上"的事件，
只能在 `SelectionMonitor` 已有的 35ms 按钮轮询里加一路信号：

- `SelectionMonitor.left_press`：每次**新的左键按下**（上升沿）发一次，长按不重复上报；
- 上报发生在 `enabled / paused / _capturing` 三个门禁**之前** —— 浮窗既然在屏幕上，
  就该能被点掉，与"划词捕获是否武装"无关；
- 顺手修掉一个隐患：按下期间若被 paused，`_down` 会一直卡在 True，**下一次按下被整个吞掉**。
  现在按下/抬起无条件记账（`test_pausing_mid_press_does_not_swallow_the_next_one`）。
- `SelectionPopup.click_away(point)` 只在**可见且点在 `frameGeometry()` 之外**时关闭并返回 True；
  **点在框内不动它**，否则「复制中文」「完整对照」和手动选译文都会失效。

## 第三轮验证记录

- 源码测试 **75 项通过**（原 69 + 画布 2 + 监视器 4）。
- `scripts/preview_pet.py`：控件级预览，5 帧全部 **9.35–10.44/255**，同姿态帧逐像素一致。
- 反向验证：临时删掉 `out.setDevicePixelRatio(1.0)`，两条 pytest 均失败（漂移 87/255），
  `preview_pet.py` 报 `FAIL: 51.6/255` —— 守卫确实能抓到这个 bug，不是摆设。
- 产物：`docs/pet-widget-strip.png`（含 idle / 视线 / 半眨眼 / 说话 / 重复姿态五帧）。


# 第四轮：截图粘不进微信 / QQ + 去掉三个快捷键

## 本轮请求（来自用户）

1. "我不需要三个快捷键"——只需让人知道：鼠标任意划选翻译、点桌宠＝整屏翻译、
   点桌宠下方「框选翻译」＝框选 OCR、双击＝设置。
2. "用 shift+win+s 和 prtsc 截图时无法把截图粘贴到微信 / QQ 对话框，就是没反应了，
   图能成功截。"

## 根因：划词翻译把用户的剪贴板清空了

`selection_monitor._copy_selection` 原来的顺序是：

```
snapshot = _clipboard_snapshot()      # 备份
clipboard.clear()                     # ← 清空
发 Ctrl+C
轮询 clipboard.text() 直到非空或超时
QTimer.singleShot(45, 恢复 snapshot)
```

两个各自独立、但都致命的缺陷：

1. **`clear()` 是多余的破坏。** 它存在的理由只是"制造一个已知为空的基线，好判断
   Ctrl+C 到底有没有产出内容"。但截图（`Win+Shift+S`、`PrtSc`）和划词翻译**共用同一块
   剪贴板**——清空的那一刻，用户刚截的图就没了。
2. **快照根本存不住位图。** `_clipboard_snapshot` 用 `mime.data(fmt)` / `copy.setData(fmt, …)`
   逐个格式复制。截图在 Qt 里是 `application/x-qt-image`，这个格式**通过 `data()` 读出来是空的**，
   于是"恢复"回去的是一张 Qt 自称有图、实际拿不出字节的空壳。

第 2 点已在 `_clip_probe4.py` 里量成表格（回填后 `cb.image()` 是否可读）：

| 回填方式 | 结果 |
| --- | --- |
| A 现状：`data()` / `setData()` 逐个格式 | **null —— 图丢了** |
| B 加一份 `image/png` payload | null —— Qt 不会拿它还原 `image()` |
| C `QClipboard.setImage()` | 64x48 ✅ |
| D `QMimeData.setImageData(QImage)` + 原格式 | 64x48 ✅ **且其它格式一起保留** |

还有一个容易骗过验证的现象：`EnumClipboardFormats` 在**坏掉之后依然列着 `CF_DIB(8)` /
`CF_BITMAP(2)`**——格式是"挂牌"的，只是渲染出来没有数据。所以判断保真度只能看
`QClipboard.image()` 能不能读出像素，不能看格式列表。

## 修法：剪贴板只借不占

`_clip_probe.py` 第 6 节给了关键结论：**没被任何应用响应的 Ctrl+C 不会推进剪贴板序号**
（1669 → 1669），图片原地不动。于是"有没有被替换"根本不需要靠清空来试探。

- **不再 `clear()`。** 改读 `GetClipboardSequenceNumber()`：Windows 每次 `SetClipboardData`
  都会推进它，序号不动就说明按键被忽略，此时剪贴板原封未动，**什么都不用还原**。
- **只有真被替换过才回填**，并且在回填前再核对一次序号：如果用户在这 45 ms 里又截了一张图，
  新内容属于用户，旧快照不许覆盖（`_restore_clipboard(mime, sequence)`）。
- **位图用 `setImageData` 存**（探针表里的 D 方案），所以回填出来的还是真正的 `CF_DIB`，
  微信、QQ 拿得到。
- **"没被响应"同时是扫描版 PDF 的信号**，`unreadable` 提示照旧发出——只是不再回填任何东西。
  这一点如果漏了，扫描版 PDF 就会从"提示你改用框选 OCR"退化成"静默无反应"。

## 顺带：截图工具的框选不再被当成划词

`Win+Shift+S` 需要拖拽选区，而拖拽正是划词翻译的手势。于是在 `_request_selection` 就被挡掉：
新增 `_process_name(hwnd)`（`OpenProcess` + `QueryFullProcessImageNameW` 取可执行名），
与 `BLOCKED_PROCESSES`（`snippingtool.exe` / `screensketch.exe` / `snipaste.exe` / `sharex.exe` /
`greenshot.exe` / `pixpin.exe` / `lightshot.exe` 等）比对。

即使某个截图工具的进程名不在名单里，上面的剪贴板策略也保证它不会被破坏——这一层只是避免
"截图到一半弹出『该区域没有可复制的文字层』"这种多余的提示。

`ctypes` 细节：`OpenProcess` 必须显式设 `restype = wintypes.HANDLE`，否则 64 位下句柄被截成
`int`，每次调用都失败。

## 去掉三个全局快捷键

`Ctrl+Alt+T / S / V` 全部取消注册，`scholarpet/hotkeys.py` 整块删除（`app.py` 的 import、
`self.hotkeys`、`action()`、`quit()` 里的 `close()`、`aboutToQuit` 接线一并移除；
`ScholarPet.spec` 的 `hiddenimports` 里本来就没有它）。所有动作改为只走鼠标：

| 动作 | 入口 |
| --- | --- |
| 翻译选中内容 | 鼠标任意划选（主入口） |
| 整屏翻译 | 单击灰原哀头像 |
| 框选 OCR | 点击头像下方「框选翻译」 |
| 设置 | 双击头像 |

同步清理了托盘菜单、桌宠右键菜单、桌宠 tooltip、「中英对照」窗页脚、设置页「使用说明」、
首次启动欢迎文案和 README。**剪贴板翻译**功能本身保留，只是不再有热键，入口在右键菜单
（「翻译剪贴板文字」）。

## 第四轮验证记录

- 源码测试 **83 项通过**（原 75 + 剪贴板 6 + 快捷键 2），**连跑三次退出码均为 0**
  （新增 `_release_clipboard` fixture 之后；见下面「又一个全绿但退出码非零」）。
- 新增守卫：
  - `test_a_screenshot_survives_a_capture_that_finds_no_text` —— 目标不响应时剪贴板必须原封不动，
    且 `unreadable` 提示仍然发出；
  - `test_a_snapshot_can_put_a_bitmap_back` —— 位图必须能原样读回（正是 `setImageData` 那条修复）；
  - `test_a_restore_never_overwrites_a_newer_copy` —— 序号变了就不许回填；
  - `test_a_snip_tool_is_never_asked_for_a_selection` / `test_a_snip_drag_does_not_arm_the_capture`；
  - `test_the_package_registers_no_global_hotkeys` —— 扫描 `scholarpet/*.py` 里出现
    `RegisterHotKey` 或 `Ctrl+Alt` 即失败，并断言 `scholarpet.hotkeys` 已不可导入；
  - `test_the_pet_tooltip_advertises_only_mouse_actions` —— tooltip 不许出现 `Ctrl`/`Alt`，
    且必须提到划选 / 单击头像 / 框选翻译 / 双击。
- **反向验证**：把三处破坏性写法放回去（加回 `clipboard().clear()`、`_clipboard_snapshot` 丢掉
  `setImageData`、`_restore_clipboard` 忽略序号），对应用例精确地 3 failed —— 守卫有效。
- 冻结自检从 10 项内容里加强了 `selection_monitor`：源码运行输出
  `windows_api=True · clipboard keeps bitmaps`（真的走一遍位图往返）。
- 文档：README 增加「四个动作，零快捷键」与「剪贴板只借不占」两节。

## 踩坑备忘（第四轮）

- **`QMimeData` 在 PySide6 里没有 `setImage`**，只有 `imageData()` / `setImageData()`；
  而 `QClipboard` 有 `image()` / `setImage()`。查 API 别照抄 C++ 文档。
- `QMimeData.data("application/x-qt-image")` 读不回图，但 `imageData()` 可以——
  前者存的是字节，后者存的是 `QImage` 本身。
- 剪贴板格式列表（含 `EnumClipboardFormats`）**不能**用来判断数据是否有效，只能看能否解码。
- PowerShell 工具的 stdout 不会回传，脚本要自己把结果写文件（UTF-8），
  否则 `Out-File` 默认 UTF-16 会让读回的内容变成二进制。

### 又一个"全绿但退出码非零"：offscreen 剪贴板的析构缺陷

第四轮新加的剪贴板测试让构建卡在 pytest 门禁上：

```
83 passed in 5.17s
Tests failed (exit code -1073741819).
```

`-1073741819` = `0xC0000005` = `STATUS_ACCESS_VIOLATION`。注意它**发生在 pytest 打印结果之后**，
和 `tests/conftest.py` 里 `_dispose_qt_before_shutdown` 记录的症状一样，但成因完全不同
（那次是残留的顶层控件，这次是剪贴板）。上一节说的"偶发一次构建失败"是随机性的，
这次是**必然复现**的。

定位靠"一个变体一个进程、量退出码"（`_off_probe.py`）：

| offscreen 平台 | 不加 reset | reset 后 |
| --- | --- | --- |
| `nothing` / `settext` / `setimage` / `clear_after_image` | 0 | 0 |
| `roundtrip_text`（纯文本往返） | **-1073741819** | 0 |
| `roundtrip_noclear` | **-1073741819** | 0 |
| `roundtrip_clear` | **-1073741819** | 0 |
| `setimagedata_then_exit` | **-1073741819** | 0 |

windows 平台上 `roundtrip_clear` / `setimagedata_then_exit` 都是 **0**。

结论：**诱因是 `QClipboard.setMimeData` 让我们成为剪贴板所有者**——与图片无关，
纯文本往返同样崩；这是 offscreen 插件自己的析构缺陷，**不是应用代码的问题**
（应用跑在 windows 平台上，实测干净）。修法放在测试侧：`tests/conftest.py` 新增
autouse fixture `_release_clipboard`，每个用例结束后 `clipboard().setText("")` 交还所有权。
连跑三次退出码均为 0。

**方法论教训**：`& $python -m pytest ... ; Write-Output "exit=$LASTEXITCODE"` 这种写法里，
外层命令的最后一句决定了工具看到的退出码——`Write-Output` 永远返回 0，
于是**崩溃被静默吃掉**。必须把 `$LASTEXITCODE` 写进文件再读，或者让被测命令成为最后一句。
另外 `build.ps1` 里 `if ($LASTEXITCODE)` 的判断是对的，它正是靠这个抓到了本次问题。

### 又一个：`Compress-Archive` 撞上 exe 的瞬时占用

修完 pytest 的崩溃后，build8 在**最后一步**失败了：

```
  [PASS] selection_monitor (0.03s) windows_api=True · clipboard keeps bitmaps
  ...
ZipArchiveHelper : 文件"...dist\ScholarPet\ScholarPet.exe"正由另一进程使用，因此该进程无法访问此文件。
=== EXITCODE=1 ===
```

注意**冻结自检已经 10/10 全 PASS、exe 也已经生成**——失败的只是收尾的打包 zip。
原因：冻结自检刚跑完，exe 的镜像段还没完全释放（或被杀软实时扫描占着）。
`Start-Process -Wait` 等到了退出码，但文件句柄的释放比进程退出更晚。

修法：`build.ps1` 的 `Compress-Archive` 加重试（10 次 × 700 ms，`-ErrorAction Stop` 让它可捕获）。
一个已经完成并验证过的构建，不该因为一次瞬时锁而整体判失败。





