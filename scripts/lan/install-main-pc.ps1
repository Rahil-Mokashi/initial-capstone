<#
.SYNOPSIS
  Turns this PC into the Main PC: protects the folders, creates the keys, opens the firewall, and starts the API at every boot.

.DESCRIPTION
  Run in an elevated PowerShell on the Main PC, using the API program that ships with the application (pperp_api.exe).
  -DryRun prints every step and changes nothing. The API is started by a scheduled task at boot as SYSTEM, with no window and no
  sign-in needed, and restarted by Windows if it stops. (A true Windows service would need a service wrapper this project does not
  carry; see docs/adr-lan-multi-user.md.)

.EXAMPLE
  .\install-main-pc.ps1 -Exe 'C:\PetrolPumpERP\pperp_api.exe' -Address 192.168.1.10 -Subnets 192.168.1.0/24 -DryRun
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$Exe,
  [Parameter(Mandatory)] [string]$Address,
  [Parameter(Mandatory)] [string[]]$Subnets,
  [int]$Port = 8443,
  [int]$PairingPort = 8444,
  [string]$DataDir = (Join-Path $env:ProgramData 'PetrolPumpERP\data'),
  [string]$WebDir = '',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$TaskName = 'PetrolPumpERP-MainPC'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-Step([string]$text, [scriptblock]$action) {
  if ($DryRun) { Write-Host "[dry run] $text" } else { Write-Host $text; & $action }
}

if (-not $DryRun) {
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) { throw 'Run this in an elevated (Administrator) PowerShell.' }
  if (-not (Test-Path $Exe)) { throw "Cannot find $Exe" }
}

Invoke-Step "Create the data folder $DataDir (database and backups live here; access: SYSTEM and Administrators)" {
  New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
  icacls $DataDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
}
Invoke-Step "$Exe lan init --address $Address --subnets $($Subnets -join ',') --port $Port --pairing-port $PairingPort" {
  $env:PETROL_PUMP_DB_PATH = Join-Path $DataDir 'petrol_pump.db'
  & $Exe lan init --address $Address --subnets ($Subnets -join ',') --port $Port --pairing-port $PairingPort
  if ($LASTEXITCODE -ne 0) { throw 'lan init failed; nothing was started.' }
}
& (Join-Path $here 'firewall-main-pc.ps1') -Address $Address -Subnets $Subnets -Port $Port -PairingPort $PairingPort -Program $Exe -DryRun:$DryRun

$webPart = if ($WebDir) { "set PPERP_WEB_DIR=$WebDir&& " } else { '' }
$command = "/c set PETROL_PUMP_DB_PATH=$(Join-Path $DataDir 'petrol_pump.db')&& $webPart`"$Exe`" lan run"
Invoke-Step "Register scheduled task '$TaskName': at startup, as SYSTEM, highest privileges, restart every minute if it stops. Action: cmd.exe $command" {
  $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $command
  $trigger = New-ScheduledTaskTrigger -AtStartup
  $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingToBatteries
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName $TaskName
}
Invoke-Step 'Stop this PC from sleeping while plugged in (the Main PC must stay on)' {
  powercfg /change standby-timeout-ac 0 | Out-Null
  powercfg /change hibernate-timeout-ac 0 | Out-Null
}
Write-Host ''
Write-Host 'Next: on this PC open the program in Client mode, then add the other PCs from Devices (owner screen).'
Write-Host "Authority fingerprint to compare on each new PC:  $Exe lan status"
