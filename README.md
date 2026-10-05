# 存钱罐（SaveMoneyApp）

一个本地优先的记账 + 存钱目标管理应用。同一套代码，可以打包成 **Windows 桌面软件** 和
**Android 手机 App**。

数据全部保存在本机 SQLite 文件里，不上传任何服务器；跨设备迁移靠「导出备份 / 导入备份」。

---

## 现在能做什么（第一阶段 MVP）

| 页面 | 功能 |
| --- | --- |
| **首页仪表盘** | 总存款大字展示；本月收入 / 支出 / 结余 / 储蓄率；可回看任意月份；存钱目标卡片（进度条、已存 / 目标、差额、截止日期、每月建议存入）；最近流水速览 |
| **记一笔** | 收入 / 支出切换；金额输入（手机唤起数字键盘）；分类下拉（带图标颜色）；备注；日期选择；快捷金额；可一键把该笔金额存入某个存钱目标 |
| **流水列表** | **曲线图**（该月每天结束时的存款趋势）+ **饼图**（收入 / 支出按分类构成），两张图随流水实时刷新；按时间倒序列表，收入绿色、支出红色；按月 / 全部筛选；该时段收支汇总；点击单条可编辑或删除（删除二次确认） |
| **设置** | **初始财产**录入与归 0；外观（深色 / 浅色切换）；存钱目标增删改 + 存入 / 取出；收支分类增删改；导出数据库(.db) / 导出流水(.csv) / 导出目标(.csv) / 导入备份；**清空所有数据**；数据文件位置与版本信息 |

底部导航 4 个标签：**首页仪表盘 ｜ 记一笔 ｜ 流水列表 ｜ 设置**

### 初始财产（第一次使用）

第一次打开应用时，可以在 **设置 → 初始财产** 把手里的钱录进去：

```
总存款 = 初始财产 + 所有收入 − 所有支出
```

这样刚装好应用就能看到真实家底，而不是从 0 开始。要点：

* 默认是 0，所以不设置的用户行为和以前完全一样；
* 允许负数（例如有信用卡欠款）；
* **只影响"起点金额"，不产生任何流水**，随时可以改或归 0；
* **设置 → 清空数据** 会把流水、目标、自定义分类和初始财产一起归 0；
* 存在 `settings` 键值表里，不需要给数据库加字段，老数据文件直接可用。

### 实时图表（流水页）

流水页顶部有两张图，**每次记一笔 / 改一笔 / 删一笔都会自动重算并刷新**，
全部本地计算，不需要联网：

| 图表 | 内容 |
| --- | --- |
| **曲线图** | 该月**每天结束时的存款**（含初始财产与往日结余），没有流水的日子沿用前一天的值，曲线连续 |
| **饼图** | 该月**按分类的构成占比**（圆环 + 图例），可切换看「支出」或「收入」 |

图表颜色统一取自 [apps/_shared/theme.py](apps/_shared/theme.py) 的 `CHART_PALETTE`，
坐标轴与网格线跟随明暗主题。

### 界面风格

苹果式的**半透明毛玻璃**质感：

* 整页背景是**纯色**，跟着主题走（深色主题深底、浅色主题浅底），不放装饰元素；
* 卡片是半透明白底 + 1px 高光描边 + 柔和投影，叠在纯色背景上形成玻璃层次；
* 底部导航栏是悬浮的半透明玻璃条，内容滚动时会从下面透出来；
* 页面用 iOS 风格的大标题，不再占用顶部工具栏；
* 输入框、下拉框、按钮统一**圆角**（14px），没有直角；
* 文字颜色严格跟随主题：浅色主题用深色字、深色主题用浅色字，保证看得清；
* 深色是默认模式（毛玻璃在深色下最明显），首页右上角或**设置 → 外观**可切换，
  选择会记住。

> 想调整观感，改 [apps/_shared/theme.py](apps/_shared/theme.py) 顶部的颜色常量即可：
> 毛玻璃浓度在"毛玻璃材质"那一段，圆角在 `FIELD_RADIUS` / `BUTTON_RADIUS`，
> 背景色在 `BG_SOLID_DARK` / `BG_SOLID_LIGHT`。


---

## 虚拟环境（venv）

