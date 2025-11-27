# Ethernet PHY Auto-Tester v2.0

一个用于以太网PHY芯片自动化测试的Python工具，支持多种PHY芯片的识别、配置和测试模式设置。

## 功能特性

- **自动硬件扫描**：自动扫描MDIO总线上的所有PHY设备
- **智能芯片识别**：通过PHY ID自动识别芯片型号并匹配对应配置
- **多厂商支持**：支持Marvell、TI等多个厂商的PHY芯片
- **测试模式配置**：提供完整的测试模式设置，包括：
  - 10BASE-T测试模式（Link Pulse、Standard、Harmonic Content）
  - 100BASE-TX测试模式
  - 1000BASE-T测试模式（Test Mode 1/2/4）
  - 发射器失真测试等
- **交互式菜单**：友好的命令行界面，支持多级菜单选择
- **灵活配置**：通过JSON配置文件轻松添加新的PHY芯片支持

## 支持的芯片型号

- **Marvell 88Q2112** (Automotive)
- **Marvell AQrate Series PHY**
- **TI DP8386x Series PHY**

## 系统依赖

### 必需依赖
- Python 3.6+
- Linux操作系统
- sudo权限（用于执行mdio命令）

### 系统工具
- `mdio` 命令行工具（MDIO总线访问工具）

### 安装mdio工具
```bash
# Ubuntu/Debian系统
sudo apt-get install mdio-tools

# 或从源码编译安装
git clone https://github.com/wkz/mdio-tools
cd mdio-tools
make && sudo make install
```

## 项目结构

```
testmode_phy/
├── main.py              # 主程序入口
├── README.md            # 项目说明文档
├── core/                # 核心模块
│   ├── __init__.py
│   ├── scanner.py        # PHY设备扫描器
│   └── executor.py       # 测试序列执行器
└── configs/             # 配置文件目录
    ├── common.json       # 通用配置和命令模板
    ├── marvell_88q2112.json  # Marvell 88Q2112配置
    ├── marvell_aqx.json       # Marvell AQrate配置
    └── ti_dp8386x.json        # TI DP8386x配置
```

## 使用方法

### 1. 基本使用

```bash
# 运行主程序
python3 main.py
```

### 2. 运行流程

1. **加载配置**：程序会自动加载`configs/`目录下的所有JSON配置文件
2. **扫描硬件**：扫描所有MDIO总线，检测PHY设备
3. **设备匹配**：根据PHY ID自动匹配对应的芯片配置
4. **选择设备**：用户从检测到的设备列表中选择目标设备
5. **执行测试**：进入交互式测试菜单，选择所需的测试模式

### 3. 配置文件说明

#### common.json
定义通用的命令模板：
```json
{
  "cmd_templates": {
    "std_c22": {
      "format": "mdio {bus} phy {phy_addr} raw {reg} {data}",
      "desc": "Standard Clause 22"
    },
    "marvell_mmd": {
      "format": "mdio {bus} mmd {phy_addr}:{dev_id} raw {reg} {data}",
      "desc": "Marvell Indirect MMD"
    }
  }
}
```

#### 芯片配置文件
每个芯片配置文件包含：
- `identity`: 芯片识别信息（PHY ID、掩码、芯片名称）
- `cmd_template`: 使用的命令模板
- `test_modes`: 测试模式和操作序列

## 使用示例

### 示例1：扫描和识别PHY设备
```bash
$ python3 main.py
========================================
    Ethernet PHY Auto-Tester v2.0
========================================
[*] Loading configurations...
[*] Loaded 3 config files.

[*] Scanning Hardware buses...
    [*] Attempting Read ID on bus mdio0 addr 0x01 using config ti_dp8386x (template: std_c22)...
    -> Exec: sudo mdio mdio0 phy 1 raw 0x02
    [RESULT] Register 0x02 value: 0x2000
    -> Exec: sudo mdio mdio0 phy 1 raw 0x03
    [RESULT] Register 0x03 value: 0xa230
    [+] Successfully read PHY ID: 0x2000a230

[+] Found Devices:
  1. [TI DP8386x Series PHY]
     Bus: mdio0 | Addr: 0x01 | ID: 0x2000a230

Select Target Device (Number): 1
```

### 示例2：执行测试模式
```
[*] Starting session for TI DP8386x Series PHY...

--- Select Option ---
1. 10M_Test_Mode
2. 100M_Test_Mode
3. 1000M_Test_Mode
4. General_Ops
0. Back/Exit
>> 1

--- Select Option ---
1. 10BASE-T Link Pulse MDI
2. 10BASE-T Link Pulse MDIX
3. 10BASE-T Standard MDI
4. 10BASE-T Standard MDIX
5. 10BASE-T Harmonic Content MDI
6. 10BASE-T Harmonic Content MDIX
0. Back/Exit
>> 1

 -> Exec: sudo mdio mdio0 phy 1 raw 0x1f 0x8000/0x0000 # Bit 15 Reset
 -> Exec: sudo mdio mdio0 phy 1 raw 0x00 0x0100/0x0000 # 将 DUT 编程为 10Base-T 模式
 -> Exec: sudo mdio mdio0 phy 1 raw 0x10 0x5008/0x0000 # 将 DUT 编程为强制 MDI
 -> Exec: sudo mdio mdio0 phy 1 raw 0x1f 0x4000/0x0000 # 重新启动 PHY
[INFO] Sequence completed.
```

## 添加新芯片支持

要添加新的PHY芯片支持，只需在`configs/`目录下创建新的JSON配置文件：

1. **创建配置文件**：以芯片型号命名，如`new_chip.json`
2. **定义芯片信息**：
```json
{
  "identity": {
    "chip_name": "New Chip Series",
    "phy_id": "0x12345678",
    "phy_id_mask": "0xFFFFFFFF"
  },
  "cmd_template": "std_c22",
  "test_modes": {
    "General_Ops": {
      "options": [
        {
          "name": "Read ID",
          "sequence": [
            { "action": "READ", "reg": "0x02", "comment": "Read PHY ID 1" },
            { "action": "READ", "reg": "0x03", "comment": "Read PHY ID 2" }
          ]
        }
      ]
    }
  }
}
```
3. **添加测试模式**：根据芯片手册添加相应的测试序列

## 故障排除

### 常见问题

1. **找不到mdio命令**
   ```bash
   # 检查是否安装
   which mdio
   
   # 如果未安装，参考上面的安装说明
   ```

2. **权限不足**
   ```bash
   # 确保当前用户有sudo权限
   sudo -v
   
   # 检查mdio设备权限
   ls -la /dev/mdio*
   ```

3. **无法检测到PHY设备**
   - 检查硬件连接
   - 确认MDIO总线名称
   - 检查PHY地址是否正确

4. **配置文件加载失败**
   - 检查JSON格式是否正确
   - 确认文件在`configs/`目录下
   - 查看错误信息了解具体问题

### 调试模式

程序会输出详细的执行信息，包括：
- 配置文件加载状态
- 硬件扫描结果
- 命令执行详情
- 寄存器读取值

## 许可证

本项目采用开源许可证，具体请查看LICENSE文件。

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。在提交代码前，请确保：
1. 代码符合PEP8规范
2. 添加适当的注释和文档
3. 测试新的功能
4. 更新相关文档
