<#
.SYNOPSIS
  Windows Firewall rules for the Main PC: one program, two ports, Private networks only, only the listed subnets.

.DESCRIPTION
  Run in an elevated PowerShell on the Main PC. Use -DryRun first: it prints exactly what would be changed and changes nothing.
  The enrolment port only listens while the owner has a pairing code open (Devices screen); the rule exists so it can be reached then.
  Nothing here opens the internet: the remote addresses are limited to the subnets you give, which must be private ranges.

.EXAMPLE
  .\firewall-main-pc.ps1 -Address 192.168.1.10 -Subnets 192.168.1.0/24 -DryRun
  .\firewall-main-pc.ps1 -Address 192.168.1.10 -Subnets 192.168.1.0/24
  .\firewall-main-pc.ps1 -Remove
#>
[CmdletBinding()]
param(
  [string]$Address,
  [string[]]$Subnets,
  [int]$Port = 8443,
  [int]$PairingPort = 8444,
  [string]$Program = '',
  [switch]$DryRun,
  [switch]$Remove
)
$ErrorActionPreference = 'Stop'
$RuleName = 'Petrol Pump ERP - Main PC'
$Private = @('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')

function Test-InPrivate([string]$cidr) {
  $ip = [System.Net.IPAddress]::Parse(($cidr -split '/')[0]).GetAddressBytes()
  if ($ip[0] -eq 10) { return $true }
  if ($ip[0] -eq 172 -and $ip[1] -ge 16 -and $ip[1] -le 31) { return $true }
  if ($ip[0] -eq 192 -and $ip[1] -eq 168) { return $true }
  return $false
}

function Invoke-Step([string]$text, [scriptblock]$action) {
  if ($DryRun) { Write-Host "[dry run] $text" } else { Write-Host $text; & $action }
}

if ($Remove) {
  Invoke-Step "Remove-NetFirewallRule -DisplayName '$RuleName'" { Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue }
  return
}

if (-not $Address -or -not $Subnets) { throw 'Give -Address (the Main PC''s own address) and -Subnets (for example 192.168.1.0/24).' }
if ($Address -in @('0.0.0.0', '::')) { throw 'Use the Main PC''s own address, not 0.0.0.0.' }
foreach ($s in $Subnets) {
  if (-not (Test-InPrivate $s)) { throw "$s is not a private network range; the Main PC must never be opened to other networks." }
  if ($s -match '/([0-9]+)$' -and [int]$Matches[1] -lt 16) { throw "$s is wider than a /16; use something like 192.168.1.0/24." }
}
if ($Port -eq $PairingPort) { throw 'The two ports must differ.' }

if (-not $DryRun) {
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) { throw 'Run this in an elevated (Administrator) PowerShell.' }
  $profileNames = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -ne 'Disconnected' } | ForEach-Object { "$($_.Name)=$($_.NetworkCategory)" }
  Write-Host "Network profiles: $($profileNames -join ', ')"
  if ((Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' })) {
    Write-Warning 'A connection is set to Public. The rule below applies to Private networks only, so set the pump network to Private (Settings > Network).'
  }
}

$params = @{
  DisplayName   = $RuleName
  Direction     = 'Inbound'
  Action        = 'Allow'
  Protocol      = 'TCP'
  LocalPort     = @($Port, $PairingPort)
  LocalAddress  = $Address
  RemoteAddress = $Subnets
  Profile       = 'Private'
  Enabled       = 'True'
}
if ($Program) { $params.Program = $Program }
$shown = ($params.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value -join ',')" }) -join '  '
Invoke-Step "New-NetFirewallRule  $shown" {
  Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
  New-NetFirewallRule @params | Out-Null
}
Write-Host ("Allowed: TCP {0} and {1} on {2} from {3}, Private networks only." -f $Port, $PairingPort, $Address, ($Subnets -join ', '))
Write-Host 'Nothing else is opened. Windows blocks all other inbound connections by default.'
