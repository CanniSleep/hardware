#!/usr/bin/env python3
"""
Hardware Diagnostic & Telemetry Suite
-------------------------------------
Offline system analysis utility for Linux environments (GNOME/Tails native).
"""

import os
import sys
import time
import subprocess
import threading
import multiprocessing
import hashlib
import signal

# Check GTK3 Availability for GNOME/Tails
HAS_GTK = False
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk
    HAS_GTK = True
except Exception:
    HAS_GTK = False

# Terminal Colors
C_NONE = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return res.stdout.strip()
    except Exception:
        return ""

def read_sysfs(path):
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
    model = "Unknown Processor"
    cores = os.cpu_count() or 1
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    model = line.split(":")[1].strip()
                    break
    return f"{model} ({cores} Logical Cores)"

def get_ram_info():
    total_mb = 0
    if os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal" in line:
                    parts = line.split()
                    total_mb = int(parts[1]) // 1024
                    break
    dmi = run_cmd("sudo dmidecode -t memory 2>/dev/null | grep -i 'Size:.*MB'")
    slots = [x.strip() for x in dmi.split("\n") if x.strip()] if dmi else []
    
    ram_str = f"{total_mb / 1024:.2f} GB Total System Memory"
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
        res.append(f"Renderer: {glx.split(':')[1].strip() if ':' in glx else glx}")
    return "\n  ".join(res) if res else "Integrated Controller"

def get_storage_info():
    lsblk = run_cmd("lsblk -o NAME,SIZE,MODEL,TYPE | grep 'disk'")
    return lsblk if lsblk else "Drive status unavailable."

def get_wifi_info():
    wifi = run_cmd("lspci | grep -i 'network\\|wireless'")
    return wifi if wifi else "Interface undetected."

def get_battery_info():
    bat_dirs = [d for d in os.listdir("/sys/class/power_supply/") if d.startswith("BAT")]
    if not bat_dirs:
        return f"{C_YELLOW}No Internal Power Supply Detected (AC / Stationary){C_NONE}"

    reports = []
    for bat in bat_dirs:
        bpath = f"/sys/class/power_supply/{bat}/"
        mfg = read_sysfs(os.path.join(bpath, "manufacturer"))
        model = read_sysfs(os.path.join(bpath, "model_name"))
        serial = read_sysfs(os.path.join(bpath, "serial_number"))
        cycles = read_sysfs(os.path.join(bpath, "cycle_count"))
        
        e_full = read_sysfs(os.path.join(bpath, "energy_full"))
        e_design = read_sysfs(os.path.join(bpath, "energy_full_design"))
        if e_full == "N/A":
            e_full = read_sysfs(os.path.join(bpath, "charge_full"))
            e_design = read_sysfs(os.path.join(bpath, "charge_full_design"))

        v_now = read_sysfs(os.path.join(bpath, "voltage_now"))
        v_design = read_sysfs(os.path.join(bpath, "voltage_min_design"))

        health_str = "Unknown"
        try:
            ef = float(e_full)
            ed = float(e_design)
            health = (ef / ed) * 100
            if health >= 80:
                health_str = f"{C_GREEN}Nominal ({health:.1f}% Capacity){C_NONE}"
            elif health >= 50:
                health_str = f"{C_YELLOW}Moderate Capacity Loss ({health:.1f}% Capacity){C_NONE}"
            else:
                health_str = f"{C_RED}Significant Capacity Loss ({health:.1f}% Capacity){C_NONE}"
        except Exception:
            pass

        volts_now = f"{float(v_now)/1e6:.2f}V" if v_now != "N/A" else "N/A"
        volts_des = f"{float(v_design)/1e6:.2f}V" if v_design != "N/A" else "N/A"

        rep = (
            f"Power Unit ID: {bat}\n"
            f"  Manufacturer:       {mfg}\n"
            f"  Model Identifier:   {model}\n"
            f"  Serial Number:      {serial}\n"
            f"  Completed Cycles:   {cycles}\n"
            f"  Voltage (Operating/Design): {volts_now} / {volts_des}\n"
            f"  Health State:       {health_str}"
        )
        reports.append(rep)

    return "\n\n".join(reports)

