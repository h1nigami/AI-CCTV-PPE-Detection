<#
Штатная остановка киоска.

Ставит стоп-флаг (kiosk.stop) — после этого start_kiosk.ps1 не перезапустит
Chrome после закрытия — и закрывает текущий процесс Chrome киоска.

Процесс определяется в первую очередь по PID из kiosk.pid (пишется
start_kiosk.ps1 при каждом запуске Chrome) — это работает без прав
администратора. Резервный способ — поиск по командной строке через
Win32_Process (может не сработать без прав администратора на Windows
с усиленными политиками, ограничивающими доступ к CommandLine чужих
процессов не-администраторам).

Запускать под тем же пользователем, под которым работает киоск (или удалённо,
например через PsExec/RDP от администратора).

Использование:
    .\stop_kiosk.ps1
#>
param()

$stopFlag = Join-Path $PSScriptRoot "kiosk.stop"
New-Item -ItemType File -Path $stopFlag -Force | Out-Null

$stopped = $false
$pidFile = Join-Path $PSScriptRoot "kiosk.pid"
if (Test-Path $pidFile) {
    $savedPid = Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($savedPid) {
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "chrome") {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $stopped = $true
        }
    }
}

if (-not $stopped) {
    # Резервный путь — по командной строке (может ничего не найти без прав администратора).
    $profileDir = Join-Path $env:LOCALAPPDATA "PPEKiosk\ChromeProfile"
    Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profileDir) } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            $stopped = $true
        }
}

if (-not $stopped) {
    Write-Warning "Процесс Chrome киоска не найден (возможно, уже закрыт, либо нет прав на его определение). Стоп-флаг всё равно установлен — при следующем запуске Chrome не откроется."
}

Write-Host "Киоск остановлен. Для повторного запуска: .\start_kiosk.ps1 (стоп-флаг снимается автоматически)."
