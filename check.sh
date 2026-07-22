#!/bin/bash
# ==============================================================================
#  HARDWARE CHECKS
# ==============================================================================

# Ensure script is run with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "\033[0;31m[ERROR] Please run this script with sudo: sudo bash check.sh\033[0m"
    exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo -e "${CYAN}=================================================================="${NC}
echo -e "${CYAN}             ULTIMATE THINKPAD HARDWARE AUDIT REPORT             "${NC}
echo -e "${CYAN}=================================================================="${NC}

# 1. SYSTEM MODEL & SERIAL
MODEL=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "Unknown")
SERIAL=$(cat /sys/class/dmi/id/product_serial 2>/dev/null || echo "Unknown")
echo -e "${YELLOW}[+] SYSTEM IDENTIFICATION:${NC}"
echo -e "    Model: ${GREEN}${MODEL}${NC}"
echo -e "    Serial: ${GREEN}${SERIAL}${NC}"

# 2. CPU & THERMAL DIAGNOSTICS
echo -e "\n${YELLOW}[+] CPU & THERMAL DIAGNOSTICS:${NC}"
CPU_NAME=$(lscpu 2>/dev/null | grep -m 1 'Model name' | cut -d':' -f2 | xargs)
[ -z "$CPU_NAME" ] && CPU_NAME="Unknown CPU"
echo -e "    Model: ${GREEN}${CPU_NAME}${NC}"
echo -e "    Cores / Threads: ${GREEN}$(nproc --all 2>/dev/null || echo "N/A")${NC} threads"

echo -e "    ${BOLD}Current Temperatures:${NC}"
FOUND_TEMP=0
for zone in /sys/class/thermal/thermal_zone*; do
    if [ -f "$zone/temp" ]; then
        TYPE=$(cat "$zone/type" 2>/dev/null || echo "zone")
        RAW_TEMP=$(cat "$zone/temp" 2>/dev/null)
        if [[ "$RAW_TEMP" =~ ^[0-9]+$ ]]; then
            TEMP=$((RAW_TEMP / 1000))
            if [ "$TEMP" -gt 0 ]; then
                FOUND_TEMP=1
                if [ "$TEMP" -ge 85 ]; then
                    echo -e "    - Sensor ($TYPE): ${RED}${TEMP}°C (OVERHEATING / NEEDS THERMAL PASTE)${NC}"
                elif [ "$TEMP" -ge 70 ]; then
                    echo -e "    - Sensor ($TYPE): ${YELLOW}${TEMP}°C (Warm)${NC}"
                else
                    echo -e "    - Sensor ($TYPE): ${GREEN}${TEMP}°C (Cool / Normal)${NC}"
                fi
            fi
        fi
    fi
done
[ "$FOUND_TEMP" -eq 0 ] && echo -e "    ${YELLOW}No active thermal zone sensors detected.${NC}"

# 3. DISPLAY PANEL & SCREEN SPECS
echo -e "\n${YELLOW}[+] DISPLAY PANEL & SCREEN SPECS:${NC}"
eDP_PATH=$(find /sys/class/drm/ -name "*eDP*" 2>/dev/null | head -n 1)

if [ -n "$eDP_PATH" ]; then
    STATUS=$(cat "$eDP_PATH/status" 2>/dev/null || echo "Unknown")
    echo -e "    Internal Screen Status: ${GREEN}${STATUS}${NC}"
    
    if [ -f "$eDP_PATH/modes" ]; then
        NATIVE_RES=$(head -n 1 "$eDP_PATH/modes" 2>/dev/null)
        echo -e "    Native Resolution: ${GREEN}${NATIVE_RES:-Unknown}${NC}"
    fi
    
    if [ -f "$eDP_PATH/edid" ]; then
        if command -v strings &>/dev/null; then
            PANEL_STRINGS=$(strings "$eDP_PATH/edid" 2>/dev/null | grep -E "^[A-Z0-9]{3,}$" | head -n 3 | xargs)
        else
            PANEL_STRINGS=$(tr -cd '[:print:]' < "$eDP_PATH/edid" 2>/dev/null | grep -oE "[A-Z0-9]{4,}" | head -n 3 | xargs)
        fi
        [ -n "$PANEL_STRINGS" ] && echo -e "    Panel EDID Identifiers: ${GREEN}${PANEL_STRINGS}${NC}"
    fi
else
    echo -e "    ${YELLOW}eDP internal screen path not found via sysfs.${NC}"
fi

# 4. MEMORY (RAM) DETAILED BREAKDOWN
echo -e "\n${YELLOW}[+] MEMORY (RAM) DETAILED BREAKDOWN:${NC}"
TOTAL_RAM=$(free -h 2>/dev/null | awk '/Mem:/ {print $2}')
echo -e "    Total Active System Memory: ${GREEN}${TOTAL_RAM:-Unknown}${NC}"

