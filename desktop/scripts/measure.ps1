# Measures cold-ish start time and idle memory for the new Electron app and the existing Qt build.
#   powershell -File desktop\scripts\measure.ps1 -Electron "<path to Petrol Pump ERP.exe>" -Qt "<path to PetrolPumpERP.exe>" -Template "<migrated template.db>"
# Both apps run against COPIES of a throwaway database (never the real %LOCALAPPDATA% one).
param(
  [Parameter(Mandatory)] [string] $Electron,
  [Parameter(Mandatory)] [string] $Qt,
  [Parameter(Mandatory)] [string] $Template,
  [int] $Runs = 5,
  [int] $IdleSeconds = 20
)

$ErrorActionPreference = 'Stop'
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

foreach ($name in 'PetrolPumpERP', 'Petrol Pump ERP', 'pperp-api') {
  if (Get-Process -Name $name -ErrorAction SilentlyContinue) { throw "'$name' is already running - close it first so the numbers are not mixed up." }
}

function Measure-App([string] $Label, [string] $Exe, [string[]] $ProcNames) {
  $rows = @()
  for ($i = 1; $i -le $Runs; $i++) {
    $work = Join-Path $env:TEMP ("pperp-measure-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $work | Out-Null
    Copy-Item $Template (Join-Path $work 'pump.db')
    $env:PETROL_PUMP_DB_PATH = Join-Path $work 'pump.db'
    $env:PPERP_USER_DATA = Join-Path $work 'userData'

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $Exe -PassThru
    $startMs = $null
    while ($sw.Elapsed.TotalSeconds -lt 90) {
      $all = Get-Process -Name $ProcNames -ErrorAction SilentlyContinue
      if ($all | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle }) { $startMs = $sw.ElapsedMilliseconds; break }
      Start-Sleep -Milliseconds 25
    }
    Start-Sleep -Seconds $IdleSeconds
    $procs = Get-Process -Name $ProcNames -ErrorAction SilentlyContinue
    $ws = ($procs | Measure-Object WorkingSet64 -Sum).Sum / 1MB
    $priv = ($procs | Measure-Object PrivateMemorySize64 -Sum).Sum / 1MB
    $rows += [pscustomobject]@{ Run = $i; StartMs = $startMs; WorkingSetMB = [math]::Round($ws, 0); PrivateMB = [math]::Round($priv, 0); Processes = @($procs).Count }

    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
  }
  Write-Output "=== $Label ==="
  $rows | Format-Table -AutoSize | Out-String | Write-Output
  $sorted = $rows | Where-Object StartMs | Sort-Object StartMs
  $median = $sorted[[int][math]::Floor($sorted.Count / 2)].StartMs
  $mws = ($rows | Sort-Object WorkingSetMB)[[int][math]::Floor($rows.Count / 2)].WorkingSetMB
  $mpv = ($rows | Sort-Object PrivateMB)[[int][math]::Floor($rows.Count / 2)].PrivateMB
  Write-Output ("{0}: first run {1} ms | median start {2} ms | median idle working set {3} MB | median idle private {4} MB" -f $Label, $rows[0].StartMs, $median, $mws, $mpv)
}

Measure-App 'New app (Electron + Python API)' $Electron @('Petrol Pump ERP', 'pperp-api')
Measure-App 'Existing Qt app'                 $Qt       @('PetrolPumpERP')

