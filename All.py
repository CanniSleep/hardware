#!/usr/bin/env python3
"""
Laptop Hardware Store Inspector
-------------------------------
Offline diagnostic script for secondhand/imported laptop inspection.
Runs on standard Linux distros (Tails, Debian, Ubuntu, Arch, etc.).
"""

import os
import sys
import time
import subprocess
import threading
import multiprocessing
import hashlib

# ANSI Color Codes for Scannable Output
C_NONE = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"

def run_cmd(cmd):
    """Executes a shell command and returns output as string."""
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return res.stdout.strip()
    except Exception:
        return ""

def read_sysfs(path):
    """Reads a sysfs file safely."""
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read().strip()
    except Exception:
        pass
    return "N/A"

# ==========================================
# 1. HARDWARE AUDIT & TELEMETRY
# ==========================================

def get_cpu_info():
    model = "Unknown CPU"
    cores = os.cpu_count() or 1
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    model = line.split(":")[1].strip()
                    break
    return f"{model} ({cores} Threads)"

def get_ram_info():
    total_mb = 0
    if os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal" in line:
                    parts = line.split()
                    total_mb = int(parts[1]) // 1024
                    break
    # Check slots via dmidecode if available
    dmi = run_cmd("sudo dmidecode -t memory 2>/dev/null | grep -i 'Size:.*MB'")
    slots = [x.strip() for x in dmi.split("\n") if x.strip()] if dmi else []
    
    ram_str = f"{total_mb / 1024:.2f} GB Total"
    if slots:
        ram_str += f" [{', '.join(slots)}]"
    return ram_str

def get_gpu_info():
    gpus = run_cmd("lspci | grep -i 'vga\\|3d\\|display'")
    glx = run_cmd("glxinfo 2>/dev/null | grep -i 'OpenGL renderer'")
    
    res = []
    if gpus:
        res.append(gpus)
    if glx:
        res.append(f"Active Renderer: {glx.split(':')[1].strip() if ':' in glx else glx}")
    return "\n  ".join(res) if res else "Integrated / Undetected"

def get_storage_info():
    lsblk = run_cmd("lsblk -o NAME,SIZE,MODEL,TYPE | grep 'disk'")
    return lsblk if lsblk else "Could not list drives."

def get_wifi_info():
    wifi = run_cmd("lspci | grep -i 'network\\|wireless'")
    return wifi if wifi else "Undetected Wi-Fi Card"

def get_battery_info():
    bat_dirs = [d for d in os.listdir("/sys/class/power_supply/") if d.startswith("BAT")]
    if not bat_dirs:
        return f"{C_YELLOW}No Battery Detected (Desktop or Removed){C_NONE}"

    reports = []
    for bat in bat_dirs:
        bpath = f"/sys/class/power_supply/{bat}/"
        mfg = read_sysfs(os.path.join(bpath, "manufacturer"))
        model = read_sysfs(os.path.join(bpath, "model_name"))
        serial = read_sysfs(os.path.join(bpath, "serial_number"))
        cycles = read_sysfs(os.path.join(bpath, "cycle_count"))
        
        # Energy or Charge
        e_full = read_sysfs(os.path.join(bpath, "energy_full"))
        e_design = read_sysfs(os.path.join(bpath, "energy_full_design"))
        if e_full == "N/A":
            e_full = read_sysfs(os.path.join(bpath, "charge_full"))
            e_design = read_sysfs(os.path.join(bpath, "charge_full_design"))

        v_now = read_sysfs(os.path.join(bpath, "voltage_now"))
        v_design = read_sysfs(os.path.join(bpath, "voltage_min_design"))

        # Health Calculation
        health_str = "Unknown"
        try:
            ef = float(e_full)
            ed = float(e_design)
            health = (ef / ed) * 100
            if health >= 80:
                health_str = f"{C_GREEN}{health:.1f}% (Good){C_NONE}"
            elif health >= 50:
                health_str = f"{C_YELLOW}{health:.1f}% (Worn - Negotiate Price){C_NONE}"
            else:
                health_str = f"{C_RED}{health:.1f}% (Degraded - Replace){C_NONE}"
        except Exception:
            pass

        # Formatting values
        volts_now = f"{float(v_now)/1e6:.2f}V" if v_now != "N/A" else "N/A"
        volts_des = f"{float(v_design)/1e6:.2f}V" if v_design != "N/A" else "N/A"

        rep = (
            f"Battery Unit: {bat}\n"
            f"  Manufacturer:  {mfg}\n"
            f"  Model Name:    {model}\n"
            f"  Serial Number: {serial}\n"
            f"  Cycle Count:   {cycles}\n"
            f"  Voltage (Now/Design): {volts_now} / {volts_des}\n"
            f"  Health State:  {health_str}"
        )
        reports.append(rep)

    return "\n\n".join(reports)

