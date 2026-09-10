# Provision StudyFlows on AWS Lightsail + CloudFront HTTPS.
# Requires: aws login (or credentials), OpenSSH client.
param(
  [string]$Region = "us-east-1",
  [string]$InstanceName = "studyflows",
  [string]$BundleId = "medium_3_0",
  [string]$BlueprintId = "ubuntu_24_04",
  [string]$RepoUrl = "https://github.com/nickrwynn/planner.git",
  [string]$RepoRef = "main",
  # Cursor Auto key for Ask / Study Lab. Defaults to the local .env value so a
  # redeploy does not silently wipe it.
  [string]$CursorApiKey = ""
)

# Native aws.exe writes to stderr often; do not treat that as a terminating error.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
$env:AWS_DEFAULT_REGION = $Region
$env:AWS_PAGER = ""

function Assert-LastExit([string]$Message) {
  if ($LASTEXITCODE -ne 0) { throw $Message }
}

Write-Host "Checking AWS identity..."
$identJson = aws sts get-caller-identity --output json
Assert-LastExit "aws sts failed - run aws login first"
$ident = $identJson | ConvertFrom-Json
Write-Host "Account=$($ident.Account)"

function New-AppSecret([int]$Len = 40) {
  $bytes = New-Object byte[] $Len
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $s = [Convert]::ToBase64String($bytes) -replace "[^a-zA-Z0-9]", "x"
  return $s.Substring(0, [Math]::Min($Len, 48))
}

$PgPassword = New-AppSecret 32
$JwtSecret = New-AppSecret 48
$az = "${Region}a"

Write-Host "Creating / reusing Lightsail instance in $az..."
$exists = $false
cmd /c "aws lightsail get-instance --instance-name $InstanceName >nul 2>&1"
if ($LASTEXITCODE -eq 0) { $exists = $true }

if (-not $exists) {
  # Pass user-data via file:// so PowerShell/aws do not split shell script lines.
  $userDataPath = (Join-Path $Root "infra\aws\user-data.sh") -replace '\\', '/'
  aws lightsail create-instances --instance-names $InstanceName --availability-zone $az --blueprint-id $BlueprintId --bundle-id $BundleId --user-data "file://$userDataPath"
  Assert-LastExit "create-instances failed"
}

Write-Host "Waiting for instance running + public IP..."
$ip = $null
for ($i = 1; $i -le 60; $i++) {
  $inst = (aws lightsail get-instance --instance-name $InstanceName --output json | ConvertFrom-Json).instance
  Write-Host ("  [{0}] state={1} ip={2}" -f $i, $inst.state.name, $inst.publicIpAddress)
  if ($inst.state.name -eq "running" -and $inst.publicIpAddress) {
    $ip = $inst.publicIpAddress
    break
  }
  Start-Sleep -Seconds 10
}
if (-not $ip) { throw "Instance never became ready" }

Write-Host "Opening ports 22/80/443..."
aws lightsail open-instance-public-ports --instance-name $InstanceName --port-info fromPort=22,toPort=22,protocol=tcp | Out-Null
aws lightsail open-instance-public-ports --instance-name $InstanceName --port-info fromPort=80,toPort=80,protocol=tcp | Out-Null
aws lightsail open-instance-public-ports --instance-name $InstanceName --port-info fromPort=443,toPort=443,protocol=tcp | Out-Null

$staticName = "$InstanceName-ip"
cmd /c "aws lightsail get-static-ip --static-ip-name $staticName >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
  Write-Host "Allocating static IP..."
  aws lightsail allocate-static-ip --static-ip-name $staticName | Out-Null
  Assert-LastExit "allocate-static-ip failed"
}
aws lightsail attach-static-ip --static-ip-name $staticName --instance-name $InstanceName | Out-Null
$ip = (aws lightsail get-static-ip --static-ip-name $staticName --output json | ConvertFrom-Json).staticIp.ipAddress
Write-Host "Static IP: $ip"

Write-Host "Downloading Lightsail SSH key..."
$keyPath = Join-Path $env:TEMP "lightsail-studyflows.pem"
$kp = aws lightsail download-default-key-pair --output json | ConvertFrom-Json
$pem = $null
if ($kp.privateKey) { $pem = $kp.privateKey }
elseif ($kp.privateKeyBase64 -and $kp.privateKeyBase64.Contains("BEGIN")) { $pem = $kp.privateKeyBase64 }
elseif ($kp.privateKeyBase64) {
  $pem = [Text.Encoding]::ASCII.GetString([Convert]::FromBase64String(($kp.privateKeyBase64 -replace '\s','')))
}
if (-not $pem) { throw "No private key in download-default-key-pair response" }
$pem = $pem -replace "`r", ""
if (-not $pem.EndsWith("`n")) { $pem += "`n" }
[IO.File]::WriteAllText($keyPath, $pem)
icacls $keyPath /inheritance:r | Out-Null
icacls $keyPath /grant:r "$($env:USERNAME):(R)" | Out-Null
Write-Host "SSH key written to $keyPath"

