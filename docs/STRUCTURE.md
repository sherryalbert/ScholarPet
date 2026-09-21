# 项目结构与文件职责

本文逐文件说明 ScholarPet 的组成。凡是"为什么这么写"不明显的地方，都在代码注释与
`docs/PROGRESS.md` 里留有理由；这里给出的是**每个文件存在的原因、对外接口和关键约束**。

```
ScholarPet/
├─ run.py                     唯一入口
├─ ScholarPet.spec            PyInstaller 打包描述
├─ requirements.txt           运行依赖（锁定版本）
├─ requirements-dev.txt       开发依赖（含 PyInstaller、pytest）
├─ README.md / LICENSE / THIRD_PARTY_NOTICES.md
├─ .gitignore / .gitattributes
├─ scholarpet/                应用源码（15 个模块）
├─ assets/                    头像原图 + 面部骨骼标注
├─ scripts/                   构建、取模型、标定与预览工具
├─ tests/                     pytest 套件（83 项）
├─ models/                    离线英中模型（不入版本控制，见下）
├─ docs/                      开发记录与预览图
└─ dist/                      构建产物（不入版本控制）
```

## 顶层文件

| 文件 | 职责 |
| --- | --- |
| `run.py` | 唯一入口。`--selftest` 转到 `scholarpet.selftest.run()`，否则调 `scholarpet.app.main()`。故意保持极薄，让 `ScholarPet.spec` 只需分析一个脚本。 |
| `ScholarPet.spec` | PyInstaller **onedir** 配置。`datas` 打入 `assets/`、`THIRD_PARTY_NOTICES.md` 与 `models/translate-en_zh-1_9`；`hiddenimports` 显式声明 onnxruntime 的 pybind 扩展、`scholarpet.offline`、`scholarpet.selftest`、ctranslate2、sentencepiece（这些是动态导入，静态分析看不到）；`excludes` 去掉 tkinter/matplotlib/scipy/pandas/QtWebEngineCore。**三层防 DLL 污染**：① `_is_codex_native()` 剔除所有来源在 `codex-runtimes/.../native/`（poppler 的 ICU/OpenSSL）的二进制；② 从解释器自身 `DLLs` 补回 `libssl-3-x64.dll`/`libcrypto-3-x64.dll`/`libffi-8.dll`；③ 不用 UPX。选 onedir 而非 onefile 是刻意的：LGPL 的 Qt 库保持可替换、启动不必解压。 |
| `requirements.txt` | 运行依赖，全部锁定具体版本（PySide6-Essentials 6.11.2、rapidocr-onnxruntime 1.4.4、onnxruntime 1.30.0、numpy 2.5.3、requests 2.34.2、ctranslate2 4.8.2、sentencepiece 0.2.2）。 |
| `requirements-dev.txt` | 在运行依赖之上加 `pyinstaller==6.22.3`、`pytest==9.1.1`。 |
| `README.md` | 面向使用者与贡献者：四个鼠标动作、剪贴板只借不占的原理、面部绑定的实现、隐私边界、开发与构建命令、打包注意事项、获取模型、分发方式。 |
| `LICENSE` | MIT，覆盖**源代码**（不含角色美术素材，见 `THIRD_PARTY_NOTICES.md`）。 |
| `THIRD_PARTY_NOTICES.md` | 上游组件许可证表（Qt/RapidOCR/ONNX Runtime/CTranslate2/SentencePiece/PyInstaller…）、模型来源与 CC-BY 4.0 声明、以及角色素材版权归属声明。 |
| `.gitignore` | 排除虚拟环境、字节码、pytest 缓存、`build/`、`dist/`、**`models/`（82 MB 模型）**、`settings.json`、密钥与压缩包。 |
| `.gitattributes` | 统一换行（`.ps1` 保持 CRLF），并把图片与 `.argosmodel` 标为二进制，避免 Git 做无谓的文本 diff。 |

## `scholarpet/` —— 应用源码

