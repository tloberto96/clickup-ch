# build_lambda.ps1
# Empaqueta la Lambda Function. Sin dependencias externas: solo main.py.
# Uso: powershell -ExecutionPolicy Bypass -File .\build_lambda.ps1

$ErrorActionPreference = "Stop"
$ZIP_FILE = "lambda_package.zip"

if (Test-Path $ZIP_FILE) { Remove-Item -Force $ZIP_FILE }

Compress-Archive -Path "main.py" -DestinationPath $ZIP_FILE

Write-Host ""
Write-Host "✅  Listo: $ZIP_FILE" -ForegroundColor Green
Write-Host "   Tamaño: $([math]::Round((Get-Item $ZIP_FILE).Length / 1KB, 2)) KB"
Write-Host ""
Write-Host "Configuración en AWS Lambda:" -ForegroundColor Yellow
Write-Host "  Runtime : Python 3.12"
Write-Host "  Handler : main.handler"
Write-Host "  Timeout : 29s (límite de API Gateway)"
Write-Host "  Sin variables de entorno necesarias"
