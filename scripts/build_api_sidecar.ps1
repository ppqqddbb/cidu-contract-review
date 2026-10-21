$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$outputDir = Join-Path $repoRoot 'apps\desktop\src-tauri\binaries'
$workDir = Join-Path $repoRoot '.build\pyinstaller'

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到打包所需的 Python 虚拟环境：$python。请先执行 uv sync --all-groups。"
}

New-Item -ItemType Directory -Force -Path $outputDir, $workDir | Out-Null

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name contract-review-api `
    --paths (Join-Path $repoRoot 'services\api') `
    --collect-all fitz `
    --collect-all PIL `
    --collect-all docx `
    --hidden-import multipart `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --distpath $outputDir `
    --workpath $workDir `
    --specpath $workDir `
    (Join-Path $repoRoot 'services\api\sidecar.py')

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$sidecar = Join-Path $outputDir 'contract-review-api.exe'
if (-not (Test-Path -LiteralPath $sidecar)) {
    throw "未生成 FastAPI 伴随程序：$sidecar"
}

Get-Item -LiteralPath $sidecar | Select-Object FullName, Length, LastWriteTime
