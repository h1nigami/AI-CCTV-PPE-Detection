<#
Удаляет задачу планировщика, зарегистрированную install_autostart.ps1.
Требует запуска PowerShell от имени администратора.

Использование:
    .\uninstall_autostart.ps1
#>
param(
    [string]$TaskName = "PPEKioskAutostart"
)

$ErrorActionPreference = "Stop"

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Запустите PowerShell от имени администратора."
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Задача '$TaskName' удалена."
