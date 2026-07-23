param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('daily', 'weekly', 'monthly')]
    [string]$Job
)

$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$log = Join-Path $repo 'cron.log'

Add-Content $log "===== $Job started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====="

$prompt = Get-Content (Join-Path $repo "prompts\$Job.md") -Raw

$allowed = 'Read,Glob,Grep,Write,Edit,Bash(git add:*),Bash(git commit:*),Bash(git status:*),Bash(git log:*),Bash(mv:*),Bash(date:*)'
$extra = @()
if ($Job -eq 'daily') {
    # daily reads Claude Code session history, which lives outside the repo
    $extra = @('--add-dir', "$env:USERPROFILE\.claude\projects")

    # ingest VM journal exports from the VMware shared folder (only .md files;
    # the VM's own cron.log and everything else in the share stay untouched)
    $vmLog = 'C:\Users\Developer-1\Documents\Virtual Machines\jgr-update\shared\pp\log'
    if (Test-Path $vmLog) {
        Get-ChildItem $vmLog -Filter *.md -File -ErrorAction SilentlyContinue | ForEach-Object {
            Move-Item $_.FullName (Join-Path $repo "inbox\$($_.Name)") -Force
            Add-Content $log "ingested from VM share: $($_.Name)"
        }
    }
}

$out = $prompt | & claude -p --model sonnet --allowedTools $allowed --output-format json @extra 2>&1 |
    ForEach-Object { "$_" }
$code = $LASTEXITCODE

# stdout is one JSON object; pull the result text and cost out of it, fall back to raw
$json = $out | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1
$parsed = $null
if ($json) { try { $parsed = $json | ConvertFrom-Json } catch {} }
if ($parsed) {
    Add-Content $log $parsed.result
    Add-Content $log ("COST: {0:N4} USD, {1} turns, {2:N0}s" -f $parsed.total_cost_usd, $parsed.num_turns, ($parsed.duration_ms / 1000))
    $out | Where-Object { $_ -notmatch '^\s*\{' } | Add-Content $log
} else {
    $out | Add-Content $log
}

if ($code -ne 0) {
    Add-Content $log "FAILED $Job $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit=$code"
}

# push runs even after a failed job so earlier unpushed commits still reach GitHub;
# done here, deterministically, not by the headless Claude run
git push origin master 2>&1 | ForEach-Object { "$_" } | Add-Content $log
if ($LASTEXITCODE -ne 0) {
    Add-Content $log "FAILED push $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (commits remain local)"
}
Add-Content $log "===== $Job ended $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit=$code ====="
exit $code
