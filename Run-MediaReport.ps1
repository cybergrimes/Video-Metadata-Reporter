# Run-MediaReport.ps1
# Runs media_report.py (keep both files in the same folder) and opens the Excel report.
#
# Usage:
#   Double-click Run-MediaReport.bat           -> pick folders in a dialog
#   .\Run-MediaReport.ps1 "D:\Movies" "D:\TV"  -> scan those folders directly
#
# Tip: put your usual folders in $DefaultFolders below to skip the picker.

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Folders)

$DefaultFolders = @(
    # "D:\Movies",
    # "D:\TV Shows"
)
$MaxAudio = 0   # 0 = as many Audio columns as needed, e.g. 3 = cap at Audio 3
$MaxSubs  = 0   # 0 = as many Sub columns as needed

$ErrorActionPreference = "Continue"   # PS 5.1 treats any stderr from python/pip as an error under "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript  = Join-Path $ScriptDir "media_report.py"

function Fail($msg) { Write-Host "`n$msg" -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }

if (-not (Test-Path $PyScript)) { Fail "media_report.py not found next to this script ($ScriptDir)." }

# --- Find Python (prefer the 'py' launcher, ignore the Microsoft Store stub) ---
$Python = $null
foreach ($cand in @("py", "python", "python3")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") { $Python = $cmd.Source; break }
}
if (-not $Python) {
    Fail "Python not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again.`nOr run:  winget install Python.Python.3.12"
}
Write-Host "Using Python: $Python" -ForegroundColor DarkGray

# --- Install packages if missing ---
& $Python -c "import pymediainfo, openpyxl" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pymediainfo and openpyxl..." -ForegroundColor Cyan
    & $Python -m pip install --user --upgrade pymediainfo openpyxl
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
}

# --- Choose folders ---
if (-not $Folders -or $Folders.Count -eq 0) { $Folders = $DefaultFolders | Where-Object { $_ } }
if (-not $Folders -or $Folders.Count -eq 0) {
    Add-Type -AssemblyName System.Windows.Forms
    $Folders = @()
    do {
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = if ($Folders.Count) { "Add another folder (Cancel when done)" } else { "Choose a folder of movies/TV to scan" }
        $dlg.ShowNewFolderButton = $false
        if ($dlg.ShowDialog() -eq "OK") { $Folders += $dlg.SelectedPath; Write-Host "  + $($dlg.SelectedPath)" } else { break }
        $more = [System.Windows.Forms.MessageBox]::Show("Add another folder?", "Media Report", "YesNo")
    } while ($more -eq "Yes")
}
if (-not $Folders -or $Folders.Count -eq 0) { Fail "No folders chosen." }

# --- Run ---
$Stamp  = Get-Date -Format "yyyy-MM-dd_HHmm"
$ExportDir = Join-Path $ScriptDir "export"
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
$Output = Join-Path $ExportDir "Media Report $Stamp.xlsx"

$argsList = @($PyScript) + $Folders + @("-o", $Output)
if ($MaxAudio -gt 0) { $argsList += @("--max-audio", $MaxAudio) }
if ($MaxSubs  -gt 0) { $argsList += @("--max-subs",  $MaxSubs) }

Write-Host "`nScanning: $($Folders -join ', ')`n" -ForegroundColor Cyan
& $Python @argsList
if ($LASTEXITCODE -ne 0) { Fail "The scan failed (see messages above)." }

Write-Host "`nSaved to: $Output" -ForegroundColor Green
Invoke-Item $Output