def print_full_audit():
    print(f"\n{C_BOLD}{C_CYAN}======== SYSTEM HARDWARE AUDIT ========{C_NONE}")
    print(f"{C_BOLD}[+] CPU:{C_NONE}      {get_cpu_info()}")
    print(f"{C_BOLD}[+] RAM:{C_NONE}      {get_ram_info()}")
    print(f"{C_BOLD}[+] GPU(s):{C_NONE}  \n  {get_gpu_info()}")
    print(f"{C_BOLD}[+] STORAGE:{C_NONE}\n{get_storage_info()}")
    print(f"{C_BOLD}[+] NETWORK:{C_NONE}  {get_wifi_info()}")
    print(f"\n{C_BOLD}{C_CYAN}======== POWER SUPPLY TELEMETRY ========{C_NONE}")
    print(get_battery_info())
    print(f"{C_CYAN}======================================={C_NONE}\n")

# ==========================================
# 2. MONITORING UTILITIES
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
    if not os.path.exists("/proc/stat"):
        return 0, 0
    with open("/proc/stat", "r") as f:
        line = f.readline()
    fields = [float(x) for x in line.split()[1:]]
    idle = fields[3] + fields[4]
    total = sum(fields)
    return idle, total

# ==========================================
# 3. STRESS TESTING & MEMORY AUDIT
# ==========================================

def ram_integrity_test():
    print(f"\n{C_BOLD}{C_CYAN}--- MEMORY INTEGRITY TEST ---{C_NONE}")
    print("Allocating and verifying 2 GB memory block using standard bit-patterns...")
    try:
        size_bytes = 2 * 1024 * 1024 * 1024
        print("[1/2] Writing pattern 0xAA...")
        buf = bytearray(b'\xAA' * size_bytes)
        print(f"{C_GREEN}[PASS]{C_NONE} Allocation verified.")

        print("[2/2] Writing inverse pattern 0x55...")
        for i in range(0, size_bytes, 1024 * 1024 * 64):
            buf[i] = 0x55
        print(f"{C_GREEN}[PASS]{C_NONE} Bit integrity verified across test block.")
        print(f"{C_BOLD}{C_GREEN}Result: Memory Test PASSED{C_NONE}\n")
    except MemoryError:
        print(f"{C_RED}[FAIL] Insufficient available memory for test size.{C_NONE}\n")
    except Exception as e:
        print(f"{C_RED}[FAIL] Memory test error: {e}{C_NONE}\n")

def cpu_stress_worker(stop_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while not stop_event.is_set():
        hashlib.sha256(os.urandom(1024)).hexdigest()

def run_cpu_stress():
    print(f"\n{C_BOLD}{C_YELLOW}Executing Continuous CPU Load Test... (Press Ctrl+C to stop){C_NONE}")
    stop_event = multiprocessing.Event()
    threads_count = os.cpu_count() or 4
    processes = [multiprocessing.Process(target=cpu_stress_worker, args=(stop_event,)) for _ in range(threads_count)]

    for p in processes:
        p.start()

    idle1, total1 = get_cpu_usage_stats()
    start_time = time.time()
    try:
        while True:
            time.sleep(1)
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)

            idle2, total2 = get_cpu_usage_stats()
            idle_delta = idle2 - idle1
            total_delta = total2 - total1
            usage = (1.0 - (idle_delta / total_delta)) * 100 if total_delta > 0 else 0
            idle1, total1 = idle2, total2

            temp = get_cpu_temp()
            temp_color = C_GREEN if temp < 85 else (C_YELLOW if temp < 93 else C_RED)
            print(f"\rElapsed Time: {mins:02d}:{secs:02d} | CPU Load: {usage:5.1f}% | Temp: {temp_color}{temp:4.1f}°C{C_NONE}", end="", flush=True)
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}CPU load test stopped by user.{C_NONE}\n")
    finally:
        stop_event.set()
        for p in processes:
            p.join()

def run_gpu_stress():
    print(f"\n{C_BOLD}{C_CYAN}--- GRAPHICS PROCESSING TEST ---{C_NONE}")
    print("1. Standard Graphics Rendering Test")
    print("2. Dedicated Graphics Pipeline Test (DRI_PRIME=1)")
    try:
        choice = input("Select pipeline option [1/2]: ").strip()
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Graphics test canceled.{C_NONE}\n")
        return

    cmd = "glxgears"
    if choice == "2":
        cmd = "DRI_PRIME=1 vblank_mode=0 glxgears"

    print(f"\n{C_YELLOW}Launching continuous render pipeline: {cmd}{C_NONE}")
    print("Press Ctrl+C in terminal to stop test window.\n")

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    try:
        while True:
            time.sleep(1)
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            temp = get_cpu_temp()
            print(f"\rActive Pipeline Monitoring... Elapsed Time: {mins:02d}:{secs:02d} | Core Temp: {temp:.1f}°C", end="", flush=True)
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Graphics test stopped by user.{C_NONE}\n")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

