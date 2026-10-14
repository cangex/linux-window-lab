$ErrorActionPreference = 'Stop'
$admin = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this setup from an elevated PowerShell window' }
powercfg.exe /hibernate off
if ($LASTEXITCODE -ne 0) { throw 'Disabling hibernation failed' }
$root = 'C:\LWLAB'
New-Item -ItemType Directory -Force $root | Out-Null
Get-CimInstance SoftwareLicensingProduct | Where-Object { $_.Name -like 'Windows*' -and $_.PartialProductKey } |
    Select-Object Name, Description, LicenseStatus, GracePeriodRemaining |
    ConvertTo-Json | Set-Content "$root\p6-license.json"
cscript.exe //nologo C:\Windows\System32\slmgr.vbs /xpr | Out-File "$root\p6-license-expiry.txt"
$license = Get-Content "$root\p6-license.json" | ConvertFrom-Json
if (-not ($license | Where-Object { $_.LicenseStatus -eq 1 -and $_.GracePeriodRemaining -gt 4320 })) { throw 'A licensed evaluation with >3 days remaining is required' }
schtasks.exe /End /TN LWLAB-P5
Get-Process lwtruth -ErrorAction SilentlyContinue | Stop-Process -Force
Invoke-WebRequest 'http://192.168.231.1:18066/lwtruth.exe' -OutFile "$root\lwtruth.exe"
Get-FileHash "$root\lwtruth.exe" | Format-List | Out-File "$root\p6-workload-hash.txt"
schtasks.exe /Create /TN LWLAB-P5 /SC ONSTART /RU SYSTEM /RL HIGHEST /TR C:\LWLAB\lwtruth.exe /F
if ($LASTEXITCODE -ne 0) { throw 'Task setup failed' }
schtasks.exe /Run /TN LWLAB-P5
Start-Sleep -Seconds 15
Get-Content "$root\p6-truth.jsonl" -Tail 1 | Set-Content "$root\p6-setup-result.json"
shutdown.exe /s /t 5
