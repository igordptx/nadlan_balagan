$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>$null
            if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Exe = 'py'; Prefix = @('-3') } }
        } catch { }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            & python -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>$null
            if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Exe = 'python'; Prefix = @() } }
        } catch { }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Python 3.11+ and winget are required.' }
    winget install --id Python.Python.3.13 -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    $python = Find-Python
    if (-not $python) { throw 'Python was installed. Open a new PowerShell window and rerun this script.' }
}

$systemTesseract = Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe'
$x86Tesseract = if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'Tesseract-OCR\tesseract.exe' } else { '' }
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue) -and
    -not (Test-Path $systemTesseract) -and -not ($x86Tesseract -and (Test-Path $x86Tesseract))) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Tesseract OCR or winget, then rerun.' }
    winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Tesseract installation failed.' }
}

$pythonExe = $python.Exe
$pythonPrefix = $python.Prefix
& $pythonExe @pythonPrefix -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $projectRoot '.browsers'
& $venvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium download failed.' }
& (Join-Path $PSScriptRoot 'sanity_windows.ps1')
Write-Host "Start with: $venvPython -m nadlan_balagan serve"
