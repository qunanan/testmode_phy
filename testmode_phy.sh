#!/bin/bash
set -euo pipefail

# 配置文件路径
CONFIG_FILE="phy_config.json"
# 默认PHY类型
DEFAULT_PHY_TYPE="AQR1113"

# 检查配置文件是否存在
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "\033[0;31m错误：配置文件$CONFIG_FILE不存在\033[0m"
    exit 1
fi

# 检查jq工具是否安装
if ! command -v jq &> /dev/null; then
    echo -e "\033[0;31m错误：需要安装jq工具来解析JSON配置文件\033[0m"
    exit 1
fi

# 颜色定义
GREEN="\033[0;32m"
RED="\033[0;31m"
NC="\033[0m"

# 全局变量
current_bus=""
last_selected_mode=""
current_phy_type="$DEFAULT_PHY_TYPE"

# 从配置文件获取值的函数
get_config() {
    local path="$1"
    jq -r ".$path" "$CONFIG_FILE" 2>/dev/null | sed 's/^null$//'
}

# 函数：执行PHY复位并等待就绪
reset_phy() {
    local bus="$1"
    echo -e "\n${GREEN}=== 执行PHY复位 ===${NC}"
    local reset_reg=$(get_config "phy_types.${current_phy_type}.registers.PHY_RESET")
    sudo mdio "$bus" $reset_reg  # 触发软复位
    echo "等待PHY复位完成..."
    sleep 1  # 等待复位生效（可根据硬件调整延时）
    echo -e "${GREEN}PHY复位成功${NC}"
}

