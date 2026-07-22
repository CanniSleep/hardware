#!/bin/bash
# ==========================================================
# THINKPAD STORE AUDIT SCRIPT (T480 & T14 GEN 2)
# ==========================================================

# Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

clear
echo -e "${CYAN}=================================================="${NC}
echo -e "${CYAN}          THINKPAD HARDWARE AUDIT REPORT          "${NC}
echo -e "${CYAN}=================================================="${NC}

# 1. System Model
MODEL=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "Unknown")
echo -e "${YELLOW}[+] LAPTOP MODEL:${NC} ${GREEN}$MODEL${NC}"

# 2. CPU
echo -e "\n${YELLOW}[+] CPU INFO:${NC}"
lscpu | grep -E "Model name|CPU\(s\):|Thread\(s\) per core"

# 3. RAM
echo -e "\n${YELLOW}[+] TOTAL RAM:${NC}"
free -h | awk '/Mem:/ {print "Capacity: " $2}'

# 4. GPU Check
echo -e "\n${YELLOW}[+] GPU / GRAPHICS CARD(S):${NC}"
lspci | grep -E "VGA|3D"

# 5. Wi-Fi Card Vendor Check
echo -e "\n${YELLOW}[+] WI-FI CARD:${NC}"
WIFI_INFO=$(lspci -k | grep -A 2 -i network)
echo "$WIFI_INFO"
if echo "$WIFI_INFO" | grep -qi "Intel"; then
    echo -e "--> ${GREEN}[OK] Intel Wi-Fi Detected${NC}"
elif echo "$WIFI_INFO" | grep -qi "Realtek"; then
    echo -e "--> ${RED}[WARNING] Realtek Wi-Fi Detected (Known Linux driver issues)${NC}"
fi

# 6. Disk Drive Check
echo -e "\n${YELLOW}[+] STORAGE DRIVE:${NC}"
lsblk -o NAME,ROTA,SIZE,TYPE,MODEL | grep -E "disk|NAME"

# 7. Dual/Single Battery Health Calculation
echo -e "\n${YELLOW}[+] BATTERY HEALTH CHECK:${NC}"
FOUND_BAT=0
for bat in /sys/class/power_supply/BAT*; do
    if [ -d "$bat" ]; then
        FOUND_BAT=1
        BAT_NAME=$(basename "$bat")
        
        FULL=$(cat "$bat/energy_full" 2>/dev/null || cat "$bat/charge_full" 2>/dev/null)
        DESIGN=$(cat "$bat/energy_full_design" 2>/dev/null || cat "$bat/charge_full_design" 2>/dev/null)
        STATUS=$(cat "$bat/status" 2>/dev/null || echo "Unknown")
        
        echo -e "${CYAN}--- $BAT_NAME (Status: $STATUS) ---${NC}"
        if [ -n "$FULL" ] && [ -n "$DESIGN" ] && [ "$DESIGN" -gt 0 ]; then
            HEALTH=$(( FULL * 100 / DESIGN ))
            if [ "$HEALTH" -ge 75 ]; then
                echo -e "Health: ${GREEN}${HEALTH}%${NC} (Good Condition)"
            elif [ "$HEALTH" -ge 50 ]; then
                echo -e "Health: ${YELLOW}${HEALTH}%${NC} (Fair - Moderate Wear)"
            else
                echo -e "Health: ${RED}${HEALTH}%${NC} (Poor - Needs Replacement Soon)"
            fi
        else
            echo "Unable to calculate exact health percentage."
        fi
    fi
done

if [ "$FOUND_BAT" -eq 0 ]; then
    echo -e "${RED}[!] NO BATTERIES DETECTED${NC}"
fi

# 8. Thunderbolt Controller Check (Critical for T480)
echo -e "\n${YELLOW}[+] THUNDERBOLT CONTROLLER:${NC}"
if [ -d "/sys/bus/thunderbolt/devices" ]; then
    echo -e "${GREEN}[OK] Thunderbolt Interface Active & Detected${NC}"
else
    echo -e "${RED}[ALERT] Thunderbolt Controller NOT found or disabled in BIOS!${NC}"
fi

echo -e "\n${CYAN}=================================================="${NC}
echo -e "${CYAN}                 AUDIT COMPLETE                   "${NC}
echo -e "${CYAN}=================================================="${NC}
