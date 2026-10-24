# data_processor.py - 数据处理函数
import pandas as pd
import os
from datetime import datetime
import serial_utils

# 响应数据存储列表
com7_md_response_data = []  # COM7的MD命令响应数据
com3_response_data = []  # COM3的响应数据


def is_md_command(command):
    """
    判断是否为md开头的命令
    """
    return command.strip().lower().startswith('md')


def parse_md_address(command):
    """
    解析md命令，提取地址参数
    """
    if not command or not is_md_command(command):
        return ""

    parts = command.strip().split()
    if len(parts) >= 2:
        return parts[1]
    return ""


def extract_bitfield(reg_value, start_bit, length):
    """
    从32位寄存器值中提取指定位域
    """
    if length == 0 or length > 32:
        return 0
    mask = (1 << length) - 1
    return (reg_value >> start_bit) & mask


def extract_data_safe(reg_value_str):
    """
    安全提取数据位（处理字节跨越问题）
    特别针对 data_start=11, data_len=9 的情况优化
    """
    if not reg_value_str or not isinstance(reg_value_str, str):
        return None

    reg_value_str = reg_value_str.strip().lower()

    if len(reg_value_str) != 8:
        return None

    try:
        reg_value = int(reg_value_str, 16)

        # 提取相关字节
        byte1 = (reg_value >> 8) & 0xFF  # 第2字节
        byte2 = (reg_value >> 16) & 0xFF  # 第3字节

        # bit11-15 在 byte1 的高5位 (bit3-7)
        # bit16-19 在 byte2 的低4位 (bit0-3)
        data_low = (byte1 >> 3) & 0x1F  # 5 bits
        data_high = (byte2 & 0x0F) << 5  # 左移5位

        return data_high | data_low
    except (ValueError, TypeError):
        return None


# 电压读取数据存储
voltage_readings = []


def add_voltage_reading(timestamp, lane_name, batch_name, command_index,
                        dmm_index, dmm_address, voltage):
    """添加电压读数到全局存储"""
    voltage_readings.append({
        'timestamp': timestamp,
        'lane': lane_name,
        'batch': batch_name,
        'command_index': command_index,
        'dmm_index': dmm_index,
        'dmm_address': dmm_address,
        'voltage': voltage
    })


