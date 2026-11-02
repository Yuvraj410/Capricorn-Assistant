# Creates a Capricorn shortcut (Startup folder or Desktop) that runs it hidden with pythonw.
param([ValidateSet("Startup", "Desktop", "StartMenu")] [string]$Where = "Startup")

$repo = Split-Path -Parent $PSScriptRoot
$pyw = Join-Path $repo "capricorn-data\python\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { Write-Host "[FAIL] Run Setup.exe first (capricorn-data\python missing)"; exit 1 }

$dir = switch ($Where) {
    "Startup"   { [Environment]::GetFolderPath("Startup") }
    "StartMenu" { [Environment]::GetFolderPath("Programs") }
    default     { [Environment]::GetFolderPath("Desktop") }
}
$lnk = Join-Path $dir "Capricorn.lnk"
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$exe = Join-Path $repo "capricorn-data\python\Scripts\Capricorn.exe"
if (Test-Path $exe) {            # shows as "Capricorn" in Task Manager
    $s.TargetPath = $exe
    $s.Arguments = ""
} else {
    $s.TargetPath = $pyw
    $s.Arguments = "-m capricorn"
}
$s.WorkingDirectory = $repo
$s.IconLocation = (Join-Path $repo "assets\icon.ico")
$s.Description = "Capricorn - say 'Hey Capri'"
$s.WindowStyle = 7
$s.Save()
Write-Host "[ OK ] Shortcut created: $lnk"