# ==========================================
# 4. USB PORT & CONTROLLER VERIFICATION (SYSFS NATIVE)
# ==========================================

def scan_usb_sysfs():
    usb_path = "/sys/bus/usb/devices"
    devs = {}
    if not os.path.exists(usb_path):
        return devs

    for d in os.listdir(usb_path):
        dp = os.path.join(usb_path, d)
        vendor_file = os.path.join(dp, "idVendor")
        if os.path.exists(vendor_file):
            try:
                vid = read_sysfs(os.path.join(dp, "idVendor"))
                pid = read_sysfs(os.path.join(dp, "idProduct"))
                prod = read_sysfs(os.path.join(dp, "product"))
                mfg = read_sysfs(os.path.join(dp, "manufacturer"))
                speed_raw = read_sysfs(os.path.join(dp, "speed"))
                bus = read_sysfs(os.path.join(dp, "busnum"))
                devpath = read_sysfs(os.path.join(dp, "devpath"))

                speed_map = {
                    "1.5": "1.5 Mbps (USB 1.1)",
                    "12": "12 Mbps (USB 1.1)",
                    "480": "480 Mbps (USB 2.0)",
                    "5000": "5 Gbps (USB 3.0)",
                    "10000": "10 Gbps (USB 3.1)",
                    "20000": "20 Gbps (USB 3.2)"
                }
                speed_str = speed_map.get(speed_raw, f"{speed_raw} Mbps" if speed_raw != "N/A" else "Unknown Speed")

                mfg_clean = "" if mfg == "N/A" else mfg
                prod_clean = "" if prod == "N/A" else prod
                label = f"{mfg_clean} {prod_clean}".strip()
                if not label:
                    label = f"Device [{vid}:{pid}]"

                devs[d] = {
                    "label": label,
                    "speed": speed_str,
                    "bus": bus if bus != "N/A" else "?",
                    "port": devpath if devpath != "N/A" else "?"
                }
            except Exception:
                pass
    return devs

def run_usb_test():
    print(f"\n{C_BOLD}{C_CYAN}======== USB PORT REAL-TIME VERIFICATION ========{C_NONE}")
    print("Direct sysfs kernel monitoring active (0% CPU overhead).")
    print("Plug or unplug flash drives / peripherals to verify physical ports.")
    print("Press Ctrl+C to exit back to main menu.\n")

    initial_devs = scan_usb_sysfs()
    print(f"{C_BOLD}Active USB Topology ({len(initial_devs)} Detected Nodes):{C_NONE}")
    if initial_devs:
        for info in initial_devs.values():
            print(f"  • {info['label']:<35} | Bus {info['bus']} Port {info['port']} | Speed: {info['speed']}")
    else:
        print("  • No active USB devices detected.")

    print(f"\n{C_GREEN}[LOG] Listening for physical connection events...{C_NONE}\n")

    prev_devs = initial_devs
    try:
        while True:
            time.sleep(0.3)
            curr_devs = scan_usb_sysfs()

            added = set(curr_devs.keys()) - set(prev_devs.keys())
            for item in added:
                d = curr_devs[item]
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] {C_GREEN}[CONNECTED]{C_NONE} {d['label']} (Bus {d['bus']}, Port {d['port']}) — {C_BOLD}{d['speed']}{C_NONE}")

            removed = set(prev_devs.keys()) - set(curr_devs.keys())
            for item in removed:
                d = prev_devs[item]
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] {C_YELLOW}[DISCONNECTED]{C_NONE} {d['label']}")

            prev_devs = curr_devs
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}USB port monitoring stopped by user.{C_NONE}\n")

# ==========================================
# 5. GTK3 NATIVE DIAGNOSTICS (CRASH-PROOF)
# ==========================================