function Invoke-Remote([string]$RemoteCmd) {
  & ssh -i $keyPath -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o ConnectTimeout=20 "ubuntu@$ip" $RemoteCmd
  return $LASTEXITCODE
}

Write-Host "Waiting for SSH..."
$sshOk = $false
for ($i = 1; $i -le 40; $i++) {
  $code = Invoke-Remote "echo SSH_OK"
  if ($code -eq 0) { $sshOk = $true; break }
  Start-Sleep -Seconds 8
}
if (-not $sshOk) { throw "SSH failed" }

Write-Host "Waiting for Docker bootstrap (cloud-init)..."
$dockerOk = $false
for ($i = 1; $i -le 40; $i++) {
  $probe = Join-Path $env:TEMP "sf-probe.sh"
  Set-Content -Path $probe -Value "#!/bin/bash`nif test -f /opt/studyflows/.bootstrap-docker-ready; then echo OK; else echo WAIT; fi`n" -Encoding ascii
  & scp -i $keyPath -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL $probe "ubuntu@${ip}:/tmp/sf-probe.sh" | Out-Null
  $out = & ssh -i $keyPath -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "ubuntu@$ip" "bash /tmp/sf-probe.sh"
  Write-Host "  docker bootstrap: $out"
  if ("$out" -match "OK") { $dockerOk = $true; break }
  Start-Sleep -Seconds 15
}
if (-not $dockerOk) {
  Write-Host "Docker marker missing - installing Docker via SSH fallback..."
  $fallback = Join-Path $Root "infra\aws\user-data.sh"
  & scp -i $keyPath -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL $fallback "ubuntu@${ip}:/tmp/user-data.sh"
  Invoke-Remote "sudo bash /tmp/user-data.sh"
}

$deployLocal = Join-Path $env:TEMP "studyflows-remote-deploy.sh"
# Use a literal bash script; substitute secrets with simple replace after write.
$bash = @'
#!/bin/bash
set -euo pipefail
sudo mkdir -p /opt/studyflows
sudo chown ubuntu:ubuntu /opt/studyflows
if [ ! -d /opt/studyflows/.git ]; then
  git clone --depth 1 --branch __REPO_REF__ __REPO_URL__ /opt/studyflows
else
  cd /opt/studyflows
  git fetch origin __REPO_REF__
  git checkout __REPO_REF__
  git reset --hard origin/__REPO_REF__
fi
cd /opt/studyflows
cat > .env <<ENVEOF
POSTGRES_DB=planner
POSTGRES_USER=planner
POSTGRES_PASSWORD=__PG_PASSWORD__
POSTGRES_PORT=5432
REDIS_PORT=6379
API_PORT=8000
WEB_PORT=3000
APP_RUNTIME_PROFILE=prod
APP_ENV=production
DATABASE_URL=postgresql+psycopg://planner:__PG_PASSWORD__@postgres:5432/planner
REDIS_URL=redis://redis:6379/0
PUBLIC_APP_ORIGIN=https://PLACEHOLDER_ORIGIN
CORS_ORIGINS=https://PLACEHOLDER_ORIGIN
STORAGE_ROOT=/data/uploads
STORAGE_BACKEND=local
AUTH_MODE=bearer
AUTH_JWT_SECRET=__JWT_SECRET__
AUTH_JWT_ALGORITHM=HS256
API_AUTH_MODE=bearer
NEXT_PUBLIC_API_AUTH_MODE=bearer
NEXT_PUBLIC_API_BASE_URL=/backend
API_INTERNAL_BASE_URL=http://api:8000
TELEMETRY_ENABLED=true
RATE_LIMIT_ENABLED=true
CANVAS_DEFAULT_BASE_URL=https://canvas.tamu.edu
CANVAS_OAUTH_REDIRECT_URI=https://PLACEHOLDER_ORIGIN/backend/integrations/canvas/oauth/callback
CANVAS_OAUTH_SUCCESS_URL=https://PLACEHOLDER_ORIGIN/?canvas=connected
CANVAS_OAUTH_FAILURE_URL=https://PLACEHOLDER_ORIGIN/?canvas=error
GOOGLE_OAUTH_REDIRECT_URI=https://PLACEHOLDER_ORIGIN/backend/integrations/google/oauth/callback
GOOGLE_OAUTH_SUCCESS_URL=https://PLACEHOLDER_ORIGIN/oauth/done
GOOGLE_OAUTH_FAILURE_URL=https://PLACEHOLDER_ORIGIN/oauth/done
CURSOR_MODEL=auto
CURSOR_API_KEY=__CURSOR_API_KEY__
ENVEOF
sudo docker compose --env-file .env -f docker-compose.yml up --build -d postgres redis api worker web
sleep 8
sudo docker compose --env-file .env exec -T api alembic -c alembic.ini upgrade head
sudo docker rm -f studyflows-edge >/dev/null 2>&1 || true
sudo docker run -d --name studyflows-edge --restart unless-stopped --network host caddy:2 caddy reverse-proxy --from :80 --to 127.0.0.1:3000
curl -fsS http://127.0.0.1:3000/backend/health || true
echo DEPLOY_OK
'@
# Carry the key over from the local .env when it was not passed explicitly.
if (-not $CursorApiKey) {
  $localEnv = Join-Path $Root ".env"
  if (Test-Path $localEnv) {
    $match = Select-String -Path $localEnv -Pattern '^CURSOR_API_KEY=(.+)$' | Select-Object -First 1
    if ($match) { $CursorApiKey = $match.Matches[0].Groups[1].Value.Trim() }
  }
}
if (-not $CursorApiKey) {
  Write-Host "WARNING: no CURSOR_API_KEY - Ask and Study Lab will be disabled on the server."
}

