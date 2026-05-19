param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if ($Clean) {
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install -e .
py -3.11 -m pip install pyinstaller
py -3.11 -m unittest discover -s tests
py -3.11 -m PyInstaller packaging/Boogart.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path "dist/Boogart.exe")) {
    throw "PyInstaller finished but dist/Boogart.exe was not created"
}

Write-Host "Built dist/Boogart.exe"