# 步骤1：选择PHY类型
select_phy_type() {
    echo -e "\n${GREEN}=== 选择PHY类型 ===${NC}"
    local phy_types=($(jq -r '.phy_types | keys[]' "$CONFIG_FILE"))
    
    for ((i=0; i<${#phy_types[@]}; i++)); do
        echo "$((i+1))) ${phy_types[$i]}"
    done
    
    echo -n "请选择PHY类型编号（默认：${DEFAULT_PHY_TYPE}）: "
    read -r phy_index
    if [ -z "$phy_index" ]; then
        current_phy_type="$DEFAULT_PHY_TYPE"
    else
        if ! [[ "$phy_index" =~ ^[0-9]+$ ]] || [ "$phy_index" -lt 1 ] || [ "$phy_index" -gt ${#phy_types[@]} ]; then
            echo -e "${RED}无效选择，使用默认PHY类型：${DEFAULT_PHY_TYPE}${NC}"
            current_phy_type="$DEFAULT_PHY_TYPE"
        else
            current_phy_type=${phy_types[$((phy_index-1))]}
        fi
    fi
    echo -e "已选择PHY类型：${current_phy_type}"
}

# 步骤2：列出并选择MDIO总线
select_bus() {
    echo -e "\n${GREEN}=== 系统MDIO总线列表 ===${NC}"
    echo "正在获取可用MDIO总线（需sudo权限）..."
    local mdio_buses=($(sudo mdio 2>/dev/null))
    if [ ${#mdio_buses[@]} -eq 0 ]; then
        echo -e "${RED}错误：未发现MDIO总线，请检查mdio工具和硬件连接${NC}"
        exit 1
    fi

    # 打印总线选项
    for ((i=0; i<${#mdio_buses[@]}; i++)); do
        echo "$((i+1))) ${mdio_buses[$i]}"
    done

    # 选择总线
    echo -n "请选择总线编号（输入编号）: "
    read -r bus_index
    if ! [[ "$bus_index" =~ ^[0-9]+$ ]] || [ "$bus_index" -lt 1 ] || [ "$bus_index" -gt ${#mdio_buses[@]} ]; then
        echo -e "${RED}无效选择，请输入有效的编号${NC}"
        exit 1
    fi
    current_bus=${mdio_buses[$((bus_index-1))]}
    echo -e "已选择MDIO总线：${current_bus}"
}

# 步骤3：PHY ID验证（仅首次选择总线时执行）
verify_phy_id() {
    local bus="$1"
    echo -e "\n${GREEN}=== PHY ID验证 ===${NC}"
    
    # 获取配置的预期ID
    local expected_default_id=$(get_config "phy_types.${current_phy_type}.expected_ids.default_id")
    local expected_msw=$(get_config "phy_types.${current_phy_type}.expected_ids.phy_id_msw")
    local expected_lsw=$(get_config "phy_types.${current_phy_type}.expected_ids.phy_id_lsw")
    
    # 验证默认ID（寄存器2）
    echo "正在读取PHY默认ID（预期${expected_default_id}）..."
    local default_reg=$(get_config "phy_types.${current_phy_type}.registers.PHY_DEFAULT_ID")
    local default_phy_id=$(sudo mdio "$bus" $default_reg 2>/dev/null || true)
    if [ "$default_phy_id" != "$expected_default_id" ]; then
        echo -e "${RED}错误：PHY默认ID为${default_phy_id}，预期${expected_default_id}${NC}"
        exit 1
    fi
    echo -e "默认ID验证通过：${GREEN}${expected_default_id}${NC}"

    # 验证真实PHY ID（高16位+低16位）
    echo "正在读取真实PHY ID..."
    local msw_reg=$(get_config "phy_types.${current_phy_type}.registers.PHY_ID_MSW")
    local lsw_reg=$(get_config "phy_types.${current_phy_type}.registers.PHY_ID_LSW")
    local phy_id_msw=$(sudo mdio "$bus" $msw_reg 2>/dev/null)
    local phy_id_lsw=$(sudo mdio "$bus" $lsw_reg 2>/dev/null)
    if [ "$phy_id_msw" != "$expected_msw" ] || [ "$phy_id_lsw" != "$expected_lsw" ]; then
        echo -e "${RED}真实PHY ID不匹配！${NC}"
        echo "实际：MSW=${phy_id_msw}, LSW=${phy_id_lsw}"
        echo "预期：MSW=${expected_msw}, LSW=${expected_lsw}"
        exit 1
    fi
    echo -e "真实PHY ID验证通过：${GREEN}${phy_id_msw} ${phy_id_lsw}${NC}"
}

# 步骤4：选择速率（按从小到大排序）
select_rate() {
    local bus="$1"
    while true; do
        echo -e "\n${GREEN}=== 选择速率 ===${NC}"
        # 从配置文件获取速率列表
        local rate_options=($(jq -r ".phy_types.${current_phy_type}.rates | keys[]" "$CONFIG_FILE" | sort -V))
        # 添加操作选项
        rate_options+=("上一步（重新选择总线）" "重新选择PHY类型" "退出脚本")
        
        for ((i=0; i<${#rate_options[@]}; i++)); do
            echo "$((i+1))) ${rate_options[$i]}"
        done

        # 选择速率
        echo -n "请选择速率编号: "
        read -r rate_index
        if ! [[ "$rate_index" =~ ^[0-9]+$ ]] || [ "$rate_index" -lt 1 ] || [ "$rate_index" -gt ${#rate_options[@]} ]; then
            echo -e "${RED}无效选择，请输入有效的编号${NC}"
            continue
        fi

        local rate_choice=${rate_options[$((rate_index-1))]}
        case "$rate_choice" in
            "上一步（重新选择总线）")
                reset_phy "$bus"  # 切换总线前复位PHY
                select_bus        # 重新选择总线
                verify_phy_id "$current_bus"  # 重新验证PHY ID
                break  # 跳出当前循环，重新进入速率选择
                ;;
            "重新选择PHY类型")
                reset_phy "$bus"
                select_phy_type
                verify_phy_id "$current_bus"
                break
                ;;
            "退出脚本")
                reset_phy "$bus"  # 退出前复位PHY
                echo -e "\n${GREEN}脚本已退出，PHY已复位${NC}"
                exit 0
                ;;
            *)
                echo -e "已选择速率：${rate_choice}"
                select_mode "$bus" "$rate_choice"  # 进入该速率的模式选择
                last_selected_mode=""  # 重置上一次模式记录
                break  # 模式选择完成后，返回速率选择界面
                ;;
        esac
    done
}

# 步骤5：选择模式
select_mode() {
    local bus="$1"
    local rate="$2"
    while true; do
        echo -e "\n${GREEN}=== 选择${rate}测试模式 ===${NC}"

        # 读取模式名称列表（键）
        mapfile -t mode_names < <(jq -r --arg rate_key "$rate" \
            '.phy_types.'"${current_phy_type}"'.rates[$rate_key].modes | keys[]' \
            "$CONFIG_FILE")

        # 添加操作选项
        mode_names+=("上一步（重新选择速率）" "退出脚本")

        # 打印模式选项
        for ((i=0; i<${#mode_names[@]}; i++)); do
            echo "$((i+1))) ${mode_names[$i]}"
        done

        # 选择模式
        echo -n "请选择模式编号: "
        read -r mode_index
        if ! [[ "$mode_index" =~ ^[0-9]+$ ]] || [ "$mode_index" -lt 1 ] || [ "$mode_index" -gt ${#mode_names[@]} ]; then
            echo -e "${RED}无效选择，请输入有效的编号${NC}"
            continue
        fi

        local selected_mode_name=${mode_names[$((mode_index-1))]}
        case "$selected_mode_name" in
            "上一步（重新选择速率）")
                reset_phy "$bus"  # 切换速率前复位PHY
                break  # 跳出当前模式循环，返回速率选择
                ;;
            "退出脚本")
                reset_phy "$bus"  # 退出前复位PHY
                echo -e "\n${GREEN}脚本已退出，PHY已复位${NC}"
                exit 0
                ;;
            *)
                # 每次切换模式都复位
                if [ -n "$last_selected_mode" ]; then
                    echo -e "\n${GREEN}=== 切换模式，执行PHY复位 ===${NC}"
                    reset_phy "$bus"
                fi
                # 获取模式对应的值
                local selected_mode_value=$(jq -r --arg rate_key "$rate" --arg mode_name "$selected_mode_name" \
                    '.phy_types.'"${current_phy_type}"'.rates[$rate_key].modes[$mode_name]' \
                    "$CONFIG_FILE")
                # 配置选中的测试模式
                configure_mode "$bus" "$rate" "$selected_mode_name" "$selected_mode_value"
                # 记录当前模式为上一次模式
                last_selected_mode="$selected_mode_name"
                echo -e "\n${GREEN}${rate}模式${selected_mode_name}配置完成！${NC}"
                echo -e "${GREEN}可继续选择其他模式（会自动复位），或选“上一步”/“退出”${NC}"
                ;;
        esac
    done
}

# 步骤6：配置选中的测试模式
configure_mode() {
    local bus="$1"
    local rate="$2"
    local mode_name="$3"
    local mode_value="$4"  # 直接使用配置文件中的值
    echo -e "\n${GREEN}=== 应用${rate}模式配置 ===${NC}"

    # 根据速率类型选择不同的配置逻辑
    case "$rate" in
        R_100M|R_1000M|R_100M_1000M)
            echo "配置${rate}测试模式：${mode_name}（值：${mode_value}）"
            
            # 从配置文件获取参数
            local reg_key=$(get_config "phy_types.${current_phy_type}.rates.${rate}.config.register")
            local register=$(get_config "phy_types.${current_phy_type}.registers.${reg_key}")
            local shift=$(get_config "phy_types.${current_phy_type}.rates.${rate}.config.shift")
            local mask=$(get_config "phy_types.${current_phy_type}.rates.${rate}.config.mask")
            local wait_reg=$(get_config "phy_types.${current_phy_type}.rates.${rate}.config.wait_register")
            local wait_val=$(get_config "phy_types.${current_phy_type}.rates.${rate}.config.wait_value")
            
            # 转换为十进制并计算移位后的值
            local mode_code=$((16#${mode_value:2}))  # 去除0x前缀并转十进制
            local shifted_code=$((mode_code << shift))
            echo "模式值左移${shift}位后：${shifted_code}，掩码：${mask}"
            sudo mdio "$bus" $register $shifted_code/$mask
            
            # 等待操作完成
            echo -e "\n${GREEN}等待${rate}测试模式操作完成...${NC}"
            while [ "$(sudo mdio "$bus" $wait_reg 2>/dev/null | awk '{print $1}')" = "$wait_val" ]; do
                sleep 0.5
            done
            echo -e "${GREEN}${rate}测试模式操作完成${NC}"
            ;;
            
        R_2G5|R_5G|R_10G)
            # --- 速率配置 ---
            local rate_code=$(get_config "phy_types.${current_phy_type}.rates.${rate}.rate_code")
            echo "配置速率${rate}：代码=${rate_code}"
            
            # 从配置文件获取速率参数
            local rate_reg_key=$(get_config "phy_types.${current_phy_type}.rates.${rate}.rate_config.register")
            local rate_register=$(get_config "phy_types.${current_phy_type}.registers.${rate_reg_key}")
            local rate_shift=$(get_config "phy_types.${current_phy_type}.rates.${rate}.rate_config.shift")
            local rate_mask=$(get_config "phy_types.${current_phy_type}.rates.${rate}.rate_config.mask")
            
            local shifted_rate_code=$((rate_code << rate_shift))
            echo "速率代码左移${rate_shift}位后：${shifted_rate_code}，掩码：${rate_mask}"
            sudo mdio "$bus" $rate_register $shifted_rate_code/$rate_mask
            
            # --- 模式配置 ---
            echo "配置Test Mode Control：${mode_name}（值：${mode_value}）"
            
            # 转换模式值为十进制
            local control_code=$((16#${mode_value:2}))  # 去除0x前缀并转十进制
            
            # 从配置文件获取模式参数
            local mode_reg_key=$(get_config "phy_types.${current_phy_type}.rates.${rate}.mode_config.register")
            local mode_register=$(get_config "phy_types.${current_phy_type}.registers.${mode_reg_key}")
            local mode_shift=$(get_config "phy_types.${current_phy_type}.rates.${rate}.mode_config.shift")
            local mode_mask=$(get_config "phy_types.${current_phy_type}.rates.${rate}.mode_config.mask")
            
            local shifted_control_code=$((control_code << mode_shift))
            local freq_code_shifted=0
            
            # 模式4（Transmitter distortion test）需配置频率
            if [ "$control_code" -eq 4 ]; then
                echo -e "\n${GREEN}=== 选择Transmitter Test Frequencies ===${NC}"
                # 读取频率模式名称列表
                mapfile -t freq_names < <(jq -r --arg rate_key "$rate" \
                    '.phy_types.'"${current_phy_type}"'.rates[$rate_key].frequency_config.modes | keys[]' \
                    "$CONFIG_FILE")
                
                for ((i=0; i<${#freq_names[@]}; i++)); do
                    echo "$((i+1))) ${freq_names[$i]}"
                done
                echo -n "请选择频率编号: "
                read -r freq_index
                if ! [[ "$freq_index" =~ ^[0-9]+$ ]] || [ "$freq_index" -lt 1 ] || [ "$freq_index" -gt ${#freq_names[@]} ]; then
                    echo -e "${RED}无效选择，默认不配置频率${NC}"
                    continue
                fi
                local selected_freq_name=${freq_names[$((freq_index-1))]}
                # 获取频率值
                local freq_value=$(jq -r --arg rate_key "$rate" --arg freq_name "$selected_freq_name" \
                    '.phy_types.'"${current_phy_type}"'.rates[$rate_key].frequency_config.modes[$freq_name]' \
                    "$CONFIG_FILE")
                local freq_code=$((16#${freq_value:2}))  # 转换为十进制
                # 从配置文件获取频率移位值
                local freq_shift=$(get_config "phy_types.${current_phy_type}.rates.${rate}.frequency_config.shift")
                freq_code_shifted=$((freq_code << freq_shift))
                echo "已选择频率：${selected_freq_name}（值：${freq_value}，左移${freq_shift}位后：${freq_code_shifted}）"
            fi
            
            # 计算总代码并写入寄存器
            local total_code=$((shifted_control_code | freq_code_shifted))
            echo "写入${mode_register}寄存器：总代码=${total_code}，掩码=${mode_mask}"
            sudo mdio "$bus" $mode_register $total_code/$mode_mask
            
            # 模式6（Droop test）等待处理器完成
            if [ "$control_code" -eq 6 ]; then
                local wait_reg=$(get_config "phy_types.${current_phy_type}.rates.${rate}.wait_config.mode_6.register")
                local wait_val=$(get_config "phy_types.${current_phy_type}.rates.${rate}.wait_config.mode_6.value")
                echo -e "\n${GREEN}等待Droop test操作完成...${NC}"
                while [ "$(sudo mdio "$bus" $wait_reg 2>/dev/null | awk '{print $1}')" = "$wait_val" ]; do
                    sleep 0.5
                done
                echo -e "${GREEN}Droop test操作完成${NC}"
            fi
            ;;
    esac
}

# 主流程
main() {
    echo -e "${GREEN}=== PHY测试模式配置脚本（每次切换模式自动复位） ===${NC}"
    select_phy_type          # 选择PHY类型
    select_bus               # 选择总线
    verify_phy_id "$current_bus"  # 验证PHY ID
    while true; do
        select_rate "$current_bus"  # 选择速率（循环）
    done
}

# 启动脚本
main