| 模块 | 行数 | 职责与关键接口 |
| --- | --- | --- |
| `__init__.py` | 2 | 包声明与 `__version__`（当前 `0.5.0`，与 README、设置页保持一致）。 |
| `app.py` | 19.8 KB | **控制器与编排**。`Worker(QObject)` 跑在 `QThread` 里，完成"OCR → 分栏排序 → 分段落 → 翻译"并回传信号；`Controller(QObject)` 组装所有窗口（`Pet` / `SelectionPopup` / `Reader` / `Overlay` / `Selection` / `SettingsDialog` / 托盘 / `TopmostKeeper` / `SelectionMonitor`）并接线。对外方法：`capture(region)`（抓整屏或进入框选）、`take_snapshot`、`start_worker`、`succeeded`/`fail`、`selection_gesture`、`selection_click_away`、`selected_text`、`show_settings`/`apply_settings`、`apply_selection_settings`、`welcome`、`reset_pet`、`quit`、`main()`。**它是唯一知道"哪个信号接到哪个槽"的地方。** |
| `config.py` | 2.8 KB | 设置持久化。`DEFAULTS` 是全部可存键的白名单；`data_dir()` 用 `SCHOLARPET_DATA_DIR` 或 `%LOCALAPPDATA%\ScholarPet`（测试靠这个变量隔离）；`_crypt()` 走 Windows DPAPI（`CRYPTPROTECT_UI_FORBIDDEN`，绝不弹凭据框）；`load_settings`/`save_settings` 把 API Key 以 `encrypted_key` 存 base64，其余键严格按白名单过滤，写入用 `.tmp` → `replace()` 原子替换，读入时对 `pet_size`(76–160)、`opacity`(45–100) 做夹紧。 |
| `face.py` | 28 KB | **面部骨骼绑定**（全项目最精密的部分）。`load_rig`/`rig_matches` 读 `assets/haibara_head.rig.json`；`split_features()` 从原图按像素掩膜抠出 `base`/`iris`/`lips`/`lash`/`hair` 五层；`_long_runs`、`_alpha_layer`、`_sclera_colour`、`_skin_patch` 是掩膜与补皮工具；`Face.render(blink, mouth, gaze)` 负责合成——**合成前把复用画布的设备像素比复位为 1.0**，否则下一帧会继承比值把图层整体放大（详见 README）；`_lid_path()` 用杏仁形裁剪留眼缝而不是直边切断；`_paint_eye`/`_paint_mouth` 只移动既有像素、永不重绘；`face_for()` 按 (尺寸, dpr) 缓存；`FaceClock` 负责自主眨眼（2.2–6.6 s，18% 连眨）、视线跟随与正弦包络动嘴。幅度常量集中在文件头部（`LID_TRAVEL`/`LID_RISE`/`GAZE_X`/`MOUTH_OPEN`/`BLINK_SECONDS`…）。 |
| `glossary.py` | 8.4 KB | 术语。`DEFAULT_ACADEMIC_GLOSSARY` 内置通信与抗干扰常用词；`OFFLINE_MODEL_CORRECTIONS` 修正离线模型的已知误译；`normalize_glossary` 清洗用户输入；`merged_glossary` 保证**用户填写优先于内置更正**。 |
| `ocr.py` | 15.8 KB | RapidOCR 封装。`_get_engine()` 懒加载 + `_ENGINE_LOCK`，推理走 `_INFERENCE_LOCK`（ONNX 会话非线程安全）；`extract_blocks()` 出原始框，`_useful_text()` 过滤低置信（<0.25）与非英文噪声，`order_blocks()`/`_column_groups()` 处理**双栏论文的左栏→右栏、栏内上→下**，`group_paragraphs()`/`_paragraph_record()` 合并段落，`_join_text()` 让连字断行拼接**不加空格**。 |
| `offline.py` | 5.5 KB | 本地离线英中。`_candidates()` 按 设置指定目录 → `sys._MEIPASS`（冻结）→ 仓库 `models/` → `%LOCALAPPDATA%\ScholarPet` 依次找模型；`model_path()` 以 `model/model.bin` + `sentencepiece.model` 同时存在为判据；`_load()` 单例加载 CTranslate2 + SentencePiece（CPU、inter 1 / intra 2）；`_split()` 把长文本按句末标点再按空格切成 ≤220 字符（长句无标点也强制切断）；`sanitize()` 去掉 SentencePiece 的 `▁` 标记、ASS 标签与汉字间多余空格。 |
| `pet.py` | 15.8 KB | 桌宠控件。`avatar_pixmap(logical_side, dpr)` 只做**一次**高质量降采样并按 dpr 缓存（`_SCALED`/`_TINTED`）；`paint_pet`/`_paint_portrait`/`_paint_owl`（没有头像时的猫头鹰兜底）；`art_box`/`badge_rect`/`preferred_height` 定义布局；`pin_above_all()` 设置顶；`Pet(QWidget)` 打开 33 ms 帧定时器（关掉「活灵活现」降到 1 fps 直接显示原图），`_look()` 把鼠标位置换算成视线偏移，单击触发整屏翻译、拖动移动、双击开设置、右键弹菜单，头像下方是「框选翻译」徽标。 |
| `selection_monitor.py` | 13.3 KB | **划词探测**。Qt 只把鼠标事件发给指针所在的窗口，所以"点屏幕任意处"必须靠 35 ms 轮询 `GetAsyncKeyState(VK_LBUTTON)`：`_poll()` 无条件记账按下/抬起，在**上升沿**先于所有门禁（禁用/暂停/框中）发射 `left_press`，`_released()` 负责 drag/double 判定。`_copy_selection()` 向目标发一次 Ctrl+C 后轮询读回；是否真的被响应由 `_clipboard_sequence()`（`GetClipboardSequenceNumber`）判定——**序号不动就说明剪贴板原封未动，什么都不还原**；`_clipboard_snapshot()`/`_restore_clipboard()` 里位图必须用 `QMimeData.setImageData`（`data()`/`setData()` 往返会丢图）；`_blocked_window()` + `BLOCKED_PROCESSES` 跳过终端/密码框/截图工具；`_process_name()` 用 `OpenProcess`+`QueryFullProcessImageNameW`（注意 `restype` 必须是 `wintypes.HANDLE`，否则 64 位下句柄被截断）。 |
| `selftest.py` | 10.8 KB | 冻结自检（10 项）。在**打包后的 exe 里**真实加载 Qt 控件、面部绑定、离线模型、OCR 引擎、TLS 与数据目录——"进程没崩"不算打包成功。`selection_monitor` 一项会真的走一遍位图往返。结果可 `--selftest-out` 写成 JSON。 |
| `settings.py` | 11.2 KB | 设置对话框。三个页签（外观 / 翻译与隐私 / 专业术语）+ 使用说明页；皮肤色板与自定义色、尺寸、透明度、「活灵活现」、头像开关、置顶、划词开关、浮窗侧/宽/字号、引擎切换（本地离线 / Google / OpenAI 兼容）、术语表按 `英文 = 中文` 逐行解析。 |
| `translation.py` | 19.5 KB | **三种翻译引擎**。Google（`clients5.google.com/translate_a/t`，无密钥实验接口）、LLM（任意 OpenAI 兼容 `/chat/completions`，`_LLM_SYSTEM_PROMPT` 是面向通信/抗干扰的学术翻译提示词）、离线（转交 `offline.py`）。`_batches()` 按字符数分批（Google 3500 / LLM 8000，最多 12 项）、`_request_with_retries()` 统一超时 25 s、重试 2 次并**支持随时取消**，`_parse_llm_translations()` 严格校验条数，`_apply_glossary()` 套用术语表；异常类型 `TranslationError`/`TranslationCancelled`。 |
| `views.py` | 18 KB | 四个界面 + 全局 `STYLE`。`Selection`：全屏快照 + 拖动框选（Esc 取消）；`SelectionPopup`：划词译文浮窗，`_place()` 智能避让**不遮挡选中内容**、不抢焦点，`click_away(point)` 供"点浮窗外任意处关闭"使用；`Reader`：整段中英对照窗，含复制与页脚说明；`Overlay`：原位覆盖层，按住看原文、右键转对照窗。 |
| `winutil.py` | 3.6 KB | 窗口置顶保活。`raise_above_all()` 调 `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE)`；`TopmostKeeper` 用**一个** 1.2 s 定时器为多个窗口（弱引用，已销毁的自动剔除）重申置顶——Qt 只在创建窗口时应用一次置顶，浏览器 F11 全屏后重排层级，桌宠就会消失。非 Windows 平台整体降级为 no-op。 |

