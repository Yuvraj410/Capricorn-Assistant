# Puts Capricorn.exe (launcher\Capricorn.exe) into capricorn-data\python\Scripts, so Windows shows
# "Capricorn" with its icon in the taskbar and Task Manager instead of "Python".
# Re-points existing Startup / Desktop shortcuts at it. Safe to run every time (only copies when changed).
$repo = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repo "Capricorn.exe"
if (-not (Test-Path $src)) { $src = Join-Path $repo "launcher\Capricorn.exe" }
$dst = Join-Path $repo "capricorn-data\python\Scripts\Capricorn.exe"
if (-not (Test-Path $src) -or -not (Test-Path (Split-Path $dst))) { exit 0 }
$same = (Test-Path $dst) -and ((Get-FileHash $src).Hash -eq (Get-FileHash $dst).Hash)
if ($same) { exit 0 }
try { Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop } catch { exit 0 }   # in use: next time
foreach ($where in @("Startup", "Desktop")) {
    $lnk = Join-Path ([Environment]::GetFolderPath($where)) "Capricorn.lnk"
    if (Test-Path $lnk) { & (Join-Path $PSScriptRoot "make_shortcut.ps1") -Where $where | Out-Null }
}
