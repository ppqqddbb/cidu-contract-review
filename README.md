# 合同智审桌面端打包说明

本文记录 Windows 环境下如何把本项目打包为 Tauri 桌面程序。当前流程会生成一个 NSIS 安装包和一个便携版程序。

项目目录：

```powershell
D:\File\VSCodeFile\QDHB\cidu-contract-review
```

## 一、打包结构

打包流程如下：

```text
apps/desktop/app.js + styles.css + index.html
        |
        | Vite build
        v
apps/desktop/dist
        |
        | tauri-build + cargo build --release
        v
contract-review-desktop.exe

services/api/app
        |
        | PyInstaller
        v
contract-backend.exe
        |
        | NSIS
        v
合同智审-0.1.0-x64-setup.exe
```

桌面程序启动时会从自身目录查找 `contract-backend.exe`，并自动启动本地 API：

```text
http://127.0.0.1:8000
```

因此便携版必须将以下两个文件放在同一目录：

```text
合同智审-0.1.0-portable.exe
contract-backend.exe
```

安装包会自动把这两个文件安装到同一目录，不需要手动复制。

## 二、环境要求

建议使用以下工具：

```text
Windows 10/11 x64
Node.js 18 或更高版本
pnpm 10.6.5
Rust stable-x86_64-pc-windows-msvc
Cargo
NSIS
Python 3.10（当前打包环境为 D:\File\Anaconda\envs\exe）
PyInstaller 6.x
```

检查 Node、pnpm、Rust：

```powershell
node --version
corepack --version
pnpm --version
rustc --version
cargo --version
```

如果尚未启用 pnpm：

```powershell
corepack enable
corepack prepare pnpm@10.6.5 --activate
pnpm --version
```

如果尚未安装 Rust MSVC 工具链：

```powershell
rustup default stable-x86_64-pc-windows-msvc
rustup target add x86_64-pc-windows-msvc
```

当前脚本默认查找以下程序：

```text
PyInstaller：D:\File\Anaconda\envs\exe\Scripts\pyinstaller.exe
Cargo：      %USERPROFILE%\.cargo\bin
NSIS：       %LOCALAPPDATA%\tauri\NSIS\makensis.exe
```

如果 PyInstaller 安装在其他位置，请修改 `scripts/package_desktop.ps1` 中的 `$knownPyInstaller`。

## 三、首次安装前端依赖

在 PowerShell 中执行：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review'

pnpm.cmd install
pnpm.cmd --dir apps/desktop install
```

只安装桌面端依赖也可以：

```powershell
pnpm.cmd --dir apps/desktop install
```

## 四、一键打包（推荐）

这是完整打包命令：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review'

powershell.exe -ExecutionPolicy Bypass -File .\scripts\package_desktop.ps1
```

脚本会依次执行：

1. 使用 `services/api/contract-backend.spec` 重建后端。
2. 使用 Vite 构建 `apps/desktop/dist`。
3. 使用 Cargo 编译 Tauri 程序。
4. 使用 NSIS 生成安装包。
5. 将最终文件复制到上级目录的 `打包输出` 文件夹。

脚本等价于下面的手动流程。

## 五、手动完整打包命令

### 1. 设置目录和工具路径

```powershell
$repoRoot = 'D:\File\VSCodeFile\QDHB\cidu-contract-review'
$pyinstaller = 'D:\File\Anaconda\envs\exe\Scripts\pyinstaller.exe'
$nsis = "$env:LOCALAPPDATA\tauri\NSIS\makensis.exe"

Set-Location $repoRoot
```

### 2. 构建后端

必须在 `services/api` 目录执行 PyInstaller，因为 `contract-backend.spec` 使用当前目录作为模块搜索路径：

```powershell
Push-Location "$repoRoot\services\api"

& $pyinstaller --clean --noconfirm contract-backend.spec
if ($LASTEXITCODE -ne 0) {
    throw '后端 PyInstaller 打包失败'
}

Pop-Location
```

后端产物：

```text
services/api/dist/contract-backend.exe
```

`contract-backend.spec` 会额外收集以下运行时依赖：

