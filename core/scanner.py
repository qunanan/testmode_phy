import subprocess
import re
import sys

class PhyScanner:
    def __init__(self):
        # 将命令定义为包含 sudo 的列表
        self.mdio_base_cmd = ["sudo", "mdio"] 

    def check_tool(self):
        """检查 mdio 工具是否存在，这里跳过实际执行，只检查 mdio"""
        # 实际检查 sudo 和 mdio 比较复杂，通常我们信任用户已配置 sudo
        try:
            # 仅检查 mdio
            subprocess.run(["mdio", "-h"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            print(f"Error: 'mdio' tool not found. Please install it.")
            sys.exit(1)

    def get_buses(self):
        """列出所有 MDIO 总线"""
        try:
            # 命令：sudo mdio
            res = subprocess.run(self.mdio_base_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[ERR] Failed to execute 'sudo mdio'. Check sudo permissions or mdio installation.")
                print(f"  {res.stderr.strip()}")
                return []
                
            buses = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return buses
        except Exception as e:
            print(f"Error scanning buses: {e}")
            return []

    def scan_devices(self, bus):
        """扫描指定总线下的 PHY 设备"""
        devices = []
        try:
            # 命令：sudo mdio $BUS
            cmd = self.mdio_base_cmd + [bus]
            res = subprocess.run(cmd, capture_output=True, text=True)
            
            if res.returncode != 0:
                print(f"[ERR] Failed to execute {' '.join(cmd)}. Check sudo permissions.")
                print(f"  {res.stderr.strip()}")
                return []

            # 解析 mdio 输出格式，例如:
            # 0x01  0x002b0980  up
            # 正则捕获: (Address) (PHY_ID)
            pattern = re.compile(r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)")
            
            for line in res.stdout.splitlines():
                match = pattern.search(line)
                if match:
                    addr_str = match.group(1)
                    id_str = match.group(2)
                    # 关键修改点：将 PHY ID 转换为整数
                    phy_id_int = int(id_str, 16)
                    
                    # 🚨 过滤条件：只保留 ID 不为零的结果
                    if phy_id_int > 0: 
                        devices.append({
                            "bus": bus,
                            "addr_hex": addr_str,
                            "addr_int": int(addr_str, 16),
                            "phy_id": phy_id_int  # 整数形式的 PHY ID
                        })
        except Exception as e:
            print(f"Error scanning devices on {bus}: {e}")
        
        return devices