<#
Регистрирует задачу планировщика Windows: start_kiosk.ps1 запускается
автоматически при входе указанного пользователя в систему. Предназначено для
выделенной учётной записи киоска (см. docs/kiosk-mode.md — настройка
автологина под этой учёткой).

Требует запуска PowerShell от имени администратора.

Использование:
    .\install_autostart.ps1
    .\install_autostart.ps1 -User "KIOSK\ppekiosk" -Url "http://localhost:8000"
#>
param(
    [string]$TaskName = "PPEKioskAutostart",
    [string]$User = "$env:USERDOMAIN\$env:USERNAME",
    [string]$Url = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Запустите PowerShell от имени администратора."
}

$scriptPath = Join-Path $PSScriptRoot "start_kiosk.ps1"
if (-not (Test-Path $scriptPath)) {
    throw "Не найден $scriptPath"
}

$argument = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Url `"$Url`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Автозапуск киоск-режима AI CCTV PPE Detection при входе в систему" -Force | Out-Null

Write-Host "Задача '$TaskName' зарегистрирована для пользователя $User."
Write-Host "Проверить вручную: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Удалить: .\uninstall_autostart.ps1"
