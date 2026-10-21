$ErrorActionPreference = 'Stop'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '..\.uv-cache'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Checked { uv run ruff check . }
Invoke-Checked { uv run mypy services }
Invoke-Checked { uv run pytest }
Invoke-Checked { uv run python scripts/validate_contracts.py }
Invoke-Checked { uv run python scripts/export_openapi.py }
Invoke-Checked { pnpm.cmd format:check }
Invoke-Checked { pnpm.cmd typecheck }
Invoke-Checked { pnpm.cmd test }
Invoke-Checked { pnpm.cmd build }
