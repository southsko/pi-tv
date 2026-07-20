# prepare_card.ps1 — run on Windows AFTER flashing the SD card with
# Raspberry Pi Imager (with WiFi/SSH customization), BEFORE first boot.
#
#   Right-click -> Run with PowerShell   (or: powershell -ExecutionPolicy Bypass -File prepare_card.ps1)
#
# What it does:
#  * stops Pi OS from expanding its root partition over the whole card
#  * makes the Pi's own first boot cap the OS at 8 GB and create a data
#    partition from the remaining space (formatted as exFAT later by
#    setup_exfat.sh on the Pi)
# No diskpart needed.

$ErrorActionPreference = "Stop"

# -- find the SD card's boot partition (FAT32, contains cmdline.txt) ------
$boot = $null
foreach ($v in Get-Volume | Where-Object DriveLetter) {
    if (Test-Path "$($v.DriveLetter):\cmdline.txt") { $boot = "$($v.DriveLetter):"; break }
}
if (-not $boot) {
    Write-Host "Could not find a drive containing cmdline.txt - is the flashed SD card inserted?" -ForegroundColor Red
    exit 1
}
Write-Host "Found boot partition at $boot"

$firstrun = "$boot\firstrun.sh"
if (-not (Test-Path $firstrun)) {
    Write-Host "No firstrun.sh on $boot." -ForegroundColor Red
    Write-Host "Re-flash with Raspberry Pi Imager and use its OS customization (set WiFi/SSH) - that generates firstrun.sh, which this script hooks into."
    exit 1
}

# -- 1. disable the built-in whole-card resize ----------------------------
$cmdline = [IO.File]::ReadAllText("$boot\cmdline.txt")
$patched = $cmdline -replace ' init=/usr/lib/raspberrypi-sys-mods/firstboot', ''
if ($patched -ne $cmdline) {
    [IO.File]::WriteAllText("$boot\cmdline.txt", $patched)
    Write-Host "cmdline.txt: removed built-in first-boot resize"
} else {
    Write-Host "cmdline.txt: no built-in resize trigger found (already removed?)"
}

# -- 2. inject our partitioning into firstrun.sh --------------------------
$snippet = @"
# --- pi-tv: cap OS at 8GB, reserve the rest as a data partition ---
ROOT_DEV=/dev/mmcblk0
OS_END_S=16777215   # sectors; 8GiB
CUR_END=`$(parted -m "`$ROOT_DEV" u s print | awk -F: '`$1==2{print `$3}' | tr -d s)
if [ -b "`$ROOT_DEV" ] && [ ! -b "`${ROOT_DEV}p3" ] && [ "`$CUR_END" -lt "`$OS_END_S" ]; then
  parted -m "`$ROOT_DEV" u s resizepart 2 `$OS_END_S || true
  partprobe "`$ROOT_DEV" || true
  resize2fs "`${ROOT_DEV}p2" || true
  parted -s "`$ROOT_DEV" u s mkpart primary `$((OS_END_S+1)) 100% || true
  partprobe "`$ROOT_DEV" || true
fi
# built-in firstboot normally regenerates SSH host keys; do it here instead
if [ -x /usr/lib/raspberrypi-sys-mods/regenerate_ssh_host_keys ]; then
  /usr/lib/raspberrypi-sys-mods/regenerate_ssh_host_keys || true
else
  ssh-keygen -A || true
fi
# --- end pi-tv ---
"@ -replace "`r`n", "`n"

$content = [IO.File]::ReadAllText($firstrun)
if ($content -match 'pi-tv: cap OS') {
    Write-Host "firstrun.sh: pi-tv snippet already present, skipping"
} elseif ($content -match '(?m)^rm -f /boot/firstrun\.sh') {
    $content = $content -replace '(?m)^rm -f /boot/firstrun\.sh', "$snippet`nrm -f /boot/firstrun.sh"
    [IO.File]::WriteAllText($firstrun, $content)
    Write-Host "firstrun.sh: partitioning snippet injected"
} else {
    # fall back: append before final exit
    $content = $content -replace '(?m)^exit 0\s*$', "$snippet`nexit 0"
    [IO.File]::WriteAllText($firstrun, $content)
    Write-Host "firstrun.sh: snippet appended (fallback position)"
}

Write-Host ""
Write-Host "Done. Eject the card, boot the Pi (first boot takes a bit longer)," -ForegroundColor Green
Write-Host "then on the Pi run: bash install.sh && bash setup_exfat.sh" -ForegroundColor Green
