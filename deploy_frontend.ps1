# deploy_frontend.ps1
# Sube el frontend a S3 e invalida CloudFront.
# Las credenciales se leen desde .env.deploy (nunca se commitea).

$ErrorActionPreference = "Stop"

$BUCKET       = "tomas-loberto-udemy-052026"
$S3_KEY       = "clickup-ch/index.html"
$LOCAL_FILE   = "frontend\index.html"
$DISTRIBUTION = "E3DDSJKSU835I0"
$ENV_FILE     = ".env.deploy"

Write-Host ""
Write-Host "=== Deploy Frontend a S3 + CloudFront ===" -ForegroundColor Cyan
Write-Host ""

# Leer credenciales desde .env.deploy
if (-not (Test-Path $ENV_FILE)) {
    Write-Host "❌  No se encontro el archivo $ENV_FILE" -ForegroundColor Red
    Write-Host "    Crea el archivo con tus credenciales AWS." -ForegroundColor Yellow
    exit 1
}

foreach ($line in Get-Content $ENV_FILE) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    $parts = $line -split '=', 2
    if ($parts.Length -eq 2 -and $parts[1].Trim() -ne '') {
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
}

# Validar que las variables requeridas estén presentes
foreach ($var in @('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')) {
    if ([string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable($var, 'Process'))) {
        Write-Host "❌  Falta la variable $var en $ENV_FILE" -ForegroundColor Red
        exit 1
    }
}

# Verificar credenciales
Write-Host "==> Verificando credenciales..." -ForegroundColor Gray
$identity = aws sts get-caller-identity 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌  Credenciales invalidas o expiradas." -ForegroundColor Red
    Write-Host $identity -ForegroundColor Red
    Write-Host "    Actualiza las credenciales en $ENV_FILE" -ForegroundColor Yellow
    exit 1
}
Write-Host "    OK" -ForegroundColor Green

# Subir a S3
Write-Host "==> Subiendo $LOCAL_FILE a s3://$BUCKET/$S3_KEY ..." -ForegroundColor Cyan
aws s3 cp $LOCAL_FILE "s3://$BUCKET/$S3_KEY" `
    --content-type "text/html" `
    --cache-control "no-cache"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌  Error al subir el archivo a S3." -ForegroundColor Red
    exit 1
}

# Invalidar CloudFront
Write-Host "==> Invalidando CloudFront ($DISTRIBUTION) ..." -ForegroundColor Cyan
aws cloudfront create-invalidation `
    --distribution-id $DISTRIBUTION `
    --paths "/*"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌  Error al invalidar CloudFront." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅  Deploy completado." -ForegroundColor Green
Write-Host ""
