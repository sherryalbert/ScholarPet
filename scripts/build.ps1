$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$pythonPath = Join-Path $projectRoot '..\..\work\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Project virtual environment not found: $pythonPath" }
$pythonPath = (Resolve-Path -LiteralPath $pythonPath).Path

# ---------------------------------------------------------------------------
# The interpreter this project uses lives inside the desktop runtime at
# ~/.cache/codex-runtimes/<id>/dependencies. That runtime publishes its vendored
# native packages (poppler, git, libheif ...) on the DLL search path, so
# PyInstaller resolves Qt's and OpenSSL's imports against those copies instead
# of the interpreter's own. Shipping them breaks QtCore at startup, so the
# native tree is scrubbed from PATH before the build and the interpreter's own
# DLL directory is pushed to the front.
# ---------------------------------------------------------------------------
$interpreterInfo = & $pythonPath -c "import json,sys;print(json.dumps({'base':sys.base_prefix}))" | ConvertFrom-Json
$interpreterDlls = Join-Path $interpreterInfo.base 'DLLs'
if (-not (Test-Path -LiteralPath $interpreterDlls)) { throw "Interpreter DLL directory not found: $interpreterDlls" }

$cleanPath = (($env:PATH -split ';') | Where-Object {
    $_ -and -not ($_ -match 'codex-runtimes' -and $_ -match '\\native\\')
}) -join ';'
$env:PATH = "$interpreterDlls;$($interpreterInfo.base);$cleanPath"
Write-Output "PATH prepared (native runtime directories removed, interpreter DLLs first)."

$popplerBin = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'
$poisonNames = @('icuuc.dll', 'icudt78.dll', 'icuin78.dll', 'icudt.dll', 'icuin.dll')

# PowerShell's Remove-Item -Recurse re-stats every path as it walks the tree.
# On a PyInstaller output (thousands of files, hundreds of MB) that takes
# minutes, produces no output, and reads exactly like a hung build. The .NET
# call removes the same tree in well under a second, so use it and keep
# Remove-Item only as a fallback for the odd read-only file.
foreach ($stale in @('build', 'dist')) {
    if (-not (Test-Path -LiteralPath $stale)) { continue }
    $target = (Resolve-Path -LiteralPath $stale).Path
    Write-Output "Removing stale $stale ..."
    try {
        [System.IO.Directory]::Delete($target, $true)
    } catch {
        Write-Output "  fast delete failed ($($_.Exception.Message)); falling back to Remove-Item."
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

& $pythonPath -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed (exit code $LASTEXITCODE)." }

# Pin pytest's scratch space inside build/ and pass --basetemp explicitly.
# Left to itself, pytest keeps numbered runs under %TEMP%\pytest-of-<user> and
# tidies the stale ones up with a bulk directory delete at the end of every
# session. Environments that gate bulk deletion answer that with a confirmation
# prompt instead, pytest counts the refusal as an error, and a fully green run
# exits 1 -- which reads as "Tests failed" and stops the build. An explicit
# basetemp skips the retention machinery altogether, and build/ is both
# gitignored and already wiped at the top of this script.
#
# The guard afterwards is `if ($LASTEXITCODE)` rather than `-ne 0` on purpose:
# an unset $LASTEXITCODE is $null and $null -ne 0 is *true* in PowerShell, so
# the `-ne 0` form can abort a build that actually succeeded.
#
# `build` has to exist first: pytest creates its basetemp with a non-recursive
# mkdir, so pointing at build\pytest-tmp while build\ is gone (this script
# deletes it above) fails every tmp_path test with FileNotFoundError.
if (-not (Test-Path -LiteralPath 'build')) {
    New-Item -ItemType Directory -Path 'build' -Force | Out-Null
}
& $pythonPath -m pytest -q --basetemp 'build\pytest-tmp'
if ($LASTEXITCODE) { throw "Tests failed (exit code $LASTEXITCODE)." }

& $pythonPath -m PyInstaller --noconfirm ScholarPet.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }

# ---------------------------------------------------------------------------
# Safety net: even if a hook re-adds a runtime DLL after Analysis, identical
# copies are removed here. Files are only deleted when their bytes match the
# runtime's own copy, so an unrelated binary of the same name is never touched.
# ---------------------------------------------------------------------------
function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

$internal = Join-Path $projectRoot 'dist\ScholarPet\_internal'
$pruned = @()
if (Test-Path -LiteralPath $internal) {
    foreach ($entry in Get-ChildItem -LiteralPath $internal -Recurse -File) {
        if ($entry.Name -notmatch '^icu.*\.dll$') { continue }
        $source = Join-Path $popplerBin $entry.Name
        if ((Test-Path -LiteralPath $source) -and ((Get-Sha256 $entry.FullName) -eq (Get-Sha256 $source))) {
            Remove-Item -LiteralPath $entry.FullName -Force
            $pruned += $entry.Name
        }
    }
}
if ($pruned.Count -gt 0) { Write-Output ("Pruned runtime-contaminated DLLs: " + ($pruned -join ', ')) }

$leftover = @(Get-ChildItem -LiteralPath $internal -Recurse -File -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -match '^icu.*\.dll$' })
if ($leftover.Count -gt 0) {
    throw ("ICU DLLs still present in the bundle: " + (($leftover | ForEach-Object { $_.Name }) -join ', ') +
           ". Qt cannot load reliably while the runtime's ICU copies shadow it.")
}

