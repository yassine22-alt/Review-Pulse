# ReviewPulse setup for Windows (PowerShell). Run from this folder:
#     .\setup.ps1              app + tests (vector plans: PDF, DXF, SVG)
#     .\setup.ps1 -Scans       also scanned plans (PyTorch CPU + PaddleOCR, about 2 GB more)
#     .\setup.ps1 -Python C:\path\to\python.exe     use this Python
# It creates .venv, installs ReviewPulse into it, then runs the self-check (rp doctor).
param([switch]$Scans, [string]$Python = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# A usable Python: version 3.11 or 3.12, and the python.org build (MSYS2 / MinGW Pythons cannot
# install most of the packages). Looked for in this order: -Python, the py launcher, python on the
# PATH, the standard install folders.
function Test-Python([string[]]$cmd) {
    try {
        $exe, $rest = $cmd
        $out = & $exe @rest -c "import sys, sysconfig; print('%d.%d' % sys.version_info[:2], sysconfig.get_platform())" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $false }
        $ver, $plat = "$out".Trim().Split(" ")
        return ($ver -in "3.11", "3.12") -and ($plat -like "win*")
    } catch { return $false }
}
$candidates = @()
if ($Python) { $candidates += , @($Python) }
foreach ($v in "3.11", "3.12") { $candidates += , @("py", "-$v") }
$candidates += , @("python")
foreach ($root in "$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}") {
    foreach ($v in "311", "312") { $candidates += , @("$root\Python$v\python.exe") }
}
$py = $null
foreach ($c in $candidates) { if (Test-Python $c) { $py = $c; break } }
if (-not $py) {
    Write-Host "Python 3.11 or 3.12 from python.org is needed. Install it from https://www.python.org/downloads/"
    Write-Host "(an MSYS2 or MinGW Python does not work), or point to it: .\setup.ps1 -Python C:\path\to\python.exe"
    exit 1
}
Write-Host "Using Python: $($py -join ' ')"

if (-not (Test-Path .venv)) { & $py[0] @($py | Select-Object -Skip 1) -m venv .venv }
$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -e ".[app,dev]"
if ($LASTEXITCODE -ne 0) { Write-Host "Installation failed: see the messages above."; exit 1 }

if ($Scans) {
    & $venvPy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    & $venvPy -m pip install -e ".[raster]"
    & $venvPy -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
}

Write-Host ""
& $venvPy -m reviewpulse.selfcheck
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host ""
Write-Host "Done. Next:"
Write-Host "  .\.venv\Scripts\Activate.ps1     (once per terminal)"
Write-Host "  rp serve                         then open http://127.0.0.1:8000"
Write-Host "  rp check path\to\plan.pdf        check a plan from the command line"
