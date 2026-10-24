#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
extract_dcc_final.py - 完整独立的 DCC DSK 值提取测试
功能：
1. 初始化（phy_init_only, m3_run, phy_macro_reset, ...）
2. 发送固定 4 个 mm 配置（仅一次）
3. 对每个通道：启用通道，顺序读取 11 个电压点（通过 ATB + 万用表）
4. 对每个通道：通过 COM3 发送 dump_ssm_cal_result 和 dump_rx_dll_Deskew_v2
5. 从 dump_ssm_cal_result 中提取 type=6,7 以及 type=52~55 的值
6. 从 dump_rx_dll_Deskew_v2 中提取 8 个 FineSkewCode
7. 保存结果至 Excel，支持元数据和三种保存模式（新文件/追加/覆盖）
8. 每条命令打印时间戳和响应预览，方便调试
"""

import os
import time
import threading
import re
import pandas as pd
from datetime import datetime

# 导入项目已有模块
import serial_utils
import main_controller
import data_processor
from config import (
    LANE_CONFIGS,
    SERIAL_PORT_COM7 as CFG_COM7,
    SERIAL_PORT_COM3 as CFG_COM3,
    BAUD_RATE as CFG_BAUD,
)

# ========== 全局数据存储（本脚本独立使用） ==========
voltage_readings = []          # 存储所有电压读数
com3_response_data = []        # 存储 COM3 响应（含原始文本）
com7_debug_log = []            # 可选，保留调试日志

# ========== 解析函数 ==========
def parse_ssm_value(text, type_id):
    """从 dump_ssm_cal_result 中提取指定 type 的 res 值"""
    pattern = rf'type:{type_id}\s+valid:\d+\s+res:(\d+)\s+name:'
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None

def parse_fineskew_codes(text):
    """从 dump_rx_dll_Deskew_v2 中提取 8 个 FineSkewCode"""
    codes = [None] * 8
    for i in range(8):
        pattern = rf'FineSkewCode{i}:(\d+)'
        match = re.search(pattern, text)
        if match:
            codes[i] = int(match.group(1))
    return codes

def parse_ecal_values(text):
    """从 dump_ssm_cal_result 中提取 type 52~55 的 res，返回 dict"""
    result = {}
    for t in [52, 53, 54, 55]:
        val = parse_ssm_value(text, t)
        if val is not None:
            result[f'eCal_TxDrvDcc{t-52}'] = val
    return result


def parse_tx_drv1ui_fineskew(text):
    """
    从 dump_tx_drv1ui_cal_res 的响应中提取有效的 fine_skew_code0~3。
    匹配第一个 gGlobalStartUpCalResults 中 valid=1 的 group，
    然后提取该 group 的四个 fine_skew_code。
    """
    # 匹配任意 lane 索引的 valid=1 行
    pattern = r'gGlobalStartUpCalResults\.mTxDrv1UiCalResults\[\d+\]\.mCalStoreValidity\[eCalGroup1_Gen1to2\] = 1'
    match = re.search(pattern, text)
    if not match:
        return (None, None, None, None)

    start = match.end()
    codes = []
    for i in range(4):
        sub_pattern = rf'fine_skew_code{i}:0x([0-9a-fA-F]+)'
        sub_match = re.search(sub_pattern, text[start:])
        if sub_match:
            codes.append(int(sub_match.group(1), 16))
        else:
            codes.append(None)
    return tuple(codes)


# ========== 元数据输入 ==========
def get_metadata():
    print("\n" + "=" * 60)
    print("请输入本次测试的全局信息（将添加到每条数据中）：")
    print("=" * 60)
    chip = input("  芯片编号 (如 TT-01): ").strip() or "Unknown"
    temp = input("  温度电压 (如 NTNV): ").strip() or "NTNV"
    fw = input("  FW版本 (如 72fae): ").strip() or "Unknown"
    gui = input("  GUI版本 (如 2.4.9): ").strip() or "Unknown"
    board = input("  单板编号 (如 SIB-02): ").strip() or "Unknown"
    print("=" * 60)
    return {
        'chip_id': chip,
        'temp_voltage': temp,
        'fw_version': fw,
        'gui_version': gui,
        'board_id': board
    }

# ========== 改进的串口发送函数（直接读取硬件缓冲区） ==========
def send_cmd(ser, command, delay=0.2, timeout=2.5, show_tx=True, show_rx=True):
    """
    发送单条命令，直接读取硬件缓冲区获取响应，不依赖后台线程。
    返回 (响应文本, 是否成功)
    """
    if not command or command.isspace():
        return "", False

    # 确保命令以换行结尾
    if not command.endswith('\n'):
        cmd_to_send = command + '\n'
    else:
        cmd_to_send = command

    # 清空硬件缓冲区（发送前清空输入缓冲区，避免残留数据干扰）
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    send_time = datetime.now()
    if show_tx:
        print(f"[{send_time.strftime('%H:%M:%S.%f')[:-3]}] 发送: {command}")

    try:
        ser.write(cmd_to_send.encode('utf-8'))
        ser.flush()
    except Exception as e:
        print(f"  发送异常: {e}")
        return "", False

    # 等待命令执行
    time.sleep(delay)

    # 读取响应
    response_buffer = ""
    start_time = time.time()
    last_data_time = time.time()
    no_data_count = 0
    max_no_data = int(timeout / 0.05) + 1

    while time.time() - start_time < timeout:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            try:
                decoded = data.decode('utf-8', errors='ignore')
                response_buffer += decoded
                last_data_time = time.time()
                no_data_count = 0
            except:
                pass

        # 如果已有数据且超过 0.5 秒无新数据，认为接收完成
        if response_buffer and time.time() - last_data_time > 0.5:
            break

        # 无数据超时保护
        no_data_count += 1
        if no_data_count > max_no_data:
            break
        time.sleep(0.05)

    response_text = response_buffer.strip()
    if show_rx:
        if response_text:
            preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 响应 ({len(response_text)} 字节): {preview}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 无响应")

    return response_text, bool(response_text)

# ========== 批次发送（处理电压标记） ==========
def send_batch_with_voltage(ser, commands, batch_name, current_lane,
                            dmm_addresses, cmd_delay=0.2, timeout=2.5):
    """
    逐条发送命令，遇到 READ_VOLTAGE_34470A 则读取万用表电压。
    每条命令都显示发送和响应。
    """
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 批次: {batch_name}")
    valid_cmds = [c for c in commands if c.strip()]
    print(f"有效命令数: {len(valid_cmds)}")
    print(f"{'='*60}")

    voltage_count = 0
    for i, cmd in enumerate(commands, 1):
        stripped = cmd.strip()
        if not stripped:
            time.sleep(cmd_delay)
            continue

        # 检查是否为电压读取标记
        if stripped.upper() == "READ_VOLTAGE_34470A":
            voltage_count += 1
            print(f"\n[电压读取点 {voltage_count}]")
            for dmm_idx, dmm_addr in enumerate(dmm_addresses):
                voltage = main_controller.read_34470a_voltage(
                    dmm_addr, dmm_idx, max_retries=3, retry_delay=0.5
                )
                if voltage is not None:
                    # 记录电压读数
                    voltage_readings.append({
                        'timestamp': datetime.now(),
                        'lane': current_lane,
                        'batch': batch_name,
                        'command_index': i,
                        'dmm_index': dmm_idx,
                        'dmm_address': dmm_addr,
                        'voltage': voltage
                    })
                    print(f"  万用表 {dmm_idx+1} 电压: {voltage:.6f} V ✓")
                else:
                    print(f"  万用表 {dmm_idx+1} 读取失败 ✗")
            time.sleep(1.0)   # 电压读取后稍作停顿
            continue

        # 普通命令发送
        send_cmd(ser, stripped, delay=cmd_delay, timeout=timeout,
                 show_tx=True, show_rx=True)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 批次完成，共 {voltage_count} 个电压点")

# ========== 保存结果到 Excel ==========
def save_results_to_excel(excel_filename, metadata=None, mode='new'):
    """
    将 voltage_readings 和 com3_response_data 整合成宽表，
    添加元数据，并按模式保存。
    """
    lane_voltage_data = {f'lane{i}': {} for i in range(4)}
    voltage_column_mapping = {
        0: 'vbg', 1: 'tx_vreg1_vp_s', 2: 'tx_vreg0_vp',
        3: 'tx_dll_vreg', 4: 'inp', 5: 'inm', 6: 'vdac_r2r_vref',
        7: 'txm_cal_filt_out(dcc0)', 8: 'txm_cal_filt_out(dcc90)',
        9: 'txm_cal_filt_out(dcc180)', 10: 'txm_cal_filt_out(dcc270)'
    }
    for reading in voltage_readings:
        lane_name = reading.get('lane', 'unknown')
        voltage = reading.get('voltage', 0)
        current_count = len(lane_voltage_data[lane_name])
        if current_count >= 11:
            continue
        col = voltage_column_mapping.get(current_count)
        if col:
            lane_voltage_data[lane_name][col] = voltage

    lane_com3_data = {f'lane{i}': {} for i in range(4)}
    for record in com3_response_data:
        timestamp, cmd, response, batch, has_response = record
        if not (response and has_response in ["执行成功", "是"]):
            continue
        cleaned = response.strip()
        if not cleaned:
            continue
        lane_name = "lane0"
        if "[" in batch and "]" in batch:
            lane_info = batch.split("[")[1].split("]")[0]
            if lane_info.startswith("Lane"):
                lane_num = int(lane_info.replace("Lane", ""))
                lane_name = f"lane{lane_num}"

        if "dump_ssm_cal_result" in cmd:
            lane_com3_data[lane_name]['dump_ssm_cal_result'] = cleaned
            inp = parse_ssm_value(cleaned, 6)
            inm = parse_ssm_value(cleaned, 7)
            if inp is not None:
                lane_com3_data[lane_name]['RxDll0DccInp'] = inp
            if inm is not None:
                lane_com3_data[lane_name]['RxDll0DccInm'] = inm
            ecal = parse_ecal_values(cleaned)
            for key, val in ecal.items():
                lane_com3_data[lane_name][key] = val

        elif "dump_rx_dll_Deskew_v2" in cmd:
            lane_com3_data[lane_name]['dump_rx_dll_Deskew_v2'] = cleaned
            codes = parse_fineskew_codes(cleaned)
            for idx, code in enumerate(codes):
                if code is not None:
                    lane_com3_data[lane_name][f'FineSkew_{idx}'] = code

        elif "dump_tx_drv1ui_cal_res" in cmd:   # 新增
            lane_com3_data[lane_name]['dump_tx_drv1ui_cal_res'] = cleaned
            codes = parse_tx_drv1ui_fineskew(cleaned)
            if codes[0] is not None:
                lane_com3_data[lane_name]['TxDrv1Ui_FineSkew_0'] = codes[0]
                lane_com3_data[lane_name]['TxDrv1Ui_FineSkew_1'] = codes[1]
                lane_com3_data[lane_name]['TxDrv1Ui_FineSkew_2'] = codes[2]
                lane_com3_data[lane_name]['TxDrv1Ui_FineSkew_3'] = codes[3]

    all_records = []
    for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
        lane_num = int(lane_name.replace('lane', ''))
        volt = lane_voltage_data.get(lane_name, {})
        com3 = lane_com3_data.get(lane_name, {})

        record = {
            'group': 0,
            'macro': 0,
            'lane': lane_num,
            'vbg': volt.get('vbg', 0),
            'tx_vreg1_vp_s': volt.get('tx_vreg1_vp_s', 0),
            'tx_vreg0_vp': volt.get('tx_vreg0_vp', 0),
            'tx_dll_vreg': volt.get('tx_dll_vreg', 0),
            'inp': volt.get('inp', 0),
            'inm': volt.get('inm', 0),
            'vdac_r2r_vref': volt.get('vdac_r2r_vref', 0),
            'txm_cal_filt_out(dcc0)': volt.get('txm_cal_filt_out(dcc0)', 0),
            'txm_cal_filt_out(dcc90)': volt.get('txm_cal_filt_out(dcc90)', 0),
            'txm_cal_filt_out(dcc180)': volt.get('txm_cal_filt_out(dcc180)', 0),
            'txm_cal_filt_out(dcc270)': volt.get('txm_cal_filt_out(dcc270)', 0),
            'RxDll0DccInp': com3.get('RxDll0DccInp', None),
            'RxDll0DccInm': com3.get('RxDll0DccInm', None),
            'FineSkew_0': com3.get('FineSkew_0', None),
            'FineSkew_1': com3.get('FineSkew_1', None),
            'FineSkew_2': com3.get('FineSkew_2', None),
            'FineSkew_3': com3.get('FineSkew_3', None),
            'FineSkew_4': com3.get('FineSkew_4', None),
            'FineSkew_5': com3.get('FineSkew_5', None),
            'FineSkew_6': com3.get('FineSkew_6', None),
            'FineSkew_7': com3.get('FineSkew_7', None),
            # 新增 4 列
            'TxDrv1Ui_FineSkew_0': com3.get('TxDrv1Ui_FineSkew_0', None),
            'TxDrv1Ui_FineSkew_1': com3.get('TxDrv1Ui_FineSkew_1', None),
            'TxDrv1Ui_FineSkew_2': com3.get('TxDrv1Ui_FineSkew_2', None),
            'TxDrv1Ui_FineSkew_3': com3.get('TxDrv1Ui_FineSkew_3', None),
            'eCal_TxDrvDcc0': com3.get('eCal_TxDrvDcc0', None),
            'eCal_TxDrvDcc1': com3.get('eCal_TxDrvDcc1', None),
            'eCal_TxDrvDcc2': com3.get('eCal_TxDrvDcc2', None),
            'eCal_TxDrvDcc3': com3.get('eCal_TxDrvDcc3', None),
            'dump_ssm_cal_result': com3.get('dump_ssm_cal_result', ''),
            'dump_rx_dll_Deskew_v2': com3.get('dump_rx_dll_Deskew_v2', ''),
            'dump_tx_drv1ui_cal_res': com3.get('dump_tx_drv1ui_cal_res', ''),  # 可选保留原始响应
        }
        all_records.append(record)

    if not all_records:
        print("没有数据可保存")
        return

    # 合并元数据
    if metadata:
        for record in all_records:
            for key, value in metadata.items():
                record[key] = value

    df = pd.DataFrame(all_records)

    # 重命名元数据列为中文
    rename_map = {
        'chip_id': '芯片编号',
        'temp_voltage': '温度电压',
        'fw_version': 'FW版本',
        'gui_version': 'gui版本',
        'board_id': '单板编号'
    }
    if metadata:
        for old, new in rename_map.items():
            if old in df.columns:
                df.rename(columns={old: new}, inplace=True)
        # 元数据列置前
        meta_cols = ['芯片编号', '温度电压', 'FW版本', 'gui版本', '单板编号']
        meta_present = [c for c in meta_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in meta_present]
        df = df[meta_present + other_cols]
    else:
        # 默认列顺序
        base_cols = ['group', 'macro', 'lane', 'vbg', 'tx_vreg1_vp_s', 'tx_vreg0_vp',
                     'tx_dll_vreg', 'inp', 'inm', 'vdac_r2r_vref',
                     'txm_cal_filt_out(dcc0)', 'txm_cal_filt_out(dcc90)',
                     'txm_cal_filt_out(dcc180)', 'txm_cal_filt_out(dcc270)']
        com3_cols = ['RxDll0DccInp', 'RxDll0DccInm',
                     'FineSkew_0', 'FineSkew_1', 'FineSkew_2', 'FineSkew_3',
                     'FineSkew_4', 'FineSkew_5', 'FineSkew_6', 'FineSkew_7',
                     'TxDrv1Ui_FineSkew_0', 'TxDrv1Ui_FineSkew_1', 'TxDrv1Ui_FineSkew_2', 'TxDrv1Ui_FineSkew_3',
                     'eCal_TxDrvDcc0', 'eCal_TxDrvDcc1', 'eCal_TxDrvDcc2', 'eCal_TxDrvDcc3',
                     'dump_ssm_cal_result', 'dump_rx_dll_Deskew_v2', 'dump_tx_drv1ui_cal_res']
        order = base_cols + com3_cols
        order = [c for c in order if c in df.columns]
        df = df[order]

    os.makedirs(os.path.dirname(excel_filename) or '.', exist_ok=True)

    # ----- 保存 -----
    if mode == 'new':
        base, ext = os.path.splitext(excel_filename)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{base}_{ts}{ext}"
        df.to_excel(new_filename, index=False, engine='openpyxl')
        print(f"✅ 数据已保存到新文件: {os.path.abspath(new_filename)}")

    elif mode == 'append':
        sheet_name = "Lane_Data"
        if os.path.exists(excel_filename):
            try:
                existing_df = pd.read_excel(excel_filename, sheet_name=sheet_name, engine='openpyxl')
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                with pd.ExcelWriter(excel_filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    combined_df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"✅ 数据已追加到 {os.path.abspath(excel_filename)} 的 {sheet_name} 末尾")
                print(f"   原 {len(existing_df)} 行，新 {len(df)} 行，共 {len(combined_df)} 行")
            except Exception as e:
                print(f"⚠️ 读取已有 Sheet 失败，将创建新 Sheet: {e}")
                with pd.ExcelWriter(excel_filename, engine='openpyxl', mode='a', if_sheet_exists='new') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"✅ 已创建新 Sheet {sheet_name} 并写入数据")
        else:
            with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"✅ 文件不存在，已创建新文件: {os.path.abspath(excel_filename)}")

    elif mode == 'overwrite':
        sheet_name = "Lane_Data"
        if os.path.exists(excel_filename):
            with pd.ExcelWriter(excel_filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"✅ 已覆盖 {os.path.abspath(excel_filename)} 中的 sheet: {sheet_name}")
        else:
            with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"✅ 文件不存在，已创建新文件: {os.path.abspath(excel_filename)}")

    else:
        df.to_excel(excel_filename, index=False, engine='openpyxl')
        print(f"✅ 数据已保存到: {os.path.abspath(excel_filename)}")

# ========== 主函数 ==========
def main():
    # 从 config 读取配置
    SERIAL_PORT_COM7 = CFG_COM7
    SERIAL_PORT_COM3 = CFG_COM3
    BAUD_RATE = CFG_BAUD
    MULTIMETER_ADDRESSES = ['TCPIP0::172.17.17.108::inst0::INSTR']

    # 1. 获取元数据
    metadata = get_metadata()

    # 2. 选择保存模式
    print("\n请选择保存模式:")
    print("  1. 生成新文件（带时间戳，默认）")
    print("  2. 追加到已有文件（同一文件同一Sheet，末尾追加）")
    print("  3. 覆盖已有文件（替换文件中的 Lane_Data Sheet）")
    save_choice = input("请选择 (1-3): ").strip() or "1"
    mode_map = {"1": "new", "2": "append", "3": "overwrite"}
    save_mode = mode_map.get(save_choice, "new")

    if save_mode == "new":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_FILE = f"./xlsx/extract_dcc_final_{ts}.xlsx"
    else:
        OUTPUT_FILE = "./xlsx/extract_dcc_final.xlsx"
    os.makedirs("./xlsx", exist_ok=True)

    print("=" * 96)
    print("extract_dcc_final - 完整 DCC DSK 值提取测试（含调试输出）")
    print(f"主控串口: {SERIAL_PORT_COM7} (逻辑 COM7), 辅助串口: {SERIAL_PORT_COM3}")
    print(f"输出文件: {OUTPUT_FILE} (模式: {save_mode})")
    print("=" * 96)

    # 清空全局数据
    global voltage_readings, com3_response_data
    voltage_readings.clear()
    com3_response_data.clear()

    # 3. 打开串口
    com7_ser = serial_utils.setup_serial_port(SERIAL_PORT_COM7, BAUD_RATE, 1.0)
    com3_ser = serial_utils.setup_serial_port(SERIAL_PORT_COM3, BAUD_RATE, 1.0)
    if not com7_ser or not com3_ser:
        print("串口打开失败，退出")
        if com7_ser: com7_ser.close()
        if com3_ser: com3_ser.close()
        return

    # 启动 COM3 接收线程（用于收集大数据量响应，但我们的 send_cmd 不依赖它，仅备用于 main_controller 函数）
    serial_utils.stop_receiving = False
    com3_thread = threading.Thread(
        target=serial_utils.receive_data_thread_com3,
        args=(com3_ser,), daemon=True
    )
    com3_thread.start()
    time.sleep(0.5)

    try:
        # ===== 步骤1: 初始化 =====
        print("\n[步骤1] 执行初始化命令...")
        init_cmds = [
            "phy_init_only",
            "m3_run",
            "phy_macro_reset",
            "serdes_set_cca_skip 0 0 0 0xffffffff",
            "serdes_set_cca_skip 0 0 1 0xffffffff",
            "serdes_start_cm 0 0  3",
            "serdes_pstate_chg 0 0 0xf 0",
            "serdes_rate_chg 0 0 0xf 5"
        ]
        for cmd in init_cmds:
            send_cmd(com7_ser, cmd, delay=0.5, timeout=3.0)
        time.sleep(2.0)

        # ===== 步骤2: 一次性固定 mm 配置 =====
        print("\n[步骤2] 发送固定 mm 配置（仅一次）...")
        fixed_mm = [
            "mm 0xb0303c24 0x4142be51",
            "mm 0xb0304424 0x4142be51",
            "mm 0xb0304c24 0x4142be51",
            "mm 0xb0305424 0x4142be51"
        ]
        for cmd in fixed_mm:
            send_cmd(com7_ser, cmd, delay=0.2, timeout=2.0)
        time.sleep(1.0)

        # ===== 步骤3: 逐通道测试 =====
        # 11 个电压点对应的信号 ID（顺序与原始项目一致）
        sig_sequence = [26, 16, 14, 20, 18, 19, 1, 26, 26, 26, 26]

        for lane_idx in range(4):
            print(f"\n{'#'*60}")
            print(f"测试 Lane {lane_idx}")
            print(f"{'#'*60}")

            # ---- 3.1 启用通道 ----
            lane_mask = 1 << lane_idx
            print(f"[Lane{lane_idx}] 启用通道 (mask=0x{lane_mask:x})")
            # send_cmd(com7_ser, f"serdes_start_tx 0 0x{lane_mask:x} 5", delay=1.0, timeout=3.0)
            # send_cmd(com7_ser, f"serdes_start_rx 0 0x{lane_mask:x} 5", delay=1.0, timeout=3.0)
            # time.sleep(2.0)   # 等待通道稳定

            # ---- 3.2 构建 ATB 读数命令 ----
            cmds = []
            for sig in sig_sequence:
                cmds.append(f"serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 {lane_idx} 0 0 9 0 1200 0 {sig} {sig}")
                cmds.append(f"serdes_atb_enable 0 0 {lane_idx} 1 1")
                cmds.append("READ_VOLTAGE_34470A")
                cmds.append(f"serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 {lane_idx} 0 0 13 0 1200 0 63 63")
                cmds.append("")  # 空行分隔

            # ---- 3.3 发送 ATB 批次 ----
            send_batch_with_voltage(
                ser=com7_ser,
                commands=cmds,
                batch_name=f"Lane{lane_idx}_ATB",
                current_lane=f"lane{lane_idx}",
                dmm_addresses=MULTIMETER_ADDRESSES,
                cmd_delay=0.2,
                timeout=2.5
            )

            # ---- 3.4 发送 COM3 命令 ----
            print(f"\n[Lane{lane_idx}] 发送 COM3 命令...")
            com3_cmds = [
                f"dump_ssm_cal_result {lane_idx}",
                f"dump_rx_dll_Deskew_v2 {lane_idx}",
                f"dump_tx_drv1ui_cal_res {lane_idx}"  # 新增

            ]

            # 使用原项目的 COM3 发送函数，它会自动将响应存入 data_processor.com3_response_data
            import data_processor as dp
            dp.com3_response_data.clear()
            for cmd in com3_cmds:
                main_controller.send_command_to_com3(
                    ser=com3_ser,
                    command=cmd,
                    command_delay=1.0,
                    response_timeout=10.0,
                    batch_name=f"[Lane{lane_idx}]",
                    show_tx_rx=True
                )
            # 将数据转移到本脚本的全局列表
            com3_response_data.extend(dp.com3_response_data)
            dp.com3_response_data.clear()

            time.sleep(2.0)   # 通道间间隔

        # ===== 步骤4: 保存结果 =====
        print("\n[步骤4] 所有通道测试完成，保存数据...")
        save_results_to_excel(OUTPUT_FILE, metadata, save_mode)

    except KeyboardInterrupt:
        print("\n用户中断，正在保存已收集的数据...")
        save_results_to_excel(OUTPUT_FILE, metadata, save_mode)
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()
        save_results_to_excel(OUTPUT_FILE, metadata, save_mode)
    finally:
        # 清理资源
        serial_utils.stop_receiving = True
        com3_thread.join(timeout=1)
        com7_ser.close()
        com3_ser.close()
        print("串口已关闭，程序结束。")

if __name__ == "__main__":
    main()