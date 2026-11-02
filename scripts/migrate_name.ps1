# One-time upgrade from the project's old name "Capricon" to "Capricorn".
# Renames capricon-data -> capricorn-data and replaces old Capricon.lnk shortcuts.
# The launcher .bat files run this automatically only while an old capricon-data folder exists.
$repo = Split-Path -Parent $PSScriptRoot
$old = Join-Path $repo "capricon-data"
$new = Join-Path $repo "capricorn-data"

if ((Test-Path $old) -and -not (Test-Path $new)) {
    # The old version must not be running (it keeps files in the folder open).
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'" |
        Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 800
    try {
        Rename-Item -LiteralPath $old -NewName "capricorn-data" -ErrorAction Stop
        Write-Host "[ OK ] Renamed capricon-data -> capricorn-data"
    } catch {
        Write-Host "[WARN] Couldn't rename capricon-data yet ($($_.Exception.Message)). It keeps working under the old name."
    }
}

foreach ($where in @("Startup", "Desktop")) {
    $oldLnk = Join-Path ([Environment]::GetFolderPath($where)) "Capricon.lnk"
    if (Test-Path $oldLnk) {
        Remove-Item -LiteralPath $oldLnk -Force -ErrorAction SilentlyContinue
        if (Test-Path (Join-Path $new "python\Scripts\pythonw.exe")) {
            & (Join-Path $PSScriptRoot "make_shortcut.ps1") -Where $where
        }
    }
}
