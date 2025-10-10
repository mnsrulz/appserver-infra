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

# 3. Define NodePorts to forward
$Ports = @(30080, 30443, 32080)

# 4. Loop through ports and add forwarding
foreach ($port in $Ports) {
    # Remove old forwarding if exists
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null

    # Add new forwarding
    netsh interface portproxy add v4tov4 `
        listenport=$port `
        listenaddress=0.0.0.0 `
        connectport=$port `
        connectaddress=$WSL_IP

    Write-Host "Forwarded localhost:$port -> ${WSL_IP}:$port"
}

Write-Host "`n✅ All NodePorts forwarded from WSL to Windows localhost"
Write-Host "You can now access your apps via http://localhost:30080, http://localhost:32080, etc."
