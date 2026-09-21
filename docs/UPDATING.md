# 更新与发版

这份文档写给"代码改完之后要做什么"。每一步都可以单独执行，也可以一口气跑完。

## 一、日常改代码：改 → 测 → 提交 → 推送

```powershell
$GIT = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd\git.exe"
$P   = "C:\Users\SherryAlbert\Documents\Codex\2026-09-20\ieee-skill-github\outputs\ScholarPet"

# 1. 跑测试（约 2 分钟；改的是界面就重点看 tests/test_selection_popup.py）
& "..\..\work\.venv\Scripts\python.exe" -m pytest -q

# 2. 看看到底改了什么，确认没有多出不该提交的文件
& $GIT -C $P status --short

# 3. 提交 + 推送
& $GIT -C $P add -A
& $GIT -C $P commit -m "fix: 描述这次改了什么"
& $GIT -C $P push
```

> 本机 `git` 不在 PATH，所以上面用的是绝对路径。`$GIT` 那份是 Visual Studio 2022 自带的
> 2.40.1，实测能正常连 GitHub；WorkBuddy 的 PortableGit 也能用，但需要额外把
> `mingw64\bin` 加进 PATH（否则报 `'remote-https' is not a git command`）。
> 装了 Git for Windows 或 GitHub Desktop 的话，直接用它们更省事。

**提交信息建议用 `feat:` / `fix:` / `docs:` / `chore:` 开头**，这样 GitHub 的提交列表一眼能看出改动性质。

## 二、要发新版了：改版本号 → 打包 → 提交 → 建 Release

### 1. 先把版本号改掉（3 处，缺一不可）

| 文件 | 位置 | 说明 |
|---|---|---|
| `scholarpet/__init__.py` | `__version__ = "0.5.0"` | **权威来源**，程序内部读它 |
| `scholarpet/settings.py` | 设置页那行 `研译 ScholarPet 0.5.0 · 灰原哀版` | 界面显示，目前是写死的 |
| `README.md` | 「项目状态」小节 | 给人看的版本说明 |

只改前两处不会崩，但用户会比较困惑：界面写着 0.6.0、README 写着 0.5.0。

### 2. 重新打包