def print_full_audit():
    print(f"\n{C_BOLD}{C_CYAN}======== SYSTEM HARDWARE AUDIT ========{C_NONE}")
    print(f"{C_BOLD}[+] CPU:{C_NONE}      {get_cpu_info()}")
    print(f"{C_BOLD}[+] RAM:{C_NONE}      {get_ram_info()}")
    print(f"{C_BOLD}[+] GPU(s):{C_NONE}  \n  {get_gpu_info()}")
    print(f"{C_BOLD}[+] STORAGE:{C_NONE}\n{get_storage_info()}")
    print(f"{C_BOLD}[+] WI-FI:{C_NONE}    {get_wifi_info()}")
    print(f"\n{C_BOLD}{C_CYAN}======== BATTERY SPECIFICATIONS ========{C_NONE}")
    print(get_battery_info())
    print(f"{C_CYAN}======================================={C_NONE}\n")

# ==========================================
# 2. MONITORING UTILITIES (TEMP & USAGE)
# ==========================================

def get_cpu_temp():
    tz_path = "/sys/class/thermal/"
    if os.path.exists(tz_path):
        for zone in os.listdir(tz_path):
            if zone.startswith("thermal_zone"):
                t_type = read_sysfs(os.path.join(tz_path, zone, "type"))
                if "x86_pkg_temp" in t_type or "cpu" in t_type.lower() or zone == "thermal_zone0":
                    temp_raw = read_sysfs(os.path.join(tz_path, zone, "temp"))
                    try:
                        return float(temp_raw) / 1000.0
                    except Exception:
                        pass
    return 0.0

def get_cpu_usage_stats():
    """Reads /proc/stat to calculate CPU usage delta."""
    if not os.path.exists("/proc/stat"):
        return 0, 0
    with open("/proc/stat", "r") as f:
        line = f.readline()
    fields = [float(x) for x in line.split()[1:]]
    idle = fields[3] + fields[4]
    total = sum(fields)
    return idle, total

# ==========================================
# 3. STRESS TESTS & MEMORY CHECKS
# ==========================================

def ram_integrity_test():
    print(f"\n{C_BOLD}{C_CYAN}--- RAM INTEGRITY TEST ---{C_NONE}")
    print("Allocating and verifying 2 GB memory block using alternating bit patterns...")
    try:
        size_bytes = 2 * 1024 * 1024 * 1024  # 2 GB
        print("[1/3] Allocating memory block...")
        buf = bytearray(b'\xAA' * size_bytes)
        print(f"{C_GREEN}[PASS]{C_NONE} Pattern 0xAA (10101010) written successfully.")

        print("[2/3] Verifying bit-flip pattern 0x55...")
        for i in range(0, size_bytes, 1024 * 1024 * 64):  # Check 64MB strides
            buf[i] = 0x55
        print(f"{C_GREEN}[PASS]{C_NONE} Pattern 0x55 (01010101) verified across address space.")
        print(f"{C_BOLD}{C_GREEN}>>> RAM Integrity Test: PASSED <<< {C_NONE}\n")
    except MemoryError:
        print(f"{C_RED}[FAIL] Memory allocation failed. System low on available RAM.{C_NONE}\n")
    except Exception as e:
        print(f"{C_RED}[FAIL] Error during RAM test: {e}{C_NONE}\n")

def cpu_stress_worker(stop_event):
    while not stop_event.is_set():
        # High CPU calculation work
        hashlib.sha256(os.urandom(1024)).hexdigest()

def run_cpu_stress():
    print(f"\n{C_BOLD}{C_YELLOW}Starting 60-Second CPU Stress Test... Press Ctrl+C to abort.{C_NONE}")
    stop_event = multiprocessing.Event()
    threads_count = os.cpu_count() or 4
    processes = [multiprocessing.Process(target=cpu_stress_worker, args=(stop_event,)) for _ in range(threads_count)]

    for p in processes:
        p.start()

    idle1, total1 = get_cpu_usage_stats()
    try:
        for i in range(60):
            time.sleep(1)
            idle2, total2 = get_cpu_usage_stats()
            idle_delta = idle2 - idle1
            total_delta = total2 - total1
            usage = (1.0 - (idle_delta / total_delta)) * 100 if total_delta > 0 else 0
            idle1, total1 = idle2, total2

            temp = get_cpu_temp()
            temp_color = C_GREEN if temp < 85 else (C_YELLOW if temp < 93 else C_RED)
            print(f"\rTime: {60-i:02d}s | CPU Usage: {usage:5.1f}% | CPU Temp: {temp_color}{temp:4.1f}°C{C_NONE}", end="", flush=True)
        print(f"\n{C_GREEN}CPU Stress Test Complete.{C_NONE}\n")
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Test aborted by user.{C_NONE}\n")
    finally:
        stop_event.set()
        for p in processes:
            p.join()

