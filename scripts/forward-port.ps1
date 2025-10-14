# 1. Replace this with your running WSL distro name
$WSL_DISTRO = "Ubuntu-24.04"

# 2. Get WSL IP automatically using cut instead of awk
do {
    try {
        $WSL_IP = wsl -d $WSL_DISTRO -e sh -c "hostname -I | cut -d' ' -f1"
    } catch {
        $WSL_IP = ""
    }
    if (-not $WSL_IP) {
        Write-Host "WSL not ready yet, retrying in 5 seconds..."
        Start-Sleep -Seconds 5
    }
} until ($WSL_IP)
Write-Host "WSL IP detected as: $WSL_IP"

# 3. Define port forwarding mappings:
#    ListenPort (Windows) -> ConnectPort (WSL)
$PortMap = @{
    80   = 30080   # HTTP
    30443  = 30443   # HTTPS
    32080 = 32080  # Traefik dashboard (optional)
}

# 4. Loop through mappings and configure portproxy
foreach ($mapping in $PortMap.GetEnumerator()) {
    $listenPort = $mapping.Key
    $connectPort = $mapping.Value

    # Remove old forwarding if it exists
    netsh interface portproxy delete v4tov4 listenport=$listenPort listenaddress=0.0.0.0 2>$null

    # Add new forwarding
    netsh interface portproxy add v4tov4 `
        listenport=$listenPort `
        listenaddress=0.0.0.0 `
        connectport=$connectPort `
        connectaddress=$WSL_IP

    Write-Host "Forwarded localhost:$listenPort -> ${WSL_IP}:$connectPort"
}

Write-Host "`n✅ All ports forwarded from Windows to WSL."
Write-Host "You can now access Traefik via:"
Write-Host "  → http://localhost"
Write-Host "  → https://localhost"
Write-Host "  → http://localhost:32080 (dashboard)"
