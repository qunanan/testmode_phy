import subprocess
import time

class PhyExecutor:
    def __init__(self, config, common_config, bus, addr_int):
        self.config = config
        self.bus = bus
        self.addr = addr_int # 整数格式的 PHY 地址
        
        # 从 common 配置中获取命令模板
        self.templates = common_config.get('cmd_templates', {})
        
        # 获取当前配置指定的模板名称
        cmd_template_name = config.get('cmd_template')
        if cmd_template_name and cmd_template_name in self.templates:
            self.default_tmpl_key = cmd_template_name
        else:
            # 如果没有指定或找不到，使用第一个模板作为默认
            self.default_tmpl_key = next(iter(self.templates)) if self.templates else None
            if cmd_template_name and cmd_template_name not in self.templates:
                print(f"[WARN] Template '{cmd_template_name}' not found in common config. Using default: {self.default_tmpl_key}")


    def _calc_hex_params(self, val_raw, shift, mask_raw):
        """
        处理数值逻辑：
        1. 将输入(字符串或int)转为 int
        2. 执行左移
        3. 格式化为 0xXXXX 字符串
        """
        try:
            val = int(str(val_raw), 0)
            mask = int(str(mask_raw), 0)
            
            val_shifted = val << shift
            
            return f"0x{val_shifted:04x}/0x{mask:04x}"
        except ValueError as e:
            print(f"Data format error: {e}")
            return "0x0000/0x0000"

    def _construct_command(self, template_format, params):
        """
        根据模板和参数构造完整的 mdio 命令列表。
        返回的是一个列表，例如: ['sudo', 'mdio', 'fixed-0', 'phy', '1', 'raw', '0', '0x8000/0x7FFF']
        """
        # 1. 填充模板
        # 模板返回的是一个字符串，例如: "mdio {bus} phy {phy_addr} raw {reg} {data}/{mask}"
        cmd_str_no_sudo = template_format.format(**params)
        
        # 2. 将字符串拆分为列表
        # ['mdio', 'fixed-0', 'phy', '1', 'raw', '0', '0x8000/0x7FFF']
        cmd_list = cmd_str_no_sudo.split()
        
        # 3. 添加 sudo
        return ["sudo"] + cmd_list

    def execute_sequence(self, sequence):
        """执行一系列寄存器操作"""
        print(f"\n[INFO] Starting sequence execution on Bus: {self.bus}, PHY: {self.addr}...")

        for step in sequence:
            # 1. 获取模板
            action = step.get('action', 'WRITE').upper() # 默认为写入操作
            tmpl_key = step.get('template', self.default_tmpl_key)
            if tmpl_key not in self.templates:
                print(f"[ERR] Template '{tmpl_key}' not found in config.")
                continue
            
            tmpl_fmt = self.templates[tmpl_key]['format']

            # 构造命令的基本参数字典
            cmd_params = {
                'bus': self.bus,
                'phy_addr': self.addr,
                'dev_id': step.get('dev_id', 0),
                'reg': step.get('reg'),
                'data': ""
            }
            
            # --- 区分读/写操作 ---
            if action == 'WRITE':
                # 写入操作：需要计算 DATA/MASK
                shift = step.get('shift', 0)
                val = step.get('val', 0)
                mask = step.get('mask', "0xFFFF")
                
                data_hex = self._calc_hex_params(val, shift, mask)
                cmd_params['data'] = data_hex
                
            elif action == 'READ':
                # 读取操作：不需要 DATA/MASK 字段，命令由专门的读取模板构造
                pass
            
            else:
                print(f"[ERR] Unknown action type: {action}. Skipping step.")
                continue

            # 4. 构造完整的命令列表
            full_cmd_list = self._construct_command(tmpl_fmt, cmd_params)

            comment = step.get('comment', '')
            print(f" -> Exec: {' '.join(full_cmd_list):<50} # {comment}")
            
            # 5. 调用系统命令
            try:
                # 使用列表形式执行命令，安全且不会启动 shell
                # check=True: 如果命令返回非零值（失败），则抛出异常
                result = subprocess.run(full_cmd_list, check=True, capture_output=True, text=True)
                # --- 处理返回值 ---
                if action == 'READ':
                    read_val = result.stdout.strip()
                    print(f"    [RESULT] Register {step.get('reg')} value: {read_val}")
            except subprocess.CalledProcessError as e:
                print(f"[FATAL] Command failed with error code {e.returncode}!")
                print(f"  STDERR: {e.stderr.strip()}")
                print(f"  STDOUT: {e.stdout.strip()}")
                print("Aborting sequence.")
                return 
            except FileNotFoundError:
                print("[FATAL] 'sudo' or 'mdio' command not found. Aborting sequence.")
                return

            # 模拟延时 (可选)
            # time.sleep(0.1)

        print("[INFO] Sequence completed.\n")
        # input("Press Enter to continue...")

    def show_menu_recursive(self, options, depth=0):
        """递归显示多级菜单"""
        while True:
            # 打印标题 (仅在顶层打印更清晰，或者每层都打)
            indent = "  " * depth
            print(f"\n{indent}--- Select Option ---")
            
            # 动态生成菜单
            # options 可能是 dict (如 test_modes 的顶层) 或 list (options 数组)
            
            menu_items = []
            if isinstance(options, dict):
                # 处理 test_modes 字典结构
                for key, val in options.items():
                    menu_items.append({"name": key, "content": val})
            elif isinstance(options, list):
                # 处理 options 列表结构
                for item in options:
                    menu_items.append({"name": item['name'], "content": item})

            # 打印选项
            for i, item in enumerate(menu_items):
                print(f"{indent}{i + 1}. {item['name']}")
            print(f"{indent}0. Back/Exit")

            # 获取输入
            try:
                choice = int(input(f"{indent}>> "))
            except ValueError:
                continue

            if choice == 0:
                return # 返回上一级

            if 1 <= choice <= len(menu_items):
                selected = menu_items[choice - 1]['content']
                
                # 判断节点类型
                if 'sub_modes' in selected:
                    # 还有子菜单
                    self.show_menu_recursive(selected['sub_modes'], depth + 1)
                elif 'options' in selected:
                    # 还有子菜单 (test_modes 的下一层)
                    self.show_menu_recursive(selected['options'], depth + 1)
                elif 'sequence' in selected:
                    # 是叶子节点，执行操作
                    self.execute_sequence(selected['sequence'])
                else:
                    # 可能是在 test_modes 顶层，继续往下
                    self.show_menu_recursive(selected, depth + 1)
            else:
                print("Invalid selection.")

    def run(self):
        """启动入口"""
        if not self.config.get('test_modes'):
            print("No test modes defined in configuration.")
            return
        self.show_menu_recursive(self.config['test_modes'])