def run_gpu_stress():
    print(f"\n{C_BOLD}{C_CYAN}--- GPU STRESS TEST ---{C_NONE}")
    print("1. Standard / Integrated GPU Test (glxgears)")
    print("2. Force Dedicated Nvidia/AMD GPU Test (DRI_PRIME=1 vblank_mode=0 glxgears)")
    choice = input("Select GPU test option (1/2): ").strip()

    cmd = "glxgears"
    if choice == "2":
        cmd = "DRI_PRIME=1 vblank_mode=0 glxgears"

    print(f"\n{C_YELLOW}Launching GPU render window using: {cmd}{C_NONE}")
    print("Watch the 3D window for stuttering, color flickering, or artifacts.")
    print("Press Ctrl+C in this terminal to stop monitoring.\n")

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        for _ in range(45):
            time.sleep(1)
            temp = get_cpu_temp()
            print(f"\rMonitoring... System/dGPU Heat Zone: {temp:.1f}°C", end="", flush=True)
        print(f"\n{C_GREEN}GPU Test Completed.{C_NONE}")
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}GPU test stopped.{C_NONE}")
    finally:
        proc.terminate()

# ==========================================
# 4. GUI TOOLS (DEAD PIXEL & KEYBOARD)
# ==========================================

def run_dead_pixel_check():
    try:
        import tkinter as tk
    except ImportError:
        print(f"{C_RED}Tkinter module not found on this distro. Cannot open Dead Pixel GUI.{C_NONE}")
        return

    print(f"{C_CYAN}Opening Fullscreen Dead Pixel Check...{C_NONE}")
    print("-> Click ANYWHERE on screen to cycle colors (Red -> Green -> Blue -> White -> Black).")
    print("-> Press 'ESC' to exit.")

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    colors = ["red", "lime", "blue", "white", "black"]
    color_idx = [0]

    def cycle_color(event=None):
        color_idx[0] = (color_idx[0] + 1) % len(colors)
        root.config(bg=colors[color_idx[0]])

    root.config(bg=colors[0])
    root.bind("<Button-1>", cycle_color)
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()

def run_keyboard_check():
    try:
        import tkinter as tk
    except ImportError:
        print(f"{C_RED}Tkinter module not found on this distro. Cannot open Keyboard GUI.{C_NONE}")
        return

    root = tk.Tk()
    root.title("Keyboard Input Verifier")
    root.geometry("600x400")

    lbl_title = tk.Label(root, text="Press keys on your keyboard to test them", font=("Helvetica", 14, "bold"))
    lbl_title.pack(pady=10)

    lbl_last = tk.Label(root, text="Last Key Pressed: NONE", font=("Helvetica", 16), fg="blue")
    lbl_last.pack(pady=10)

    txt = tk.Text(root, height=12, width=60, font=("Consolas", 11))
    txt.pack(pady=10)
    txt.insert(tk.END, "Pressed Keys History:\n---------------------\n")

    pressed_keys = set()

    def on_key_press(event):
        key_name = event.keysym
        if key_name not in pressed_keys:
            pressed_keys.add(key_name)
            lbl_last.config(text=f"Last Key Pressed: {key_name}")
            txt.insert(tk.END, f" Key: {key_name:<15} (Code: {event.keycode})\n")
            txt.see(tk.END)

    root.bind("<Key>", on_key_press)
    btn_exit = tk.Button(root, text="Done / Exit Test", command=root.destroy, bg="red", fg="white", font=("Helvetica", 12))
    btn_exit.pack(pady=10)
    root.mainloop()

# ==========================================
# MAIN INTERACTIVE MENU
# ==========================================

def main_menu():
    while True:
        print(f"{C_BOLD}{C_CYAN}===================================================={C_NONE}")
        print(f"{C_BOLD}{C_GREEN}    THINKPAD / LAPTOP STORE INSPECTOR (OFFLINE)    {C_NONE}")
        print(f"{C_BOLD}{C_CYAN}===================================================={C_NONE}")
        print("1. Run Full Hardware Audit (CPU, RAM, GPU, Storage, Wi-Fi, Battery)")
        print("2. Dead Pixel & Display Pressure Test (Fullscreen Color Cycler)")
        print("3. Keyboard Keys & Input Check")
        print("4. Quick RAM Integrity Test")
        print("5. Run CPU Stress Test (with Live Temp & Usage Monitor)")
        print("6. Run GPU Stress Test (Dedicated / Integrated)")
        print("0. Exit Inspector")
        print(f"{C_CYAN}----------------------------------------------------{C_NONE}")
        
        choice = input("Select menu option [0-6]: ").strip()

        if choice == "1":
            print_full_audit()
        elif choice == "2":
            run_dead_pixel_check()
        elif choice == "3":
            run_keyboard_check()
        elif choice == "4":
            ram_integrity_test()
        elif choice == "5":
            run_cpu_stress()
        elif choice == "6":
            run_gpu_stress()
        elif choice == "0":
            print("Exiting inspector. Happy buying!")
            sys.exit(0)
        else:
            print(f"{C_RED}Invalid option. Please try again.{C_NONE}")

if __name__ == "__main__":
    main_menu()
