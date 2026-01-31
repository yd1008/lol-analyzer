# PowerShell script to run the LoL Analyzer

Write-Host "Starting LoL Performance Analyzer..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the analyzer" -ForegroundColor Yellow

# Navigate to the script directory
Set-Location -Path $PSScriptRoot

# Run the analyzer
python lol_analyzer.py