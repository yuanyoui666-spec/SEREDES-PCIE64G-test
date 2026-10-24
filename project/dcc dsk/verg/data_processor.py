# data_processor.py - 数据处理函数
import pandas as pd
import os
from datetime import datetime
import config
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


def save_responses_to_excel_with_lanes(excel_filename):
    """
    保存多通道响应数据到Excel文件
    支持lane0-lane3四个通道的数据分类保存
    """
    all_response_data = []

    # 按通道组织数据
    lane_data = {
        'lane0': {'md': [], 'com3': []},
        'lane1': {'md': [], 'com3': []},
        'lane2': {'md': [], 'com3': []},
        'lane3': {'md': [], 'com3': []}
    }

    # 处理COM7的MD命令数据
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
            else:
                total_records = len(com7_md_response_data)
                if total_records > 0:
                    record_index = com7_md_response_data.index(record)
                    lane_index = record_index // 6
                    if lane_index < 4:
                        lane_name = f"lane{lane_index}"

            lane_md_count = len(lane_data[lane_name]['md']) + 1

            if lane_md_count == 1:
                param_name = f"dll_comp_dcc_dac_code（inpcal）"
            elif lane_md_count == 2:
                param_name = f"dll_comp_dcc_dac_code（inmcal）"
            elif lane_md_count == 3:
                param_name = f"dll_comp_dcc_dac_code（dcccal 0）"
            elif lane_md_count == 4:
                param_name = f"dll_comp_dcc_dac_code（dcccal 90）"
            elif lane_md_count == 5:
                param_name = f"dll_comp_dcc_dac_code（dcccal 180）"
            elif lane_md_count == 6:
                param_name = f"dll_comp_dcc_dac_code（dcccal 270）"
            else:
                param_name = f"dll_comp_dcc_dac_code（未知）"

            converted_value = ""
            if value and len(value) == 8:
                converted_value = extract_data_safe(value)
                if converted_value is not None:
                    print(f"转换值: {value} -> {converted_value}")

            lane_data[lane_name]['md'].append([
                lane_name,
                param_name,
                value,
                converted_value,
                f"MD读取"
            ])

    # 处理COM3的响应数据
    for record in com3_response_data:
        timestamp, cmd, response, batch, has_response = record

        if response and has_response in ["执行成功", "是"]:
            cleaned_response = serial_utils.clean_special_chars(response)

            if cleaned_response:
                lane_name = "lane0"

                if "[" in batch and "]" in batch:
                    lane_info = batch.split("[")[1].split("]")[0]
                    if lane_info.startswith("lane"):
                        lane_name = lane_info
                else:
                    total_records = len(com3_response_data)
                    if total_records > 0:
                        record_index = com3_response_data.index(record)
                        lane_index = record_index // 2
                        if lane_index < 4:
                            lane_name = f"lane{lane_index}"

                if "dump_ssm_cal_result" in cmd:
                    param_name = f"dump_ssm_cal_result"
                elif "dump_rx_dll_Deskew_v2" in cmd:
                    param_name = f"dump_rx_dll_Deskew_v2"
                else:
                    param_name = f"{cmd}"

                lane_data[lane_name]['com3'].append([
                    lane_name,
                    param_name,
                    cleaned_response[:3500] + ("..." if len(cleaned_response) > 3500 else ""),
                    "",
                    f"COM3执行"
                ])

    # 将所有通道的数据按顺序合并
    for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
        for md_record in lane_data[lane_name]['md']:
            channel, param_name, value, converted_value, data_type = md_record
            all_response_data.append([
                channel,
                param_name,
                value,
                converted_value,
                data_type
            ])

        for com3_record in lane_data[lane_name]['com3']:
            channel, param_name, response, converted_value, data_type = com3_record
            all_response_data.append([
                channel,
                param_name,
                response,
                converted_value,
                data_type
            ])

    if not all_response_data:
        print("没有有效的响应数据需要保存")
        return

    try:
        df = pd.DataFrame(all_response_data, columns=[
            '通道',
            '参数',
            '读取值/响应结果',
            '转换后的值',
            '数据类型'
        ])

        df.to_excel(excel_filename, index=False, engine='openpyxl')

        print(f"多通道响应数据已保存到: {os.path.abspath(excel_filename)}")
        print(f"共保存 {len(all_response_data)} 条记录")

    except Exception as e:
        print(f"保存Excel文件时出错: {e}")
        try:
            csv_filename = excel_filename.replace('.xlsx', '.csv')
            df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
            print(f"数据已保存为CSV文件: {csv_filename}")
        except Exception as e2:
            print(f"保存CSV文件也失败: {e2}")

##新增代码  0602 电压读取##

# data_processor.py - 新增电压数据处理功能
def save_voltage_readings_to_excel(voltage_readings, excel_filename):
    """
    保存电压读数到Excel文件
    """
    if not voltage_readings:
        print("没有电压读数需要保存")
        return

    try:
        # 转换数据格式
        voltage_data = []
        for reading in voltage_readings:
            voltage_data.append([
                reading.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                reading.get('lane', 'unknown'),
                reading.get('batch', 'unknown'),
                reading.get('command_index', 0),
                reading.get('dmm_index', 0),
                reading.get('dmm_address', 'unknown'),
                f"{reading.get('voltage', 0):.6f} V"
            ])

        # 创建DataFrame
        df_voltage = pd.DataFrame(voltage_data, columns=[
            '时间戳',
            '测试通道',
            '批次名称',
            '命令序号',
            '万用表编号',
            '万用表地址',
            '电压值'
        ])

        # 保存到单独的Excel文件
        voltage_filename = excel_filename.replace('.xlsx', '_voltage.xlsx')
        df_voltage.to_excel(voltage_filename, index=False, engine='openpyxl')

        print(f"电压数据已保存到: {os.path.abspath(voltage_filename)}")
        print(f"共保存 {len(voltage_readings)} 条电压记录")

    except Exception as e:
        print(f"保存电压数据时出错: {e}")


def save_all_data_to_excel(excel_filename, voltage_readings):
    """
    保存所有数据到Excel文件
    """
    # 保存原有的响应数据
    save_responses_to_excel_with_lanes(excel_filename)

    # 保存电压数据
    save_voltage_readings_to_excel(voltage_readings, excel_filename)

##新增代码  0602 电压读取##