### 一次划词翻译的数据流

```
鼠标抬起 ─► selection_monitor._poll() ─► _released() ─┬─ drag/double? ─► _copy_selection()
                                                       │                    │ 发 Ctrl+C
                                                       │                    │ 读回文字
                                                       │                    ▼
                                                       │            selected(text, anchor, _)
                                                       ▼
                       app.selection_click_away()            app.selected_text()
                       （点浮窗外任意处 → 关掉浮窗）                │
                                                                    ▼
                                              Worker.run() 线程：glossary → translation/offline
                                                                    │  progress 信号
                                                                    ▼
                                              Controller.succeeded() ─► SelectionPopup.show_translation()
                                                                    └─► Reader / Overlay
```

## `assets/` —— 美术素材

| 文件 | 说明 |
| --- | --- |
| `haibara_head.png` | 1254×1254 的头像原图，是整个桌宠唯一的图形素材。动画只在这张图上做像素级的部件位移。 |
| `haibara_head.rig.json` | 面部骨骼标注：`left_eye`/`right_eye`/`mouth`/`left_iris`/`right_iris` 五个归一化矩形框。由 `scripts/calibrate_face.py` 从原图量测生成；缺失或与原图尺寸不符时 `face.py` 会回退到内置的 `FALLBACK_RIG`。 |

