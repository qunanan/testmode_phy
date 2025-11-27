import subprocess
import re
import sys
import json
import os

class PhyScanner:
    def __init__(self, configs, common_config):
        # 将命令定义为包含 sudo 的列表
        self.mdio_base_cmd = ["sudo", "mdio"]
        # 加载配置文件
        self.configs = configs
        self.common_config = common_config

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

    def scan_devices(self, bus, config_filename=None):
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
                    
                    # 🚨 如果 ID 为 0，使用 Read ID 指令重新获取
                    if phy_id_int == 0:
                        phy_id_int = self.read_phy_id(bus, addr_str)
                    
                    # 只保留 ID 不为零的结果
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
    
    def read_phy_id(self, bus, addr_hex):
        """使用所有configs中定义的Read ID方法来获取硬件ID，保留返回id不为零的结果并返回"""
        valid_ids = []
        # 遍历所有配置文件中的Read ID方法
        for config_data in self.configs:
            config_name = config_data.get('config_name', 'Unnamed Config')
            if not config_data.get('cmd_template'):
                continue
            # 获取当前配置指定的模板名称
            tmpl_key = config_data.get('cmd_template')
            if not tmpl_key:
                continue
            # 查找General_Ops中的Read ID选项
            if 'test_modes' in config_data and 'General_Ops' in config_data['test_modes']:
                general_ops = config_data['test_modes']['General_Ops']
                if 'options' in general_ops:
                    for option in general_ops['options']:
                        if option.get('name') == 'Read ID' and 'sequence' in option:
                            sequence = option['sequence']
                            # 执行Read ID序列
                            phy_id = self._execute_read_id_sequence(bus, addr_hex, sequence, tmpl_key)
                            if phy_id > 0:
                                valid_ids.append(phy_id)
                                print(f"    [+] Successfully read PHY ID: 0x{phy_id:08x}")
        
        # 返回第一个有效的ID（如果有的话）
        return valid_ids[0] if valid_ids else 0
    
    def _execute_read_id_sequence(self, bus, addr_hex, sequence, template_name):
        """执行Read ID序列并返回PHY ID，参考executor.py的实现方式"""
        try:
            read_values = []
            
            # 从 common 配置中获取命令模板
            templates = self.common_config.get('cmd_templates', {})
            
            for step in sequence:
                action = step.get('action', 'WRITE').upper()
                if action != 'READ':
                    continue

                tmpl_key = step.get('cmd', template_name)
    
                # 获取模板格式
                if tmpl_key not in templates:
                    print(f"    [!] Template '{template_name}' not found in templates")
                    return 0
                    
                tmpl_fmt = templates[tmpl_key]['format']
                
                # 构造命令参数
                cmd_params = {
                    'bus': bus,
                    'phy_addr': int(addr_hex, 16),  # 转换为整数
                    'dev_id': step.get('dev_id', 0),
                    'reg': step.get('reg'),
                    'data': ""
                }
                
                # 构造命令字符串
                cmd_str_no_sudo = tmpl_fmt.format(**cmd_params)
                cmd_list = cmd_str_no_sudo.split()
                full_cmd_list = ["sudo"] + cmd_list
                
                comment = step.get('comment', '')
                # print(f"    -> Exec: {' '.join(full_cmd_list):<50} # {comment}")
                
                # 执行命令
                try:
                    result = subprocess.run(full_cmd_list, check=True, capture_output=True, text=True)
                    if action == 'READ':
                        read_val = result.stdout.strip()
                        # print(f"    [RESULT] Register {step.get('reg')} value: {read_val}")
                        read_values.append(int(read_val, 16))
                except subprocess.CalledProcessError as e:
                    print(f"    [!] Failed to read register {step.get('reg')}")
                    print(f"      STDERR: {e.stderr.strip()}")
                    return 0
                except FileNotFoundError:
                    print("    [!] 'sudo' or 'mdio' command not found.")
                    return 0
            
            # 如果读取了两个值（PHY ID1 和 PHY ID2），合并它们
            if len(read_values) >= 2:
                full_phy_id = (read_values[0] << 16) | read_values[1]
                return full_phy_id
            elif len(read_values) == 1:
                return read_values[0]
            
        except Exception as e:
            print(f"Error executing Read ID sequence for {bus} addr {addr_hex}: {e}")
        
        return 0
