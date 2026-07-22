param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('daily', 'weekly', 'monthly')]
    [string]$Job
)

# Thin launcher only: locate Python and forward to the ddp_diary core. No
# business logic lives here — see spec.md §3 ("thin launchers").
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath = Join-Path $repoRoot 'config\host.toml'

# Make the core importable even without an editable `pip install -e .`.
$env:PYTHONPATH = (Join-Path $repoRoot 'src') + ';' + $env:PYTHONPATH

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error "no python interpreter found on PATH"
    exit 1
}

& $python.Source -m ddp_diary run --job $Job --config $configPath --role host
exit $LASTEXITCODE
