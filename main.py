import os
import sys
import glob
import json
from core.scanner import PhyScanner
from core.executor import PhyExecutor

CONFIG_DIR = "configs"

def load_configs():
    """加载 configs 目录下所有的 JSON"""
    configs = []
    common_config = {}
    
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        print(f"[WARN] Config directory '{CONFIG_DIR}' created. Please add JSON files.")
        return configs, common_config

    # 首先加载 common.json
    common_path = os.path.join(CONFIG_DIR, "common.json")
    if os.path.exists(common_path):
        try:
            with open(common_path, 'r') as fp:
                common_config = json.load(fp)
                print(f"[*] Loaded common configuration")
        except Exception as e:
            print(f"[ERR] Failed to load {common_path}: {e}")
    
    # 然后加载其他配置文件
    files = glob.glob(os.path.join(CONFIG_DIR, "*.json"))
    for f in files:
        if os.path.basename(f) == "common.json":
            continue  # 跳过 common.json
            
        try:
            with open(f, 'r') as fp:
                cfg = json.load(fp)
                if 'identity' in cfg:
                    configs.append(cfg)
        except Exception as e:
            print(f"[ERR] Failed to load {f}: {e}")
    return configs, common_config

def match_device(phy_id, configs):
    """
    根据 PHY ID 匹配配置
    逻辑: (Read_ID & Mask) == Config_ID
    """
    for cfg in configs:
        ident = cfg['identity']
        try:
            target_id = int(ident['phy_id'], 0)
            mask = int(ident['phy_id_mask'], 0)
            
            if (phy_id & mask) == target_id:
                return cfg
        except:
            continue
    return None

def main():
    # 检查命令行参数
    debug_mode = '--debug' in sys.argv
    
    print("========================================")
    print("    Ethernet PHY Auto-Tester v2.0")
    print("========================================")
    if debug_mode:
        print("[DEBUG] Debug mode enabled")

    # 1. 准备工作
    print("[*] Loading configurations...")
    configs, common_config = load_configs()
    print(f"[*] Loaded {len(configs)} config files.")

    scanner = PhyScanner(configs, common_config)
    scanner.check_tool()
    
    # 2. 扫描硬件
    print("\n[*] Scanning Hardware buses...")
    buses = scanner.get_buses()
    all_devices = []

    for bus in buses:
        devs = scanner.scan_devices(bus)
        all_devices.extend(devs)

    if not all_devices:
        print("[!] No PHY devices found via mdio.")
        return

    # 3. 列出设备并匹配（不显示，只准备数据）
    valid_devices = []
    
    for i, dev in enumerate(all_devices):
        cfg = match_device(dev['phy_id'], configs)
        
        # 如果没有匹配到特定配置，看看有没有通用的 (ID Mask 为 0 的)
        if not cfg:
            cfg = match_device(0, configs) 
            
        valid_devices.append({
            "hw": dev,
            "cfg": cfg
        })

    # 4. 设备选择和测试循环
    while True:
        # 显示设备列表
        print("\n[+] Found Devices:")
        for i, dev in enumerate(valid_devices):
            chip_name = dev['cfg']['identity']['chip_name'] if dev['cfg'] else "Unknown/No Config"
            print(f"  {i+1}. [{chip_name}]")
            print(f"     Bus: {dev['hw']['bus']} | Addr: {dev['hw']['addr_hex']} | ID: {hex(dev['hw']['phy_id'])}")
        
        # 用户选择设备
        while True:
            try:
                sel = input("\nSelect Target Device (Number, or 'q' to quit): ")
                if sel.lower() == 'q':
                    print("Exiting...")
                    return
                    
                idx = int(sel) - 1
                if 0 <= idx < len(valid_devices):
                    target = valid_devices[idx]
                    break
                else:
                    print("Invalid number.")
            except ValueError:
                if sel.lower() == 'q':
                    print("Exiting...")
                    return
                print("Please enter a number or 'q' to quit.")

        # 5. 启动执行器
        if target['cfg']:
            print(f"\n[*] Starting session for {target['cfg']['identity']['chip_name']}...")
            executor = PhyExecutor(target['cfg'], common_config, target['hw']['bus'], target['hw']['addr_int'], debug_mode)
            
            # 运行执行器，执行完成后自动返回设备列表
            executor.run()
            
            # 执行器运行完成后，对设备进行复位
            executor.reset_device()
        else:
            print("[ERR] No suitable configuration found for this device.")
            continue

if __name__ == "__main__":
    main()