项目自带专用虚拟环境 **`.venv`**（Python 3.12.10，约 190 MB），
与系统 Python 完全隔离，已装好：`flet` 0.28.3、`flet-cli`、`flet-desktop`、
`flet-web`、`Pillow`、`PyInstaller`。

### 进入虚拟环境

**PowerShell**（推荐）：

```powershell
cd D:\project\save-money-app

# 如果提示"禁止运行脚本"，先对当前窗口放宽一次（只影响这个窗口）
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\.venv\Scripts\Activate.ps1
```

激活成功后提示符会变成 `(venv)`，`python` 指向 `.venv`。退出：

```powershell
deactivate
```

**想省事**：双击 `shell.ps1`，会直接开一个已经激活好虚拟环境的 PowerShell 窗口。

**cmd.exe**：

```cmd
cd /d D:\project\save-money-app
.venv\Scripts\activate.bat
```

### 不想激活也行

不激活完全不影响使用，直接调用解释器即可（项目里所有文档和脚本都是这么写的）：

```powershell
.venv\Scripts\python.exe scripts\dev_run.py
```

> 注意：**不要**直接敲 `python xxx.py` —— 那会用系统 Python，
> 里面没有装 flet，会报 `ModuleNotFoundError`。

### 关于本项目 venv 的一个特殊之处

这个 venv 是用 `scripts/install_deps.py` 把包**直接装进
`.venv\Lib\site-packages`** 建起来的（因为受限环境下 `ensurepip` 不可用，
详见 [docs/环境搭建.md](docs/环境搭建.md)）。因此 `Scripts\` 里没有
`pip.exe`，激活脚本也是手工补的：

| 文件 | 用途 |
| --- | --- |
| `Scripts\python.exe` | 本环境的解释器（一直可用） |
| `Scripts\Activate.ps1` | PowerShell 激活 |
| `Scripts\activate.bat` | cmd 激活 |
| `Scripts\deactivate.ps1` / `.bat` | 退出 |

`python -m pip ...` 是可用的（pip 作为模块存在于 site-packages）。

---

## 快速开始

```powershell
# 1) 环境已经建好（.venv 就在项目里）。若要重建：
#    python -m venv .venv
#    python scripts\install_deps.py -r requirements-desktop.txt

# 2) 跑业务逻辑测试（纯数据，无界面）
.venv\Scripts\python.exe tests\run_tests.py

# 3) 启动界面（带热重载：改完代码保存，自动重启看效果）
.venv\Scripts\python.exe scripts\dev_run.py                 # 桌面窗口
.venv\Scripts\python.exe scripts\dev_run.py --web           # 浏览器预览 :8550
.venv\Scripts\python.exe scripts\dev_run.py --target mobile --web --port 8551   # 手机端布局
.venv\Scripts\python.exe scripts\dev_run.py --demo          # 顺便造一批演示数据
```

也可以直接双击 **`start.bat`**（自动检查环境并启动）：

```
start.bat                  桌面窗口 + 热重载
start.bat desktop web      浏览器预览
start.bat mobile web       手机端布局预览
```

**验证状态**（本次交付时实测）：

| 检查项 | 命令 | 结果 |
| --- | --- | --- |
| 业务逻辑 | `tests\run_tests.py` | 111 用例全部通过 |
| 页面渲染 | `scripts\check_ui.py` | 4 个页面全部通过 |
| 弹窗交互 | `scripts\check_dialogs.py` | 9 项全部通过 |
| 热重载 | `scripts\dev_run.py` | 改文件后自动重启并恢复服务 |


应用内数据默认放在：

| 平台 | 数据目录 |
| --- | --- |
| Windows | `%APPDATA%\SaveMoneyApp\pocket_money.db` |
| macOS | `~/Library/Application Support/SaveMoneyApp/` |
| Linux | `~/.local/share/SaveMoneyApp/` |
| Android | 应用私有数据目录（Flet 的 `FLET_APP_STORAGE_DATA`） |

开发期加 `--dev` 会把数据放到项目内 `.devdata/`，方便随时删掉重来。

### 清空数据 / 造演示数据

```powershell
# 查看当前有多少数据（不改动）
.venv\Scripts\python.exe scripts\reset_data.py --status --all