def save_responses_to_excel_with_voltage(excel_filename):
    """
    保存多通道响应数据到Excel文件 - 宽表格式
    每个通道一行，所有参数作为列
    包含 COM3 数据（dump_ssm_cal_result, dump_rx_dll_Deskew_v2）
    """
    # 按通道组织MD数据
    lane_md_data = {
        'lane0': {},
        'lane1': {},
        'lane2': {},
        'lane3': {}
    }

    # 按通道组织电压数据 - 11个电压点全部保存
    lane_voltage_data = {
        'lane0': {},
        'lane1': {},
        'lane2': {},
        'lane3': {}
    }

    # 按通道组织COM3数据
    lane_com3_data = {
        'lane0': {},
        'lane1': {},
        'lane2': {},
        'lane3': {}
    }

    # ========== 1. 处理COM7的MD命令数据 ==========
    md_param_names = [
        "dll_comp_dcc_dac_code（inpcal）",
        "dll_comp_dcc_dac_code（inmcal）",
        "dll_comp_dcc_dac_code（dcccal 0）",
        "dll_comp_dcc_dac_code（dcccal 90）",
        "dll_comp_dcc_dac_code（dcccal 180）",
        "dll_comp_dcc_dac_code（dcccal 270）"
    ]

    for lane in lane_md_data:
        for param in md_param_names:
            lane_md_data[lane][param] = None

    for record in com7_md_response_data:
        timestamp, cmd, address, value, batch, has_response, retry_count = record
        if "初始化阶段" in batch and "[" not in batch:
            continue
        if value and has_response == "是":
            lane_name = "lane0"
            if "[" in batch and "]" in batch:
                lane_info = batch.split("[")[1].split("]")[0]
                if lane_info.startswith("lane"):
                    lane_name = lane_info

            lane_md_count = sum(1 for v in lane_md_data[lane_name].values() if v is not None) + 1
            if lane_md_count == 1:
                param_name = "dll_comp_dcc_dac_code（inpcal）"
            elif lane_md_count == 2:
                param_name = "dll_comp_dcc_dac_code（inmcal）"
            elif lane_md_count == 3:
                param_name = "dll_comp_dcc_dac_code（dcccal 0）"
            elif lane_md_count == 4:
                param_name = "dll_comp_dcc_dac_code（dcccal 90）"
            elif lane_md_count == 5:
                param_name = "dll_comp_dcc_dac_code（dcccal 180）"
            elif lane_md_count == 6:
                param_name = "dll_comp_dcc_dac_code（dcccal 270）"
            else:
                continue

            converted_value = ""
            if value and len(value) == 8:
                converted_value = extract_data_safe(value)

            lane_md_data[lane_name][param_name] = converted_value

    # ========== 2. 处理电压数据 - 11个电压点全部保存 ==========
    voltage_column_mapping = {
        0: 'vbg',
        1: 'tx_vreg1_vp_s',
        2: 'tx_vreg0_vp',
        3: 'tx_dll_vreg',
        4: 'inp',
        5: 'inm',
        6: 'vdac_r2r_vref',
        7: 'txm_cal_filt_out(dcc0)',
        8: 'txm_cal_filt_out(dcc90)',
        9: 'txm_cal_filt_out(dcc180)',
        10: 'txm_cal_filt_out(dcc270)',
    }

    for reading in voltage_readings:
        lane_name = reading.get('lane', 'unknown')
        voltage = reading.get('voltage', 0)

        current_count = len(lane_voltage_data[lane_name])
        if current_count >= 11:
            continue

        column_name = voltage_column_mapping.get(current_count)
        if column_name:
            lane_voltage_data[lane_name][column_name] = voltage

    # ========== 3. 处理COM3的响应数据 ==========
    for record in com3_response_data:
        timestamp, cmd, response, batch, has_response = record
        if response and has_response in ["执行成功", "是"]:
            cleaned_response = response.strip()
            if cleaned_response:
                lane_name = "lane0"
                if "[" in batch and "]" in batch:
                    lane_info = batch.split("[")[1].split("]")[0]
                    if lane_info.startswith("lane"):
                        lane_name = lane_info

                # 完整保存COM3数据，不截断
                if "dump_ssm_cal_result" in cmd:
                    lane_com3_data[lane_name]['dump_ssm_cal_result'] = cleaned_response
                elif "dump_rx_dll_Deskew_v2" in cmd:
                    lane_com3_data[lane_name]['dump_rx_dll_Deskew_v2'] = cleaned_response
                else:
                    lane_com3_data[lane_name][cmd.strip()] = cleaned_response

    # ========== 4. 构建宽表数据 ==========
    all_records = []

    for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
        lane_num = int(lane_name.replace('lane', ''))

        md_data = lane_md_data.get(lane_name, {})
        voltage_data = lane_voltage_data.get(lane_name, {})
        com3_data = lane_com3_data.get(lane_name, {})  # 获取COM3数据

        # 调试输出
        print(f"[DEBUG] {lane_name} COM3数据: {list(com3_data.keys())}")

        record = {
            'group': 0,
            'macro': 0,
            'lane': lane_num,
            'vbg': voltage_data.get('vbg', 0),
            'tx_vreg1_vp_s': voltage_data.get('tx_vreg1_vp_s', 0),
            'tx_vreg0_vp': voltage_data.get('tx_vreg0_vp', 0),
            'dll_comp_dcc_dac_code (dccinpcal)': md_data.get('dll_comp_dcc_dac_code（inpcal）', 0),
            'dll_comp_dcc_dac_code (dccinmcal)': md_data.get('dll_comp_dcc_dac_code（inmcal）', 0),
            'tx_dll_vreg': voltage_data.get('tx_dll_vreg', 0),
            'inp': voltage_data.get('inp', 0),
            'inm': voltage_data.get('inm', 0),
            'dll_comp_dcc_dac_code（dcccal 0）': md_data.get('dll_comp_dcc_dac_code（dcccal 0）', 0),
            'dll_comp_dcc_dac_code（dcccal 90）': md_data.get('dll_comp_dcc_dac_code（dcccal 90）', 0),
            'dll_comp_dcc_dac_code（dcccal 180）': md_data.get('dll_comp_dcc_dac_code（dcccal 180）', 0),
            'dll_comp_dcc_dac_code（dcccal 270）': md_data.get('dll_comp_dcc_dac_code（dcccal 270）', 0),
            'vdac_r2r_vref': voltage_data.get('vdac_r2r_vref', 0),
            'txm_cal_filt_out(dcc0)': voltage_data.get('txm_cal_filt_out(dcc0)', 0),
            'txm_cal_filt_out(dcc90)': voltage_data.get('txm_cal_filt_out(dcc90)', 0),
            'txm_cal_filt_out(dcc180)': voltage_data.get('txm_cal_filt_out(dcc180)', 0),
            'txm_cal_filt_out(dcc270)': voltage_data.get('txm_cal_filt_out(dcc270)', 0),
            # === COM3 数据（关键修复：正确从 com3_data 获取）===
            'dump_ssm_cal_result': com3_data.get('dump_ssm_cal_result', ''),
            'dump_rx_dll_Deskew_v2': com3_data.get('dump_rx_dll_Deskew_v2', ''),
        }

        all_records.append(record)

    if not all_records:
        print("没有有效的响应数据需要保存")
        return

    try:
        df = pd.DataFrame(all_records)

        column_order = [
            'group', 'macro', 'lane',
            'vbg', 'tx_vreg1_vp_s', 'tx_vreg0_vp',
            'dll_comp_dcc_dac_code (dccinpcal)',
            'dll_comp_dcc_dac_code (dccinmcal)',
            'tx_dll_vreg', 'inp', 'inm',
            'dll_comp_dcc_dac_code（dcccal 0）',
            'dll_comp_dcc_dac_code（dcccal 90）',
            'dll_comp_dcc_dac_code（dcccal 180）',
            'dll_comp_dcc_dac_code（dcccal 270）',
            'vdac_r2r_vref',
            'txm_cal_filt_out(dcc0)',
            'txm_cal_filt_out(dcc90)',
            'txm_cal_filt_out(dcc180)',
            'txm_cal_filt_out(dcc270)',
            'dump_ssm_cal_result',
            'dump_rx_dll_Deskew_v2',
        ]
        df = df[column_order]

        df.to_excel(excel_filename, index=False, engine='openpyxl')

        print(f"整合数据已保存到: {os.path.abspath(excel_filename)}")
        print(f"共保存 {len(all_records)} 条记录（每个通道一行）")

        # 打印统计信息
        for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
            v_data = lane_voltage_data.get(lane_name, {})
            c_data = lane_com3_data.get(lane_name, {})
            print(f"  {lane_name}: 电压数据 {len(v_data)} 个, COM3数据 {len(c_data)} 个")

    except Exception as e:
        print(f"保存Excel文件时出错: {e}")
        import traceback
        traceback.print_exc()
        try:
            csv_filename = excel_filename.replace('.xlsx', '.csv')
            df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
            print(f"数据已保存为CSV文件: {csv_filename}")
        except Exception as e2:
            print(f"保存CSV文件也失败: {e2}")


def save_responses_to_excel_with_lanes(excel_filename):
    """保存多通道响应数据到Excel文件（兼容旧版本）"""
    save_responses_to_excel_with_voltage(excel_filename)