if command -v dmidecode &> /dev/null; then
    MAX_CAP=$(dmidecode -t memory 2>/dev/null | grep -i "Maximum Capacity" | cut -d':' -f2 | xargs)
    SLOTS_NUM=$(dmidecode -t memory 2>/dev/null | grep -i "Number Of Devices" | cut -d':' -f2 | xargs)
    echo -e "    Max Supported RAM: ${GREEN}${MAX_CAP:-Unknown}${NC} across ${GREEN}${SLOTS_NUM:-Unknown}${NC} physical slot(s)"
    
    echo -e "    ${BOLD}Slot Configuration:${NC}"
    dmidecode -t 17 2>/dev/null | tr -d '\r' | awk '
        BEGIN { slot=0 }
        /Memory Device$/ {
            if (slot > 0) { print slot "::" size "::" ff "::" type "::" speed }
            slot++; size="Unknown"; ff="Unknown"; type="Unknown"; speed="Unknown"
        }
        /Size:/ { size=$0; sub(/.*Size:[ \t]*/, "", size) }
        /Form Factor:/ { ff=$0; sub(/.*Form Factor:[ \t]*/, "", ff) }
        /Type:/ && !/Type Detail/ { type=$0; sub(/.*Type:[ \t]*/, "", type) }
        /Speed:/ && !/Configured/ { speed=$0; sub(/.*Speed:[ \t]*/, "", speed) }
        END { if (slot > 0) { print slot "::" size "::" ff "::" type "::" speed } }
    ' | while IFS="::" read -r slot size ff type speed; do
        if echo "$size" | grep -qi "No Module"; then
            echo -e "      ${GREEN}[FREE SLOT AVAILABLE]${NC} Slot $slot: Empty / Unpopulated"
        elif echo "$ff" | grep -qi "Row of chips\|Embedded" || echo "$type" | grep -qi "Embedded"; then
            echo -e "      ${CYAN}[SOLDERED RAM]${NC} Slot $slot: $size | $type | $speed"
        else
            echo -e "      ${YELLOW}[REMOVABLE SODIMM SLOT]${NC} Slot $slot: $size | $ff | $type | $speed"
        fi
    done
else
    echo -e "    ${RED}dmidecode command not available.${NC}"
fi

# 5. WI-FI / WLAN CARD AUDIT
echo -e "\n${YELLOW}[+] WI-FI / WLAN CARD DIAGNOSTICS:${NC}"
WIFI_INFO=$(lspci -k 2>/dev/null | grep -A 2 -i network)
if [ -n "$WIFI_INFO" ]; then
    CARD_NAME=$(echo "$WIFI_INFO" | head -n 1 | cut -d':' -f3 | xargs)
    echo -e "    Hardware: ${GREEN}${CARD_NAME}${NC}"
    if echo "$WIFI_INFO" | grep -qi "Intel"; then
        echo -e "    Card Status: ${GREEN}[GOOD] Intel Wi-Fi detected (Recommended for Linux stability)${NC}"
    elif echo "$WIFI_INFO" | grep -qi "Realtek"; then
        echo -e "    Card Status: ${RED}[WARNING] Realtek Wi-Fi detected (Known driver/drop issues on Linux)${NC}"
    else
        echo -e "    Card Status: ${YELLOW}[ACCEPTABLE] Non-Intel Wi-Fi detected${NC}"
    fi
else
    echo -e "    ${RED}[!] NO WI-FI CARD DETECTED VIA PCI BUS${NC}"
fi

# 6. GPU DIAGNOSTICS
echo -e "\n${YELLOW}[+] GPU / GRAPHICS CARD(S):${NC}"
lspci 2>/dev/null | grep -E "VGA|3D" | while read -r gpu; do
    echo -e "    - ${GREEN}${gpu}${NC}"
done

# 7. STORAGE (SSD / HDD) HEALTH
echo -e "\n${YELLOW}[+] STORAGE (SSD / HDD) HEALTH:${NC}"
lsblk -o NAME,TYPE,SIZE,ROTA,MODEL 2>/dev/null | grep -E "disk|NAME" | while read -r line; do
    echo -e "    ${line}"
done

for dev in /dev/nvme0n1 /dev/sda /dev/sdb; do
    if [ -b "$dev" ] && command -v smartctl &> /dev/null; then
        SMART_HEALTH=$(smartctl -H "$dev" 2>/dev/null | grep -i "result" | cut -d':' -f2 | xargs)
        MODEL_NAME=$(smartctl -i "$dev" 2>/dev/null | grep -i "Device Model\|Model Number" | cut -d':' -f2 | xargs)
        if [ -n "$SMART_HEALTH" ]; then
            if [ "$SMART_HEALTH" = "PASSED" ] || [ "$SMART_HEALTH" = "OK" ]; then
                echo -e "    SMART Health ($dev - ${MODEL_NAME:-Drive}): ${GREEN}[PASSED / GOOD]${NC}"
            else
                echo -e "    SMART Health ($dev - ${MODEL_NAME:-Drive}): ${RED}[FAILED / DYING DRIVE]${NC}"
            fi
        fi
    fi
done