## `scripts/` —— 工具

| 文件 | 说明 |
| --- | --- |
| `build.ps1` | 完整构建流程：清 `build/`+`dist/` → 从 PATH 剔除 codex-runtimes 的 native 目录并把解释器 `DLLs` 提到最前 → 跑 pytest（**显式 `--basetemp build\pytest-tmp`**，见文件内注释的两种踩坑）→ PyInstaller → 只删除与污染源 SHA256 相同的 `icu*.dll` 并核对 `libssl`/`libcrypto` → 在产物上跑冻结自检 → `Compress-Archive` 打 zip（10×700 ms 重试，防杀软瞬时占用）。 |
| `fetch_model.py` | 获取离线模型（**模型不入版本控制**）。默认从 Argos 下载并解压到 `models/translate-en_zh-1_9`；`--archive` 改用本地 `.argosmodel`；`--check` 只报告；`--force` 重装；`--dest`/`--url` 可覆盖。解压时自动剥掉压缩包里那层包裹目录，并带 zip-slip 防护；只用标准库，未装依赖也能跑。 |
| `calibrate_face.py` | 从 `haibara_head.png` 量测五官位置并写出 `haibara_head.rig.json`，同时输出一张标注覆盖图供人眼核对。换头像素材后要重跑。 |
| `preview_face.py` | 把 `Face` 的各种姿态渲染成 PNG，供人眼判断动画是否自然（不含控件层）。 |
| `preview_pet.py` | **控件级**预览：用 `QWidget.grab()` 抓真实控件，并且**故意把同一姿态连画两帧**逐帧比对漂移。之所以需要它：画布复用导致的设备像素比泄漏**只在第 2 帧之后**出现，任何只渲染首帧的检查都会全绿。 |
| `collect_licenses.py` | 收集已安装依赖的许可证文本，供打包进 `_internal/licenses`。 |

## `tests/` —— pytest 套件（83 项）

