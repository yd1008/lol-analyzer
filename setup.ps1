# LoL Analyzer Setup Script for PowerShell

Write-Host "LoL Performance Analyzer - PowerShell Setup" -ForegroundColor Green
Write-Host "=" * 50

# Check if Python is installed
Write-Host "`nChecking for Python installation..." -ForegroundColor Yellow
$pythonVersion = $null
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Python not found! Please install Python 3.8 or higher from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# Check if pip is available
Write-Host "`nChecking for pip..." -ForegroundColor Yellow
try {
    $pipVersion = pip --version 2>&1
    Write-Host "Found pip: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "pip not found! Please install pip with Python." -ForegroundColor Red
    exit 1
}

# Navigate to the script directory
Set-Location -Path $PSScriptRoot

# Install required packages
Write-Host "`nInstalling required packages..." -ForegroundColor Yellow
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install required packages!" -ForegroundColor Red
    exit 1
}

Write-Host "`nPackage installation completed!" -ForegroundColor Green

# Run the setup configuration
Write-Host "`nRunning configuration setup..." -ForegroundColor Yellow
python setup.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Configuration setup failed!" -ForegroundColor Red
    exit 1
}

Write-Host "`nConfiguration completed successfully!" -ForegroundColor Green

# Offer to test the connection
Write-Host "`nWould you like to test the API connections now? (y/n)" -ForegroundColor Cyan
$testResponse = Read-Host

if ($testResponse.ToLower() -eq 'y' -or $testResponse.ToLower() -eq 'yes') {
    Write-Host "`nTesting API connections..." -ForegroundColor Yellow
    python test_connection.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nAPI connection test successful!" -ForegroundColor Green
    } else {
        Write-Host "`nAPI connection test failed. Please check your configuration." -ForegroundColor Red
    }
}

Write-Host "`nSetup complete! To run the analyzer, use: python lol_analyzer.py" -ForegroundColor Green
Write-Host "Make sure to keep the program running to receive automatic updates." -ForegroundColor Green