```text
app.main
PyMuPDF / fitz
Pillow
python-docx
FastAPI / Uvicorn / HTTPX
libssl-3-x64.dll
libcrypto-3-x64.dll
zlib.dll
```

后端使用无控制台模式运行，因此 `services/api/app/__main__.py` 显式设置：

```python
log_config=None
access_log=False
```

这样可以避免无控制台程序中 `sys.stderr is None` 导致 Uvicorn 日志格式化器调用 `isatty()` 崩溃。

### 3. 安装并构建前端

```powershell
Set-Location $repoRoot

pnpm.cmd --dir apps/desktop install
pnpm.cmd --dir apps/desktop build
```

如果终端提示 `vite is not recognized`，可以直接调用本地 Vite：

```powershell
$vitePackage = Get-ChildItem `
    -LiteralPath "$repoRoot\apps\desktop\node_modules\.pnpm" `
    -Directory `
    -Filter 'vite@*' |
    Select-Object -First 1

if ($null -eq $vitePackage) {
    throw '没有找到本地 Vite'
}

Push-Location "$repoRoot\apps\desktop"
node "$($vitePackage.FullName)\node_modules\vite\bin\vite.js" build
Pop-Location
```

前端产物：

```text
apps/desktop/dist/index.html
apps/desktop/dist/assets/*
```

Vite 配置使用相对路径：

```text
base: "./"
```

这是为了让 Tauri 的 `tauri.localhost` 页面能够正确加载本地 HTML、JavaScript 和 CSS。

### 4. 编译 Tauri 桌面程序

```powershell
Set-Location $repoRoot

$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"

cargo build `
    --release `
    --offline `
    --manifest-path apps/desktop/src-tauri/Cargo.toml

if ($LASTEXITCODE -ne 0) {
    throw 'Tauri Cargo 编译失败'
}
```

产物：

```text
apps/desktop/src-tauri/target/release/contract-review-desktop.exe
```

前端资源通过 `apps/desktop/src-tauri/tauri.conf.json` 的配置嵌入：

```json
{
  "build": {
    "frontendDist": "../dist"
  }
}
```

### 5. 生成 NSIS 安装包

```powershell
Set-Location $repoRoot

& $nsis scripts/contract-review-installer.nsi

if ($LASTEXITCODE -ne 0) {
    throw 'NSIS 安装包生成失败'
}
```

NSIS 脚本会把以下两个文件安装到同一个目录：

```text
apps/desktop/src-tauri/target/release/contract-review-desktop.exe
services/api/dist/contract-backend.exe
```

NSIS 原始产物：

```text
scripts/contract-review-0.1.0-x64-setup.exe
```

### 6. 复制最终输出

```powershell
$outputDir = 'D:\File\VSCodeFile\QDHB\打包输出'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

Copy-Item `
    "$repoRoot\apps\desktop\src-tauri\target\release\contract-review-desktop.exe" `
    "$outputDir\合同智审-0.1.0-portable.exe" `
    -Force

Copy-Item `
    "$repoRoot\services\api\dist\contract-backend.exe" `
    "$outputDir\contract-backend.exe" `
    -Force

Copy-Item `
    "$repoRoot\scripts\contract-review-0.1.0-x64-setup.exe" `
    "$outputDir\合同智审-0.1.0-x64-setup.exe" `
    -Force
```

## 六、输出文件和运行方式

最终文件位于：

```text
D:\File\VSCodeFile\QDHB\打包输出
```

安装版现在会同时部署应用私有的 LibreOffice，安装后目录结构包含：

```text
%LOCALAPPDATA%\Programs\合同智审\contract-review-desktop.exe
%LOCALAPPDATA%\Programs\合同智审\contract-backend.exe
%LOCALAPPDATA%\Programs\合同智审\libreoffice\program\soffice.com
```

后端会优先使用上述私有 LibreOffice，不依赖目标电脑预装 LibreOffice，也不会与系统中其他版本混用。便携版运行时需要保持以下三个项目位于同一目录：

```text
合同智审-0.1.0-portable.exe
contract-backend.exe
libreoffice\
```

推荐运行安装版：

```powershell
Start-Process 'D:\File\VSCodeFile\QDHB\打包输出\合同智审-0.1.0-x64-setup.exe'
```

运行便携版时，两个文件必须在同一目录：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\打包输出'
Start-Process '.\合同智审-0.1.0-portable.exe'
```

不要只复制 `合同智审-0.1.0-portable.exe`，否则桌面程序找不到 `contract-backend.exe`，前端会显示 `Failed to fetch`。

## 七、后端健康检查

打包程序启动后，使用以下命令检查后端：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/health'
```

正常结果类似：

```text
status version
------ -------
ok     0.1.0
```

检查端口是否被占用：

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

## 八、开发模式运行

启动后端：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review\services\api'

$env:API_HOST = '0.0.0.0'
$env:API_PORT = '8000'
$env:API_RELOAD = 'false'

& 'D:\File\Anaconda\envs\exe\python.exe' -m app
```

另开一个 PowerShell 窗口启动前端：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review'

pnpm.cmd --dir apps/desktop dev
```

访问：

```text
http://127.0.0.1:1420
```

局域网内其他电脑访问时，将 `127.0.0.1` 换成本机局域网 IP，例如：

```text
http://192.168.1.20:1420
```

前端在未设置 `VITE_API_BASE_URL` 时会自动调用同一台主机的 `8000` 端口：
`http://192.168.1.20:8000`。如需手动指定 API 地址，可在启动前端前设置：

```powershell
$env:VITE_API_BASE_URL = 'http://192.168.1.20:8000'
```

如果其他电脑仍打不开，请在运行服务的 Windows 主机上放行端口：

```powershell
New-NetFirewallRule -DisplayName '合同智审 API 8000' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000
New-NetFirewallRule -DisplayName '合同智审 Web 1420' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1420
```

## 九、案例库数据库查询

在 `Law-Push` 中执行 `python .\run_filter.py 30`，分类完成后生成 `law.txt` 和
`case.csv`，并自动将 CSV 案例写入 PostgreSQL。相同标题和链接的案例不会重复插入。
导入失败保留 CSV，可执行 `python .\case_database.py .\case.csv` 单独重试。

桌面端“案例库”通过 `GET /api/v1/cases/database` 查询数据，打开页面或点击“刷新”
会重新查询。左侧按文件日期分组，右侧保留案例标题、来源、发布日期、摘要和原文链接。
页面无需上传、删除文件或手动同步，历史上传索引不再作为页面数据源。

后端 `services/api/.env` 中的 `CASE_DB_HOST`、`CASE_DB_PORT`、`CASE_DB_NAME`、
`CASE_DB_USER`、`CASE_DB_PASSWORD`、`CASE_DB_SCHEMA`、`CASE_DB_TABLE` 必须与
`Law-Push/kb_sync.local.json` 的 `database` 配置一致（其中 `CASE_DB_NAME` 对应 `database`）。
前端只访问 FastAPI，不保存数据库凭据。修改代码后重启后端并刷新前端，安装版需重新打包。

### 兼容旧版案例原件存储接口

当前案例库查询不会触发 Dify 知识库同步。以下上传接口仅为旧版客户端保留。

案例文件上传的链路为：桌面端 -> 本地合同审查 API -> 金蝶 Custom API -> 金蝶 `r8p0_law` 法律案例库实体及其 `r8p0_file` 附件。金蝶保存案例原件和档案信息，本地 `.data/cases/catalog.json` 仅保存案例展示索引。删除案例条目只删除本地索引，不删除金蝶法律案例库中的原件。此方案不新建独立业务表。

后端支持以下环境变量：

```powershell
$env:DIFY_BASE_URL = 'http://ciduai.daneng.cc/v1'
$env:DIFY_CONTRACT_TYPE_API_KEY = '你的合同分类 API Key'
$env:DIFY_CONTRACT_REVIEW_API_KEY = '你的合同审查 API Key'
$env:KINGDEE_CASE_STORAGE_URL = 'http://<金蝶服务地址>/ierp/kapi/v2/r8p0/bos/contract-review/legal-cases/file/store'

# OAuth（推荐）：后端每次上传前自动申请短期 token
$env:KINGDEE_CASE_STORAGE_TOKEN_URL = 'http://<金蝶服务地址>/ierp/kapi/oauth2/getToken'
$env:KINGDEE_CASE_STORAGE_CLIENT_ID = '<客户端 ID>'
$env:KINGDEE_CASE_STORAGE_CLIENT_SECRET = '<客户端密钥>'
$env:KINGDEE_CASE_STORAGE_USERNAME = '<金蝶用户名>'
$env:KINGDEE_CASE_STORAGE_ACCOUNT_ID = '<金蝶账号 ID>'

# 或使用静态令牌（临时联调，会过期）
# $env:KINGDEE_CASE_STORAGE_AUTHORIZATION = 'Bearer <金蝶 access-token>'
```

后端会自动读取 `services/api/.env` 与项目根目录的 `.env`。第一次配置可执行：

```powershell
Copy-Item '.\services\api\.env.example' '.\services\api\.env'
```

在 `JD/hvqfq` 项目中编译并发布 `LegalCaseStorageApi` 后，将其完整 HTTP 地址填入 `KINGDEE_CASE_STORAGE_URL`。本次新增接口路径为 `/contract-review/legal-cases/file/store`，接收 `caseId`、`fileName`、`contentType` 和 `contentBase64`，并返回 `storagePath` 与 `downloadUrl`。认证方式以金蝶接口发布配置为准；不要将凭据放进 `VITE_*`、桌面端代码或前端构建产物。

这些变量必须在启动后端之前设置。安装版后端会继承桌面程序启动时的用户环境变量。

## 十、清理后重新打包

需要完全清理构建缓存时执行：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review'

Remove-Item -LiteralPath 'apps\desktop\dist' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath 'services\api\dist\contract-backend.exe' -Force -ErrorAction SilentlyContinue

cargo clean --manifest-path apps\desktop\src-tauri\Cargo.toml

powershell.exe -ExecutionPolicy Bypass -File .\scripts\package_desktop.ps1
```

## 十一、常见问题

### `Unable to configure formatter 'default'`

这是旧版无控制台后端使用了 Uvicorn 默认日志配置。必须重新执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\package_desktop.ps1
```

不能继续使用旧的 `contract-backend.exe`。

### `Failed to fetch`

依次检查：

```powershell
Test-Path 'D:\File\VSCodeFile\QDHB\打包输出\contract-backend.exe'
Invoke-RestMethod 'http://127.0.0.1:8000/health'
```

如果第一个结果为 `False`，说明便携版缺少后端文件；如果第二个命令失败，说明后端没有正常启动或 `8000` 端口已被其他程序占用。

### 页面空白或仍然是旧页面

关闭旧程序，删除旧桌面快捷方式，卸载旧安装目录后，再运行最新安装包。不要从旧安装目录启动快捷方式。

### `vite is not recognized`

执行：

```powershell
pnpm.cmd --dir apps/desktop install
```

一键脚本也包含了本地 Vite 路径回退逻辑。

### `makensis.exe` 找不到

确认以下文件存在：

```powershell
Test-Path "$env:LOCALAPPDATA\tauri\NSIS\makensis.exe"
```

如果 NSIS 安装在其他目录，需要修改 `scripts/package_desktop.ps1` 中的 `$nsisBin`。

## 十二、版本更新时的顺序

修改前端后：

```powershell
pnpm.cmd --dir apps/desktop build
```

修改后端后：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review\services\api'
& 'D:\File\Anaconda\envs\exe\Scripts\pyinstaller.exe' --clean --noconfirm contract-backend.spec
```

修改 Tauri 配置或 Rust 代码后：

```powershell
cargo build --release --offline --manifest-path apps/desktop/src-tauri/Cargo.toml
```

通常直接重新执行一键打包即可：

```powershell
Set-Location 'D:\File\VSCodeFile\QDHB\cidu-contract-review'
powershell.exe -ExecutionPolicy Bypass -File .\scripts\package_desktop.ps1
```



# 启动前端
cd D:\File\VSCodeFile\QDHB\cidu-contract-review
pnpm.cmd --dir apps/desktop install
pnpm.cmd --dir apps/desktop dev


# 启动后端
cd D:\File\VSCodeFile\QDHB\cidu-contract-review\services\api
python -m app