# 清空正式数据（%APPDATA%\SaveMoneyApp）：流水、目标、自定义分类
.venv\Scripts\python.exe scripts\reset_data.py --clear

# 清空开发数据（.devdata 与 .devdata/mobile）
.venv\Scripts\python.exe scripts\reset_data.py --clear --dev --mobile

# 想先看看界面效果时，清空并造一批演示数据
.venv\Scripts\python.exe scripts\reset_data.py --clear --all --demo
```

清面前会自动导出一份快照到备份目录，清错了可以在「设置 - 导入备份」里恢复。
应用内也能清：**设置 → 清空数据 → 清空所有数据**。

---

## 目录结构（一眼看懂）

```
save-money-app/
├── core/                  【共享核心】与界面无关，桌面端和手机端共用
│   ├── models.py            数据模型（流水、分类、目标、统计结果）
│   ├── errors.py            统一业务异常
│   ├── bootstrap.py         启动引导：import 路径 + 数据库初始化
│   ├── db/                  数据访问层（SQLite）
│   │   ├── connection.py        连接管理、事务、热备份
│   │   ├── schema.py            建表、版本迁移、预置分类
│   │   └── repositories/        每张表一个仓储：增删改查 + 校验
│   ├── services/            业务逻辑层：所有"钱怎么算"都在这里
│   │   ├── stats_service.py     总存款、月度收支、储蓄率、趋势
│   │   ├── goal_service.py      目标进度、每月建议存入公式
│   │   ├── backup_service.py    导出 / 导入 / CSV
│   │   └── settings_service.py  应用配置读写
│   └── utils/               工具：金额(Decimal)、路径、临时目录兼容
│
├── apps/                  【两个前端】各自一个入口，界面代码共用
│   ├── _shared/              共享 UI（两端引用同一份）
│   │   ├── theme.py             颜色 / 尺寸 / 明暗主题
│   │   ├── shell.py             底部导航 4 标签外壳
│   │   ├── components.py        可复用小组件
│   │   └── views/               四个页面 + 两个编辑弹窗
│   ├── desktop/app_entry.py  桌面端入口（窗口尺寸、数据目录）
│   └── mobile/app_entry.py   手机端入口（全屏、应用私有目录）
│
├── tests/                 【测试】第一步的业务逻辑测试，111 个用例
├── scripts/               【开发脚本】装依赖、热重载、自检、演示数据
├── docs/                  【文档】环境搭建 / 目录结构 / 开发路线
├── assets/                【静态资源】打包用的图标（见 assets/README.md）
├── config/pip.ini         国内镜像等本机配置
├── start.bat              一键启动（自动检查环境）
├── requirements.txt       运行依赖（flet）
├── requirements-desktop.txt  桌面窗口 / 浏览器预览额外依赖
└── .venv/                 专用虚拟环境（不进版本库）
```

更详细的说明见 [docs/目录结构.md](docs/目录结构.md)。

---

## 开发约定（重要）

1. **算钱只在 `core/services`**。界面里不允许出现金额公式，只做展示，
   这样桌面端和手机端的结果永远一致。
2. **金额一律用 `Decimal`**，数据库以文本存十进制字符串，避免浮点误差累加。
   所有金额文本都走 `utils.money.format_money()`，统一千分位和两位小数。
3. **校验错误统一抛 `errors.AppError` 子类**，界面层 `except AppError` 一条就够，
   异常消息本身就是给用户看的中文提示。
4. **改数据结构要升版本号**：`core/db/schema.py` 里的 `SCHEMA_VERSION` + `MIGRATIONS`，
   保证老用户的数据库升级时不丢数据。
5. 新增页面放在 `apps/_shared/views/`，继承 `BaseView`，实现 `load()` 和 `render()`；
   数据变更后调用 `self.changed("提示语")` 触发刷新。

---

## 已实现 vs 待开发

✅ **第一阶段（MVP）**：记账、看存钱进度、备份迁移 —— 已完成

🟡 **第二阶段**：
- 预算管理（分类月度预算、首页剩余额度、超支橙红提醒）
- 统计图表（月度支出饼图、存款增长折线图，用 Flet 自带图表组件）
- 本地密码锁（哈希保存，不存明文）
- 模板录入（工资等固定收支一键记账）

🟢 **第三阶段**：
- 预算预警提示、月度报表导出
- 多账户分离（银行卡 / 现金分开统计）

数据库里已经预留了 `budgets`、`templates`、`accounts` 三张表，
第二阶段开发不需要改结构。详见 [docs/开发路线.md](docs/开发路线.md)。

---

## 打包成独立软件

### 桌面端（已实测可用）

```powershell
.venv\Scripts\python.exe scripts\build_desktop.py            # 直接打包
.venv\Scripts\python.exe scripts\build_desktop.py --clean    # 先清旧产物
.venv\Scripts\python.exe scripts\build_desktop.py --console  # 保留控制台窗口，排查启动问题
```

产出：`dist\Flipped的存钱罐\Flipped的存钱罐.exe`

| 项目 | 数值 |
| --- | --- |
| 主程序 | 8 MB |
| 整个目录 | 约 130 MB（含内置的 Flet 桌面客户端 95 MB） |
| 依赖 | **不需要装 Python**，双击即用 |
| 数据位置 | `%APPDATA%\SaveMoneyApp` |

**换电脑时把整个 `dist\Flipped的存钱罐` 目录拷过去**（不能只拷 exe，
它依赖同目录的 `_internal`）。

用的是 PyInstaller 而不是 `flet build windows`：后者要先下载约 1GB 的
Flutter SDK 再用 Flutter 重新编译，产物更小更"正规"；PyInstaller 只需
pip 装一个包、一分钟出结果，适合"先要个能双击运行的 exe"。

有个坑记一下：**必须把 `flet_desktop` 自带的桌面客户端一起打包**
（脚本里已处理）。漏了它，exe 启动时会去 `~/.flet` 下载解压，
用户目录不可写就直接崩。

### 手机端（Android APK）

详细步骤见 **[docs/打包指南.md](docs/打包指南.md)**（含工具链位置、常见坑与排查）。

简版（工具链已备在 `.toolchain/`，约 3.5 GB）：

```powershell
# 1) 安装 Android 平台包与构建工具（约 300MB）
.venv\Scripts\python.exe scripts\setup_android_toolchain.py

