<#
Штатная остановка киоска.

Ставит стоп-флаг (kiosk.stop) — после этого start_kiosk.ps1 не перезапустит
Chrome после закрытия — и закрывает текущий процесс Chrome киоска (определяется
по своему изолированному профилю, обычный Chrome пользователя не трогается).

Запускать под тем же пользователем, под которым работает киоск (или удалённо,
например через PsExec/RDP от администратора).

Использование:
    .\stop_kiosk.ps1
#>
param()

$stopFlag = Join-Path $PSScriptRoot "kiosk.stop"
New-Item -ItemType File -Path $stopFlag -Force | Out-Null

$profileDir = Join-Path $env:LOCALAPPDATA "PPEKiosk\ChromeProfile"
Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profileDir) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Киоск остановлен. Для повторного запуска: .\start_kiosk.ps1 (стоп-флаг снимается автоматически)."