```powershell
cd "C:\Users\SherryAlbert\Documents\Codex\2026-09-20\ieee-skill-github\outputs\ScholarPet"
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

`build.ps1` 会自动依次做完这些事，中途任何一步失败都会直接中断：

1. 删掉旧的 `build\` 和 `dist\`
2. 清理 PATH 里会污染 Qt 的原生运行时目录，把解释器自己的 `DLLs` 提到最前
3. 跑全部单元测试（当前 **84 个**）
4. PyInstaller 按 `ScholarPet.spec` 打包成 `dist\ScholarPet\`
5. 校验包内没有 ICU 污染、OpenSSL 与解释器一致（这三层防护见 README）
6. 收集第三方许可、把 README / LICENSE / THIRD_PARTY_NOTICES 拷进包
7. **在打包好的 exe 里**跑一遍冻结自检（10 项，真的加载 Qt / 离线模型 / OCR）
8. 压缩成 `dist\ScholarPet-Windows-x64.zip`

产物就是这一个文件：

```
dist\ScholarPet-Windows-x64.zip       约 215 MB
```

> 打包依赖 `..\..\work\.venv`（559 MB）。**不要删它**，删了 build.ps1 第 5 行会直接
> `throw`。真要重建：`python -m venv ..\..\work\.venv` 再装 `requirements-dev.txt`。

### 3. 提交并推送

```powershell
& $GIT -C $P add -A
& $GIT -C $P commit -m "chore: bump version to 0.6.0"
& $GIT -C $P push
```

`dist/` 在 `.gitignore` 里，**压缩包不会被提交**——它走 Release 附件，不走仓库。

### 4. 建新的 Release

1. 打开 <https://github.com/sherryalbert/ScholarPet/releases/new>
2. **Tag** 填新版本号（如 `v0.6.0`）→ 点 **Create new tag**（tag 必须和上一步的版本号一致）
3. **Title** 填 `ScholarPet v0.6.0`
4. 把 `dist\ScholarPet-Windows-x64.zip` 拖进附件框
5. 描述里写这次改了什么（可以复用 `docs/` 里的说明）
6. 点 **Publish release**

**每次发新版都新建一个 tag**，不要改旧的 Release —— 旧版本别人可能已经下载存档了，改动会让对方困惑。

## 三、绝对不能提交的东西

`.gitignore` 已经挡住了以下内容，**不要用 `git add -f` 强行加进去**：

| 路径 | 体积 | 为什么不能进仓库 |
|---|---|---|
| `dist/`、`build/` | 668 MB / 336 文件 | 编译产物，每个人的机器都能重新生成；GitHub 仓库会瞬间膨胀 |
| `models/translate-en_zh-1_9/` | 82 MB | 模型是 CC-BY 4.0，随仓库分发要单独标注；已有 `scripts/fetch_model.py` 按需下载 |
| `work/.venv/` | 559 MB | 虚拟环境，且含绝对路径，换台机器就废 |
| `__pycache__/` | 小 | 每次运行都变，提交了会无限累积无意义 diff |

判断标准很简单：**能靠脚本重新生成的东西都不该进 Git。** 仓库里只放"人写出来的东西"。

### 为什么 `dist/` 是"传不上去"而不是"不建议传"

拿这个项目实测的数字：

| 内容 | 体积 | GitHub 规则 | 结果 |
|---|---|---|---|
| `dist/ScholarPet-Windows-x64.zip` | **215.5 MB** | 单文件硬上限 **100 MB** | 推送直接被拒 |
| `dist/ScholarPet/_internal/cv2/cv2.pyd` | 82.3 MB | 同上 | 侥幸没超，但已在危险区 |
| `dist/ScholarPet/_internal/models/.../model.bin` | 78.9 MB | 同上 | 同上 |
| `dist/` 全部 336 个文件 | **668.3 MB** | 仓库建议 < 1 GB | 一次发版就吃掉大半配额 |
| 当前仓库（源码，60 文件） | 3.6 MB | — | 正常 |

三个后果，任何一个都足以否决这件事：

1. **推不上去。** GitHub 在服务端直接拒绝超过 100 MB 的文件，`git push` 报错退出，跟网络无关。
2. **就算能推，仓库会废掉。** Git 对二进制文件不做增量存储 —— 每次重新打包，668 MB **完整地再存一遍**。
   发 3 个版本就是 2 GB，别人 `git clone` 要下 2 GB，没人愿意。
3. **已有的 Release 已经解决了这个问题。** Release 附件不受仓库大小限制（单文件 2 GB），
   下载走的也是独立通道，不占用 clone 体积。**软件就该走 Release。**

> Git LFS 也救不了：GitHub 免费额度是 1 GB 存储 + 1 GB/月流量，
> 一个 215 MB 的包被下载 5 次就超额，之后链接直接返回错误。

## 四、派生产物要跟着代码一起更新

改完这些地方，记得重跑对应脚本，否则仓库里的图会过期：

| 改了什么 | 重新生成 |
|---|---|
| 界面布局（`views.py` / `pet.py` / `settings.py`） | `python scripts\preview_ui.py` → `docs/ui-*.png` |
| 面部骨骼（`assets/haibara_head.rig.json`） | `python scripts\preview_face.py`、`scripts\calibrate_face.py` |
| 依赖版本（`requirements*.txt`） | `python scripts\collect_licenses.py` → `THIRD_PARTY_NOTICES.md` |

## 五、常见故障

**`git: 'remote-https' is not a git command`**
用的是 WorkBuddy 里那份精简 PortableGit，且 PATH 里没有 `mingw64\bin`。换 VS2022 那份，
或把 `...\PortableGit\...\mingw64\bin` 加进 PATH。

**`Failed to connect to 127.0.0.1 port 7890`**
旧的全局代理配置。现在 `http.proxy` 已改为实际在用的 `127.0.0.1:7897`（Clash Verge）。
换代理软件后端口会变，用 `git config --global --get http.proxy` 核对，然后
`git config --global http.proxy http://127.0.0.1:<新端口>` 更新。

**`git status` 显示 `main...origin/main [gone]`**
本地缺 `refs/remotes/origin/main` 这个引用文件。跑一次 `git fetch origin` 即可，
不影响远端内容。

**推送时弹浏览器要授权**
Git Credential Manager 在取 GitHub 凭据，点 Authorize 即可；凭据存在 Windows 凭据管理器里，
之后不用重复登录。

**打包启动报 `ImportError: DLL load failed while importing QtCore`**
PATH 里混进了外来运行时（如 `codex-runtimes\...\native\`）的 DLL。`build.ps1` 已自动清理，
如果手工调 PyInstaller 就会踩到。