# 2) 检查工具链
.venv\Scripts\python.exe scripts\setup_android_toolchain.py --check

# 3) 打包
.venv\Scripts\python.exe scripts\build_apk.py
```

产物在 `build\apk\app-release.apk`。

> ⚠️ **在受限沙箱环境里打不出 APK**：Dart（Flutter 运行时）无法派生子进程
> （`Process.runSync` 报 `拒绝访问 / CreateFile failed 5`），而 Flutter 构建
> 全程依赖子进程。这是环境边界，不是配置问题。**在正常电脑上没这个限制。**

图标与桌面端共用：`assets/icon.png`（Flet 打包默认读取）。

---

## 应用图标

图标由汤姆猫那张水彩画生成：

```powershell
.venv\Scripts\python.exe scripts\prepare_brand_icon.py
.venv\Scripts\python.exe scripts\prepare_brand_icon.py --source "D:\...\你的图.jpg"
```

产出（`assets/branding/`）：

| 文件 | 用途 |
| --- | --- |
| `app_icon_rounded.png` | 圆角方形 1024px，**实际使用的图标** |
| `app_icon.png` | 方形 1024px，备用 |
| `app_icon.ico` | 多尺寸 ico，Windows 快捷方式与 exe 图标 |
| `icon_preview.png` | 预览（1024/128/64/32，检查小尺寸是否还认得出） |

同时会输出到 `assets/icon.png` 与 `assets/icon.ico`，因为
`flet build` 默认读这两个位置。

**关于"把猫抠出来"**：试过两种抠图思路都不成立 —— 按"与背景色不同"会把
彩色天空当成前景；按"饱和度分离"则因为水彩画里猫的灰白毛、雪地、天空的
浅色区互相重叠，抠出来是一团糊。原图只有 1055px，猫只占约 250px，
硬抠再放大只会更糟。所以最终**直接用猫 + 日落背景的方形构图**当图标，
这本来就是一张完整好看的画。
