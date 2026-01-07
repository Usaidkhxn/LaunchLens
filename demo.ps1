# LaunchLens demo runner (Windows PowerShell)
# Usage:
#   ./demo.ps1
# Creates synthetic data, builds warehouse, and launches Streamlit app.

$ErrorActionPreference = "Stop"

Write-Host "== LaunchLens Demo =="

# Ensure venv exists
if (!(Test-Path ".\.venv\Scripts\Activate.ps1")) {
  Write-Host "Creating venv..."
  py -m venv .venv
}

# Activate venv
Write-Host "Activating venv..."
. .\.venv\Scripts\Activate.ps1

Write-Host "Installing dependencies..."
python -m pip install -U pip
pip install -r requirements.txt

# Generate data
Write-Host "Generating synthetic event data..."
python .\src\launchlens\data\generate_events.py --out_dir data --n_users 8000 --n_days 28 --experiment_start_day 14 --purchase_lift_mult 1.15

# Build warehouse
Write-Host "Building warehouse tables..."
python .\src\launchlens\warehouse\build_warehouse.py --db data\launchlens.duckdb

# Run AB readout (prints in terminal)
Write-Host "Running A/B readout..."
python .\src\launchlens\experimentation\ab_readout.py --db data\launchlens.duckdb --experiment_id exp_checkout_v1

# Launch Streamlit
Write-Host "Launching dashboard..."
$env:PYTHONPATH = "src"
streamlit run .\src\launchlens\dashboards\app.py