# 8. BATTERY EFFICIENCY & HEALTH
echo -e "\n${YELLOW}[+] BATTERY LIFE EFFICIENCY:${NC}"
FOUND_BAT=0
for bat in /sys/class/power_supply/BAT*; do
    if [ -d "$bat" ]; then
        FOUND_BAT=1
        BAT_NAME=$(basename "$bat")
        
        FULL=$(cat "$bat/energy_full" 2>/dev/null || cat "$bat/charge_full" 2>/dev/null)
        DESIGN=$(cat "$bat/energy_full_design" 2>/dev/null || cat "$bat/charge_full_design" 2>/dev/null)
        CYCLES=$(cat "$bat/cycle_count" 2>/dev/null || echo "N/A")
        STATUS=$(cat "$bat/status" 2>/dev/null || echo "Unknown")
        
        echo -e "    ${CYAN}--- ${BAT_NAME} (Status: ${STATUS}) ---${NC}"
        echo -e "    Cycle Count: ${GREEN}${CYCLES}${NC}"
        
        if [[ "$FULL" =~ ^[0-9]+$ ]] && [[ "$DESIGN" =~ ^[0-9]+$ ]] && [ "$DESIGN" -gt 0 ]; then
            HEALTH=$(( FULL * 100 / DESIGN ))
            if [ "$HEALTH" -ge 80 ]; then
                echo -e "    Health Efficiency: ${GREEN}${HEALTH}% (Excellent Condition)${NC}"
            elif [ "$HEALTH" -ge 60 ]; then
                echo -e "    Health Efficiency: ${YELLOW}${HEALTH}% (Fair - Moderate Wear)${NC}"
            else
                echo -e "    Health Efficiency: ${RED}${HEALTH}% (Poor - Degraded)${NC}"
            fi
        fi
    fi
done
[ "$FOUND_BAT" -eq 0 ] && echo -e "    ${RED}[!] NO BATTERIES DETECTED${NC}"

# 9. THUNDERBOLT CONTROLLER DIAGNOSTICS
echo -e "\n${YELLOW}[+] THUNDERBOLT CONTROLLER DIAGNOSTICS:${NC}"
if echo "$CPU_NAME" | grep -qi "AMD"; then
    echo -e "    ${CYAN}[INFO] AMD Processor Detected (${MODEL}):${NC}"
    echo -e "    AMD ThinkPads use standard USB-C 3.2 Gen 2 / DP Alt Mode (No Thunderbolt controller expected)."
else
    TB_PCI=$(lspci 2>/dev/null | grep -i "thunderbolt")
    if [ -n "$TB_PCI" ]; then
        echo -e "    PCI Bus Status: ${GREEN}[DETECTED] $TB_PCI${NC}"
    else
        echo -e "    PCI Bus Status: ${YELLOW}[NOT DETECTED] No Thunderbolt device on PCI bus.${NC}"
    fi

    if [ -d "/sys/bus/thunderbolt/devices" ]; then
        TB_DEVS=$(ls -A /sys/bus/thunderbolt/devices 2>/dev/null)
        if [ -n "$TB_DEVS" ]; then
            echo -e "    Sysfs Interface: ${GREEN}[OK] Controller active. Devices found.${NC}"
        else
            echo -e "    Sysfs Interface: ${RED}[ALERT] Directory exists but is empty! (Check BIOS settings)${NC}"
        fi
    else
        if echo "$MODEL" | grep -qi "T480"; then
            echo -e "    Sysfs Interface: ${RED}[CRITICAL - DO NOT BUY] Dead Thunderbolt chip detected on T480!${NC}"
        else
            echo -e "    Sysfs Interface: ${YELLOW}Thunderbolt interface not present in kernel sysfs.${NC}"
        fi
    fi
fi

# 10. USB HOST CONTROLLERS & LIVE PORT TEST
echo -e "\n${YELLOW}[+] USB HOST CONTROLLERS:${NC}"
lspci 2>/dev/null | grep -i "usb" | while read -r usb_ctrl; do
    echo -e "    - ${GREEN}${usb_ctrl}${NC}"
done

echo -e "\n${CYAN}=================================================================="${NC}
echo -e "${CYAN}                    INTERACTIVE USB PORT TEST                    "${NC}
echo -e "${CYAN}=================================================================="${NC}
echo -e "Press ${BOLD}[ENTER]${NC} to start live USB port testing (or Ctrl+C to skip)."
read -r _ < /dev/tty 2>/dev/null || read -r _

echo -e "\n${YELLOW}[*] USB MONITOR ACTIVE:${NC} Plug a flash drive into EACH USB port one by one."
echo -e "The terminal will log newly inserted USB devices live. Press ${BOLD}Ctrl+C${NC} when finished.\n"

udevadm monitor --subsystem-match=usb --property 2>/dev/null | grep --line-buffered "DEVTYPE=usb_device" | while read -r _; do
    echo -e "${GREEN}[USB PORT ALIVE] USB Device Connection Detected!${NC}"
done
