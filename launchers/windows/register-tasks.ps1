<#
Registers (or re-registers) the three ddp-diary Task Scheduler jobs.

This script only WRITES scheduled-task definitions when YOU run it — it is
never invoked automatically by ddp-diary. Run from an ELEVATED PowerShell
(Task Scheduler registration needs elevation for S4U logon) — see spec.md §10
for the schedule and the approved migration plan for when to run this during
cutover. Re-running is safe: /F overwrites an existing task of the same name.
#>

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$windowsDir = Join-Path $repoRoot 'launchers\windows'

$dailyCmd = Join-Path $windowsDir 'daily.cmd'
$weeklyCmd = Join-Path $windowsDir 'weekly.cmd'
$monthlyCmd = Join-Path $windowsDir 'monthly.cmd'

Write-Host "Registering JournalDaily (21:00 daily) -> $dailyCmd"
schtasks /Create /TN "JournalDaily" /TR "`"$dailyCmd`"" /SC DAILY /ST 21:00 /F

Write-Host "Registering JournalWeekly (Sun 21:30) -> $weeklyCmd"
schtasks /Create /TN "JournalWeekly" /TR "`"$weeklyCmd`"" /SC WEEKLY /D SUN /ST 21:30 /F

Write-Host "Registering JournalMonthly (1st @ 22:00) -> $monthlyCmd"
schtasks /Create /TN "JournalMonthly" /TR "`"$monthlyCmd`"" /SC MONTHLY /D 1 /ST 22:00 /F

Write-Host ""
Write-Host "Done. Verify with: Get-ScheduledTask -TaskName 'Journal*' | Format-Table TaskName,State"