$bash = $bash.Replace("__REPO_REF__", $RepoRef).Replace("__REPO_URL__", $RepoUrl).Replace("__PG_PASSWORD__", $PgPassword).Replace("__JWT_SECRET__", $JwtSecret).Replace("__CURSOR_API_KEY__", $CursorApiKey)
[IO.File]::WriteAllText($deployLocal, $bash.Replace("`r`n", "`n"))

Write-Host "Uploading and running remote deploy (docker build may take 10-20 min)..."
& scp -i $keyPath -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL $deployLocal "ubuntu@${ip}:/tmp/studyflows-remote-deploy.sh"
$code = Invoke-Remote "bash /tmp/studyflows-remote-deploy.sh"
if ($code -ne 0) { throw "Remote deploy failed" }

Write-Host "Creating CloudFront distribution..."
$ref = "studyflows-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$distFile = Join-Path $env:TEMP "studyflows-cf.json"
$distJson = @"
{
  "CallerReference": "$ref",
  "Comment": "StudyFlows always-on",
  "Enabled": true,
  "Origins": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "studyflows-lightsail",
        "DomainName": "$ip",
        "CustomOriginConfig": {
          "HTTPPort": 80,
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "http-only",
          "OriginSslProtocols": { "Quantity": 1, "Items": ["TLSv1.2"] }
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "studyflows-lightsail",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] }
    },
    "Compress": true,
    "ForwardedValues": {
      "QueryString": true,
      "Cookies": { "Forward": "all" },
      "Headers": { "Quantity": 1, "Items": ["*"] }
    },
    "MinTTL": 0,
    "DefaultTTL": 0,
    "MaxTTL": 0,
    "TrustedSigners": { "Enabled": false, "Quantity": 0 }
  },
  "PriceClass": "PriceClass_100",
  "ViewerCertificate": { "CloudFrontDefaultCertificate": true }
}
"@
[IO.File]::WriteAllText($distFile, $distJson)

$cf = aws cloudfront create-distribution --distribution-config "file://$distFile" --output json | ConvertFrom-Json
Assert-LastExit "CloudFront create failed"
$cfDomain = $cf.Distribution.DomainName
$cfId = $cf.Distribution.Id
$origin = "https://$cfDomain"
Write-Host "CloudFront: $origin"

$patch = @"
#!/bin/bash
set -euo pipefail
cd /opt/studyflows
sed -i 's|https://PLACEHOLDER_ORIGIN|$origin|g' .env
sudo docker compose --env-file .env -f docker-compose.yml up -d api web worker
echo PATCH_OK $origin
"@
$patchLocal = Join-Path $env:TEMP "studyflows-patch-origin.sh"
[IO.File]::WriteAllText($patchLocal, $patch.Replace("`r`n", "`n"))
& scp -i $keyPath -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL $patchLocal "ubuntu@${ip}:/tmp/studyflows-patch.sh"
Invoke-Remote "bash /tmp/studyflows-patch.sh" | Out-Null

$outPath = Join-Path $Root "infra\aws\last-deploy.json"
@{
  account = $ident.Account
  region = $Region
  instance = $InstanceName
  staticIp = $ip
  cloudfrontDomain = $cfDomain
  cloudfrontId = $cfId
  publicAppOrigin = $origin
  capServerUrl = $origin
} | ConvertTo-Json | Set-Content $outPath -Encoding utf8

Write-Host ""
Write-Host "=== StudyFlows is on AWS ==="
Write-Host "CAP_SERVER_URL / app URL: $origin"
Write-Host "Saved: $outPath"
Write-Host "CloudFront may take 5-15 minutes to go fully live."