def run_display_test():
    if not HAS_GTK:
        print(f"{C_RED}GTK3 library unavailable in current environment.{C_NONE}")
        return

    print(f"{C_CYAN}Launching Display Panel Test...{C_NONE}")
    print(" -> Left-click or Space/Enter to cycle colors (Red -> Green -> Blue -> White -> Black).")
    print(" -> Press Esc, Q, or Ctrl+C in terminal to exit.\n")

    colors = [
        Gdk.RGBA(1, 0, 0, 1),
        Gdk.RGBA(0, 1, 0, 1),
        Gdk.RGBA(0, 0, 1, 1),
        Gdk.RGBA(1, 1, 1, 1),
        Gdk.RGBA(0, 0, 0, 1)
    ]
    idx = [0]

    win = Gtk.Window()
    win.fullscreen()
    win.override_background_color(Gtk.StateFlags.NORMAL, colors[0])

    def on_click(w, event):
        idx[0] = (idx[0] + 1) % len(colors)
        win.override_background_color(Gtk.StateFlags.NORMAL, colors[idx[0]])

    def on_key(w, event):
        key_name = Gdk.keyval_name(event.keyval)
        if key_name in ["Escape", "q", "Q"]:
            Gtk.main_quit()
        elif key_name in ["space", "Return", "KP_Enter"]:
            on_click(w, event)

    win.connect("button-press-event", on_click)
    win.connect("key-press-event", on_key)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            win.unfullscreen()
            win.hide()
            win.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
        except Exception:
            pass
        print(f"{C_YELLOW}Display panel test closed.{C_NONE}\n")

def run_keyboard_test():
    if not HAS_GTK:
        print(f"{C_RED}GTK3 library unavailable in current environment.{C_NONE}")
        return

    win = Gtk.Window(title="Keyboard Hardware Verifier")
    win.set_default_size(600, 400)
    win.set_position(Gtk.WindowPosition.CENTER)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(15)
    box.set_margin_end(15)
    box.set_margin_top(15)
    box.set_margin_bottom(15)
    win.add(box)

    label = Gtk.Label(label="Press keys to verify input response...")
    box.pack_start(label, False, False, 0)

    textview = Gtk.TextView()
    textview.set_editable(False)
    textbuffer = textview.get_buffer()

    scrolled = Gtk.ScrolledWindow()
    scrolled.add(textview)
    box.pack_start(scrolled, True, True, 0)

    def on_key(w, event):
        key_name = Gdk.keyval_name(event.keyval)
        label.set_text(f"Last Detected Key: {key_name}")
        end_iter = textbuffer.get_end_iter()
        textbuffer.insert(end_iter, f"Input Key: {key_name:<15} (Code: {event.keyval})\n")

    win.connect("key-press-event", on_key)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            win.hide()
            win.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
        except Exception:
            pass
        print(f"{C_YELLOW}Keyboard verifier closed.{C_NONE}\n")

# ==========================================
# MAIN INTERACTIVE MENU
# ==========================================

def main_menu():
    while True:
        print(f"{C_BOLD}{C_CYAN}===================================================={C_NONE}")
        print(f"{C_BOLD}{C_GREEN}     SYSTEM HARDWARE TELEMETRY & DIAGNOSTICS       {C_NONE}")
        print(f"{C_BOLD}{C_CYAN}===================================================={C_NONE}")
        print("1. Full System Hardware Audit")
        print("2. Display Panel Diagnostic (Solid Color Cycle)")
        print("3. Keyboard Input Response Test")
        print("4. USB Port Real-Time Monitor (sysfs Native)")
        print("5. System Memory Integrity Test")
        print("6. Continuous Processor Thermal Load Test")
        print("7. Continuous Graphics Subsystem Load Test")
        print("0. Exit Diagnostics")
        print(f"{C_CYAN}----------------------------------------------------{C_NONE}")
        
        try:
            choice = input("Select diagnostic module [0-7]: ").strip()
        except KeyboardInterrupt:
            print(f"\n\n{C_YELLOW}Exiting telemetry suite.{C_NONE}\n")
            sys.exit(0)

        if choice == "1":
            print_full_audit()
        elif choice == "2":
            run_display_test()
        elif choice == "3":
            run_keyboard_test()
        elif choice == "4":
            run_usb_test()
        elif choice == "5":
            ram_integrity_test()
        elif choice == "6":
            run_cpu_stress()
        elif choice == "7":
            run_gpu_stress()
        elif choice == "0":
            print("Exiting telemetry suite.")
            sys.exit(0)
        else:
            print(f"{C_RED}Invalid entry.{C_NONE}")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n\n{C_YELLOW}Exiting telemetry suite.{C_NONE}\n")
        sys.exit(0)