foreach ($name in @('libssl-3-x64.dll', 'libcrypto-3-x64.dll')) {
    $built = Get-ChildItem -LiteralPath $internal -Recurse -File -Filter $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $built) { throw "$name is missing from the bundle; HTTPS translation engines would fail." }
    $expected = Join-Path $interpreterDlls $name
    if ((Test-Path -LiteralPath $expected) -and ((Get-Sha256 $built.FullName) -ne (Get-Sha256 $expected))) {
        throw "$name was taken from a foreign runtime copy; rebuild after scrubbing PATH."
    }
}
Write-Output 'Bundle check passed: no runtime-contaminated ICU DLLs, OpenSSL matches the interpreter.'

& $pythonPath scripts/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
Copy-Item -LiteralPath README.md,LICENSE,THIRD_PARTY_NOTICES.md -Destination dist/ScholarPet/

# ---------------------------------------------------------------------------
# Frozen self-test: really loads Qt widgets, the offline model and the OCR
# engine inside the packaged executable. "The process stayed alive" is not
# enough evidence that a PyInstaller bundle works.
# ---------------------------------------------------------------------------
$report = Join-Path $env:LOCALAPPDATA 'ScholarPet\selftest.json'
if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report -Force }
$exe = (Resolve-Path 'dist\ScholarPet\ScholarPet.exe').Path
$process = Start-Process -FilePath $exe -ArgumentList '--selftest' -Wait -PassThru
if (-not (Test-Path -LiteralPath $report)) { throw "Frozen self-test produced no report (exit code $($process.ExitCode))." }
$result = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $result.results) {
    $mark = if ($item.ok) { 'PASS' } else { 'FAIL' }
    Write-Output ("  [{0}] {1} ({2}s) {3}" -f $mark, $item.check, $item.seconds, $item.detail)
}
if ($process.ExitCode -ne 0 -or -not $result.ok) { throw "Frozen self-test failed (exit code $($process.ExitCode))." }

# The frozen self-test has only just stopped using the executable, and a virus
# scanner commonly still has it open. Compress-Archive then reports "being used
# by another process" and fails a build whose executable is already finished and
# verified, which is what happened on build8. Retry briefly instead.
$archive = 'dist/ScholarPet-Windows-x64.zip'
for ($attempt = 1; $attempt -le 10; $attempt++) {
    try {
        Compress-Archive -Path dist/ScholarPet -DestinationPath $archive -Force -ErrorAction Stop
        break
    } catch {
        if ($attempt -eq 10) { throw }
        Start-Sleep -Milliseconds 700
    }
}
Write-Output 'Ready: dist/ScholarPet/ScholarPet.exe (frozen self-test passed)'