| 文件 | 覆盖内容 |
| --- | --- |
| `conftest.py` | 会话级 `qapp`；退出前显式销毁 Qt（`_dispose_qt_before_shutdown`）；`_release_clipboard` 在每个用例后把剪贴板所有权交还系统——**缺了它，offscreen 平台下 `QClipboard.setMimeData` 会在解释器析构时崩成 0xC0000005**。 |
| `test_face.py` | 26 项：rig 覆盖全部五官且与原画匹配、虹膜落在眼框内、反向（上下颠倒）标定被拒绝、每只眼都能切出睫毛与虹膜、中性姿态等于原图本身、合成漂移小、眨眼只动眼区、视线只在眼区内移动、张嘴只动嘴、`face_for` 有缓存、渲染保留 dpr、缺 rig 时回退、时钟自主眨眼并回到睁开、关掉活灵活现后不眨、翻译中张嘴、视线跟随与漂移、openness 曲线先快后慢、30 fps 下必然存在闭眼帧、控件动画不画到自身之外、点击触发眨眼、spec 确实带上 rig sidecar、**复用画布不继承上一帧的比值**、**动画帧仍显示完整头像**。 |
| `test_selection_monitor.py` | 默认只做划词、非 Windows 为 no-op、左键任意处只上报一次、拖动仍触发选区、暂停时仍上报按下、暂停不吞掉下一次按下、位图快照能原样放回、**截图在"没有文字"的捕获后幸存**、**序号变了就不许覆盖剪贴板**、截图工具的拖拽不触发挥窗。 |
| `test_selection_popup.py` | 浮窗定位与内容、框外点击关闭而框内点击不关、隐藏状态下点击被忽略。 |
| `test_ui.py` | `Pet` 与 `SettingsDialog` 的行为，以及**"不许有全局快捷键"守卫**（源码里不得出现 `RegisterHotKey` / `Ctrl+Alt`）。 |
| `test_worker.py` | `Worker` 线程的信号与完成/失败路径。 |
| `test_translation.py` | 分批、响应解析、错误与取消。 |
| `test_terminology.py` | 内置术语覆盖常用通信词、`sanitize` 去解码残留、离线更正表命中已知误译、**用户术语覆盖内置更正**、离线引擎端到端套用更正、真实模型输出正确术语。 |
| `test_ocr.py` | 双栏保持分离且左→右阅读、连字断行拼接不加空格、空白与非英文噪声被忽略、空 OCR 结果的清洗。 |
| `test_offline.py` | 用真实模型翻译一段学术样例。 |

## `models/` —— 离线模型（不入版本控制）

`models/translate-en_zh-1_9/` 是 Argos Open Technologies 打包的 OPUS-MT 英中模型
（CC-BY 4.0，作者 Jörg Tiedemann 与 Santhottan Thottingal），共 8 个文件约 85.6 MB，
其中 `model/model.bin` 单个 82.7 MB。

它**足够大，会主导仓库体积**（提交进 Git 会让 `.git` 膨胀到约 70 MB），所以不随仓库分发：

```powershell
python scripts\fetch_model.py          # 下载并解压到 models/translate-en_zh-1_9
python scripts\fetch_model.py --check  # 只检查是否已安装
```

开发、测试与 `scripts/build.ps1` 都要求它先就位；打包时由 `ScholarPet.spec` 送进 `_internal/models`。

## `docs/` —— 开发记录

| 文件 | 说明 |
| --- | --- |
| `PROGRESS.md` | 四轮开发的完整记录：每个 bug 的**症状、根因、测量方法与反向验证**。修过的问题包括画布复用导致的设备像素比泄漏（脸被放大裁切）、剪贴板被清空导致截图无法粘贴、offscreen 下剪贴板析构崩溃、构建退出码被 `Write-Output` 吞掉等。排查同类问题的第一站。 |
| `frozen-selftest.json` | 最近一次冻结自检的原始输出。 |
| `face-layers.png`、`face-rig.png`、`face-preview*.png`、`face-blink*.png` | 面部绑定的层级拆分、标注框与各姿态预览。 |
| `pet-widget-strip.png` | 控件级逐帧预览（含"同一姿态连画两帧"的对照帧）。 |

## `dist/` —— 构建产物（不入版本控制）

`dist/ScholarPet/`（约 474 MB，onedir）与 `dist/ScholarPet-Windows-x64.zip`（约 226 MB）。
`ScholarPet.exe` 只有 7.4 MB，是**启动器**；真正的运行时——PySide6、`python312.dll`、
OpenCV(`cv2` 117 MB)、`models`(85 MB)、ctranslate2、onnxruntime——都在同级的 `_internal/` 里。
**因此不能只把 exe 发给别人**，分发方式见 README 的「分发给别人」一节。

## 运行本项目所需的其它位置

| 位置 | 说明 |
| --- | --- |
| `..\ieee-skill-github\work\.venv` | 开发与构建用的虚拟环境，**不属于项目目录**，也不入版本控制（`.gitignore` 已忽略 `.venv/`）。 |
| `%LOCALAPPDATA%\ScholarPet` | 运行时写入的设置与加密密钥（`settings.json`）。可用 `SCHOLARPET_DATA_DIR` 改到别处——测试就是这么隔离的。 |
