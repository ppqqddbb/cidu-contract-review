$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$projectRoot = Resolve-Path (Join-Path $repoRoot '..')
$outputDir = Join-Path $projectRoot '打包输出'
$portableResourcesDir = Join-Path $outputDir 'binaries'
$libreOfficeStage = Join-Path $repoRoot '.build\libreoffice'
$libreOfficeOutput = Join-Path $outputDir 'libreoffice'
$portableName = '合同智审-0.1.0-portable.exe'
$setupName = '合同智审-0.1.0-x64-setup.exe'
$backendName = 'contract-backend.exe'

function Resolve-LibreOfficeSource {
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:LIBREOFFICE_PATH)) {
        $candidates += $env:LIBREOFFICE_PATH
    }
    $candidates += @(
        'C:\Program Files\LibreOffice',
        'C:\Program Files (x86)\LibreOffice'
    )
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $resolvedItem = Resolve-Path -LiteralPath $candidate -ErrorAction SilentlyContinue
        if ($null -eq $resolvedItem) { continue }
        $resolved = $resolvedItem.Path
        $hasSoffice = Test-Path -LiteralPath (Join-Path $resolved 'program\soffice.com')
        $hasXmlReader = (Test-Path -LiteralPath (Join-Path $resolved 'program\xmlreaderlo.dll')) -or
            (Test-Path -LiteralPath (Join-Path $resolved 'program\xmlreaderdlo.dll'))
        if ($hasSoffice -and $hasXmlReader) {
            return $resolved
        }
    }
    throw '未找到完整的 LibreOffice 安装。请安装 64 位 LibreOffice，或设置 LIBREOFFICE_PATH 指向其安装目录。'
}

$libreOfficeSource = Resolve-LibreOfficeSource
New-Item -ItemType Directory -Force -Path $libreOfficeStage | Out-Null
if (!(Test-Path -LiteralPath (Join-Path $libreOfficeStage 'program\soffice.com'))) {
    Write-Output "复制 LibreOffice 运行库：$libreOfficeSource"
    Copy-Item -Path (Join-Path $libreOfficeSource '*') -Destination $libreOfficeStage -Recurse -Force
}
if (!(Test-Path -LiteralPath (Join-Path $libreOfficeStage 'program\soffice.com'))) {
    throw "LibreOffice 暂存失败：$libreOfficeStage"
}

New-Item -ItemType Directory -Force -Path $outputDir, $portableResourcesDir | Out-Null

$cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
$nsisBin = Join-Path $env:LOCALAPPDATA 'tauri\NSIS'
$backendSource = Join-Path $repoRoot 'services\api\dist\contract-backend.exe'
$pyinstallerCommand = Get-Command pyinstaller.exe -ErrorAction SilentlyContinue
$pyinstallerPath = $pyinstallerCommand.Source
if ([string]::IsNullOrWhiteSpace($pyinstallerPath)) {
    $knownPyInstaller = 'D:\File\Anaconda\envs\exe\Scripts\pyinstaller.exe'
    if (Test-Path -LiteralPath $knownPyInstaller) { $pyinstallerPath = $knownPyInstaller }
}
if (Test-Path -LiteralPath $cargoBin) { $env:PATH = "$cargoBin;$env:PATH" }
if (!(Test-Path -LiteralPath (Join-Path $nsisBin 'makensis.exe'))) {
    throw "未找到 NSIS：$nsisBin"
}
if ([string]::IsNullOrWhiteSpace($pyinstallerPath)) {
    throw '未找到 PyInstaller，无法重建后端程序'
}

Push-Location $repoRoot
try {
    Push-Location (Join-Path $repoRoot 'services\api')
    try {
        & $pyinstallerPath --clean --noconfirm contract-backend.spec
    }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (!(Test-Path -LiteralPath $backendSource)) {
        throw "PyInstaller 执行后仍未找到后端程序：$backendSource"
    }

    $vitePackage = Get-ChildItem -LiteralPath (Join-Path $repoRoot 'apps\desktop\node_modules\.pnpm') -Directory -Filter 'vite@*' |
        Select-Object -First 1
    if ($null -eq $vitePackage) { throw '未找到 apps/desktop 的 Vite 本地缓存，请先执行 pnpm.cmd --dir apps/desktop install' }
    Push-Location (Join-Path $repoRoot 'apps\desktop')
    try {
        node (Join-Path $vitePackage.FullName 'node_modules\vite\bin\vite.js') build
    }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    cargo build --release --offline --manifest-path apps/desktop/src-tauri/Cargo.toml
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & (Join-Path $nsisBin 'makensis.exe') scripts/contract-review-installer.nsi
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $releaseExe = Join-Path $repoRoot 'apps\desktop\src-tauri\target\release\contract-review-desktop.exe'
    $setupExe = Get-ChildItem -LiteralPath (Join-Path $repoRoot 'scripts') -Filter '*0.1.0-x64-setup.exe' -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if ($null -eq $setupExe) {
        throw "未找到 Tauri NSIS 安装包：$bundleDir"
    }

    Copy-Item -LiteralPath $releaseExe -Destination (Join-Path $outputDir $portableName) -Force
    Copy-Item -LiteralPath $backendSource -Destination (Join-Path $outputDir $backendName) -Force
    Copy-Item -LiteralPath $setupExe.FullName -Destination (Join-Path $outputDir $setupName) -Force
    if (Test-Path -LiteralPath $libreOfficeOutput) {
        Remove-Item -LiteralPath $libreOfficeOutput -Recurse -Force
    }
    Copy-Item -LiteralPath $libreOfficeStage -Destination $libreOfficeOutput -Recurse -Force

    Write-Output '桌面端打包完成：'
    Get-ChildItem -LiteralPath $outputDir -File |
        Where-Object { $_.Name -in @($portableName, $setupName) } |
        Select-Object FullName, Length, LastWriteTime |
        Format-Table -AutoSize
}
finally {
    Pop-Location
}
