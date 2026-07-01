<#
Запуск дашборда AI CCTV PPE Detection в режиме киоска Google Chrome.

Открывает Chrome в полноэкранном режиме (--kiosk) без адресной строки, вкладок
и элементов управления браузером — так, чтобы для оператора приложение выглядело
как отдельная программа, а не вкладка браузера. Использует отдельный профиль
Chrome (не трогает обычный профиль пользователя), поэтому JWT-сессия (см.
backend/auth) переживает перезапуски.

Если Chrome закрылся или упал — скрипт перезапускает его автоматически
(до появления стоп-флага kiosk.stop, см. stop_kiosk.ps1). Это и есть
"блокировка устройства только для выполнения этой программы" на уровне
Chrome: оператор не может остаться на рабочем столе без дашборда.

Использование:
    .\start_kiosk.ps1                                   # http://localhost:8000
    .\start_kiosk.ps1 -Url "http://192.168.0.85"        # адрес фронт-сервера
    .\start_kiosk.ps1 -ChromePath "D:\Chrome\chrome.exe"

Для автозапуска при входе в систему — см. install_autostart.ps1.
#>
param(
    [string]$Url = "http://localhost:8000",
    [string]$ChromePath,
    [int]$WaitForBackendSec = 120,
    [int]$RestartDelaySec = 2
)

$ErrorActionPreference = "Stop"
$stopFlag = Join-Path $PSScriptRoot "kiosk.stop"
$profileDir = Join-Path $env:LOCALAPPDATA "PPEKiosk\ChromeProfile"

function Find-Chrome {
    if ($ChromePath) {
        if (Test-Path $ChromePath) { return $ChromePath }
        throw "Chrome не найден по указанному пути: $ChromePath"
    }
    $candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    throw "Google Chrome не найден. Установите Chrome или укажите путь через -ChromePath."
}

function Wait-Backend {
    param([string]$BaseUrl, [int]$TimeoutSec)
    $healthUrl = "$($BaseUrl.TrimEnd('/'))/health"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Warning "Бэкенд $BaseUrl не ответил за $TimeoutSec с — всё равно запускаем Chrome."
}

$chrome = Find-Chrome
New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
Remove-Item -Path $stopFlag -Force -ErrorAction SilentlyContinue

Wait-Backend -BaseUrl $Url -TimeoutSec $WaitForBackendSec

$chromeArgs = @(
    "--kiosk", $Url,
    "--user-data-dir=$profileDir",
    "--no-first-run",
    "--noerrdialogs",
    "--disable-session-crashed-bubble",
    "--disable-infobars",
    "--disable-translate",
    "--disable-features=TranslateUI",
    "--disable-pinch",
    "--overscroll-history-navigation=0",
    "--autoplay-policy=no-user-gesture-required"
)

while (-not (Test-Path $stopFlag)) {
    $proc = Start-Process -FilePath $chrome -ArgumentList $chromeArgs -PassThru
    Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if (Test-Path $stopFlag) { break }
    Start-Sleep -Seconds $RestartDelaySec
}

Remove-Item -Path $stopFlag -Force -ErrorAction SilentlyContinue
