param(
    [ValidateSet("smoke", "tier2", "full")]
    [string]$Profile = "smoke"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found at $python"
}

$profiles = @{
    smoke = @(
        "tests/test_parser.py",
        "tests/test_validator_invariants.py",
        "tests/test_endpoint_contracts.py",
        "tests/test_efficiency_workflows.py",
        "tests/test_new_log_regressions.py"
    )
    tier2 = @(
        "tests/test_advanced_tier2_parser.py",
        "tests/test_advanced_tier2_workflows.py",
        "tests/test_tier2_parser_regressions.py",
        "tests/test_tier2_workflow_matrix.py",
        "tests/test_new_log_regressions.py",
        "tests/test_efficiency_workflows.py",
        "tests/test_endpoint_contracts.py"
    )
    full = @("tests")
}

$targets = $profiles[$Profile]

Write-Host "Running local test station profile: $Profile" -ForegroundColor Cyan
Write-Host "Targets:" -ForegroundColor Cyan
$targets | ForEach-Object { Write-Host " - $_" }

Push-Location $repoRoot
try {
    & $python -m pytest @targets -q
}
finally {
    Pop-Location
}
