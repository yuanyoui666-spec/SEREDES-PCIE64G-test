"""
temp4_main.py - 四通道测试程序（内置COM3数据提取）
集成元数据输入 + 保存模式选择（同文件同Sheet追加/覆盖）
"""

import os
import time
import threading
import re
import pandas as pd
from datetime import datetime

import serial_utils
import main_controller
from command_generator import generate_batch_commands_for_lane
from config import LANE_CONFIGS, SERIAL_PORT_COM7 as CFG_COM7, SERIAL_PORT_COM3 as CFG_COM3, BAUD_RATE as CFG_BAUD

# ========== 全局数据存储 ==========
com7_md_response_data = []
com3_response_data = []
voltage_readings = []

# ========== 提取函数 ==========
def parse_ssm_value(text, type_id):
    pattern = rf'type:{type_id}\s+valid:\d+\s+res:(\d+)\s+name:'
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None

def parse_fineskew_codes(text):
    codes = [None] * 8
    for i in range(8):
        pattern = rf'FineSkewCode{i}:(\d+)'
        match = re.search(pattern, text)
        if match:
            codes[i] = int(match.group(1))
    return codes

# ========== 新增：元数据获取函数 ==========
def get_metadata():
    """交互式获取测试元数据"""
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

# ========== 保存函数（含提取逻辑 + 元数据 + 三种模式） ==========
def save_responses_to_excel_with_extraction(excel_filename, metadata=None, mode='new'):
    """
    保存多通道响应数据到Excel文件 - 宽表格式
    每个通道一行，所有参数作为列
    包含 COM3 数据（dump_ssm_cal_result, dump_rx_dll_Deskew_v2）
    支持元数据列插入和三种保存模式：
      - 'new': 生成带时间戳的新文件
      - 'append': 追加到已有文件的同一 Sheet（Lane_Data）末尾（同Sheet末尾追加）
      - 'overwrite': 覆盖已有文件中的 Sheet（Lane_Data）
    """
    lane_md_data = {f'lane{i}': {} for i in range(4)}
    lane_voltage_data = {f'lane{i}': {} for i in range(4)}
    lane_com3_data = {f'lane{i}': {} for i in range(4)}

    # ----- 1. MD数据处理 -----
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
        if "初始化" in batch and "[" not in batch:
            continue
        if value and has_response == "是":
            # 提取通道名 (batch 格式如 "[Lane0]")
            lane_name = "lane0"
            if "[" in batch and "]" in batch:
                lane_info = batch.split("[")[1].split("]")[0]
                if lane_info.startswith("Lane"):
                    lane_num = int(lane_info.replace("Lane", ""))
                    lane_name = f"lane{lane_num}"
            # 按顺序填充参数
            lane_md_count = sum(1 for v in lane_md_data[lane_name].values() if v is not None) + 1
            param_name = None
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
            if param_name:
                # 提取位域 (bit 11~19)
                converted = None
                if value and len(value) == 8:
                    try:
                        reg = int(value, 16)
                        byte1 = (reg >> 8) & 0xFF
                        byte2 = (reg >> 16) & 0xFF
                        data_low = (byte1 >> 3) & 0x1F
                        data_high = (byte2 & 0x0F) << 5
                        converted = data_high | data_low
                    except:
                        converted = None
                lane_md_data[lane_name][param_name] = converted

    # ----- 2. 电压数据处理 -----
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

    # ----- 3. COM3数据处理（包含提取） -----
    for record in com3_response_data:
        timestamp, cmd, response, batch, has_response = record
        if response and has_response in ["执行成功", "是"]:
            cleaned = response.strip()
            if not cleaned:
                continue
            # 提取通道名
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

            elif "dump_rx_dll_Deskew_v2" in cmd:
                lane_com3_data[lane_name]['dump_rx_dll_Deskew_v2'] = cleaned
                codes = parse_fineskew_codes(cleaned)
                for idx, code in enumerate(codes):
                    if code is not None:
                        lane_com3_data[lane_name][f'FineSkew_{idx}'] = code

    # ----- 4. 构建宽表 -----
    all_records = []
    for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
        lane_num = int(lane_name.replace('lane', ''))
        md = lane_md_data.get(lane_name, {})
        volt = lane_voltage_data.get(lane_name, {})
        com3 = lane_com3_data.get(lane_name, {})

        record = {
            'group': 0,
            'macro': 0,
            'lane': lane_num,
            'vbg': volt.get('vbg', 0),
            'tx_vreg1_vp_s': volt.get('tx_vreg1_vp_s', 0),
            'tx_vreg0_vp': volt.get('tx_vreg0_vp', 0),
            'dll_comp_dcc_dac_code (dccinpcal)': md.get('dll_comp_dcc_dac_code（inpcal）', 0),
            'dll_comp_dcc_dac_code (dccinmcal)': md.get('dll_comp_dcc_dac_code（inmcal）', 0),
            'tx_dll_vreg': volt.get('tx_dll_vreg', 0),
            'inp': volt.get('inp', 0),
            'inm': volt.get('inm', 0),
            'dll_comp_dcc_dac_code（dcccal 0）': md.get('dll_comp_dcc_dac_code（dcccal 0）', 0),
            'dll_comp_dcc_dac_code（dcccal 90）': md.get('dll_comp_dcc_dac_code（dcccal 90）', 0),
            'dll_comp_dcc_dac_code（dcccal 180）': md.get('dll_comp_dcc_dac_code（dcccal 180）', 0),
            'dll_comp_dcc_dac_code（dcccal 270）': md.get('dll_comp_dcc_dac_code（dcccal 270）', 0),
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
            'dump_ssm_cal_result': com3.get('dump_ssm_cal_result', ''),
            'dump_rx_dll_Deskew_v2': com3.get('dump_rx_dll_Deskew_v2', ''),
        }
        all_records.append(record)

    if not all_records:
        print("没有数据可保存")
        return

    # ----- 合并元数据 -----
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
        # 列顺序：元数据列在前
        meta_cols = ['芯片编号', '温度电压', 'FW版本', 'gui版本', '单板编号']
        meta_present = [c for c in meta_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in meta_present]
        df = df[meta_present + other_cols]
    else:
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
            'RxDll0DccInp', 'RxDll0DccInm',
            'FineSkew_0', 'FineSkew_1', 'FineSkew_2', 'FineSkew_3',
            'FineSkew_4', 'FineSkew_5', 'FineSkew_6', 'FineSkew_7',
            'dump_ssm_cal_result',
            'dump_rx_dll_Deskew_v2'
        ]
        column_order = [c for c in column_order if c in df.columns]
        df = df[column_order]

    os.makedirs(os.path.dirname(excel_filename) or '.', exist_ok=True)

    # ----- 根据模式保存 -----
    if mode == 'new':
        base, ext = os.path.splitext(excel_filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{base}_{timestamp}{ext}"
        df.to_excel(new_filename, index=False, engine='openpyxl')
        print(f"✅ 数据已保存到新文件: {os.path.abspath(new_filename)}")

    elif mode == 'append':
        sheet_name = "Lane_Data"
        if os.path.exists(excel_filename):
            try:
                # 读取已有数据（同一 Sheet）
                existing_df = pd.read_excel(excel_filename, sheet_name=sheet_name, engine='openpyxl')
                # 合并：新数据追加到末尾（按列名对齐）
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                # 写回，覆盖该 Sheet
                with pd.ExcelWriter(excel_filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    combined_df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"✅ 数据已追加到 {os.path.abspath(excel_filename)} 的 {sheet_name} 末尾")
                print(f"   原 {len(existing_df)} 行，新 {len(df)} 行，共 {len(combined_df)} 行")
            except Exception as e:
                # 如果读取失败（如 Sheet 不存在），则直接写入该 Sheet
                print(f"⚠️ 读取已有 Sheet 失败，将创建新 Sheet: {e}")
                with pd.ExcelWriter(excel_filename, engine='openpyxl', mode='a', if_sheet_exists='new') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"✅ 已创建新 Sheet {sheet_name} 并写入数据")
        else:
            # 文件不存在，创建新文件
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
    SERIAL_PORT_COM7 = CFG_COM7
    SERIAL_PORT_COM3 = CFG_COM3
    BAUD_RATE = CFG_BAUD
    MULTIMETER_ADDRESSES = ['TCPIP0::172.17.17.108::inst0::INSTR']

    # ---- 1. 获取元数据 ----
    metadata = get_metadata()

    # ---- 2. 选择保存模式 ----
    print("\n请选择保存模式:")
    print("  1. 生成新文件（带时间戳，默认）")
    print("  2. 追加到已有文件（同一文件同一Sheet，末尾追加数据）")
    print("  3. 覆盖已有文件（替换文件中的 Lane_Data Sheet）")
    save_choice = input("请选择 (1-3): ").strip() or "1"
    mode_map = {"1": "new", "2": "append", "3": "overwrite"}
    save_mode = mode_map.get(save_choice, "new")

    # 根据模式决定文件名
    if save_mode == "new":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_FILE = f"./xlsx/temp4_result_{timestamp}.xlsx"
    else:
        OUTPUT_FILE = "./xlsx/temp4_result.xlsx"

    os.makedirs("./xlsx", exist_ok=True)

    print("=" * 96)
    print("temp4_main - 四通道测试（内置COM3提取）修正版")
    print(f"COM7: {SERIAL_PORT_COM7}, COM3: {SERIAL_PORT_COM3}")
    print(f"输出: {OUTPUT_FILE} (模式: {save_mode})")
    print("=" * 96)

    # 清空全局数据
    com7_md_response_data.clear()
    com3_response_data.clear()
    voltage_readings.clear()

    # 连接串口
    com7_ser = serial_utils.setup_serial_port(SERIAL_PORT_COM7, BAUD_RATE, 1.0)
    com3_ser = serial_utils.setup_serial_port(SERIAL_PORT_COM3, BAUD_RATE, 1.0)
    if not com7_ser or not com3_ser:
        print("串口打开失败，退出")
        if com7_ser: com7_ser.close()
        if com3_ser: com3_ser.close()
        return

    serial_utils.stop_receiving = False
    com7_thread = threading.Thread(target=serial_utils.receive_data_thread_com7, args=(com7_ser,), daemon=True)
    com3_thread = threading.Thread(target=serial_utils.receive_data_thread_com3, args=(com3_ser,), daemon=True)
    com7_thread.start()
    com3_thread.start()
    time.sleep(0.5)

    try:
        # ----- 初始化 -----
        print("\n执行初始化...")
        init_cmds = [
            "",
            "phy_init_only",
            "m3_run",
            "phy_macro_reset",
            "serdes_set_cca_skip 0 0 0 0xffffffff",
            "serdes_set_cca_skip 0 0 1 0xffffffff",
            "serdes_start_cm 0 0  3",
            "serdes_pstate_chg 0 0 0xf 0",
            "serdes_rate_chg 0 0 0xf 5"
        ]
        main_controller.send_command_batch_com7(
            ser=com7_ser,
            batch_commands=init_cmds,
            batch_name="[初始化]",
            command_delay=0.5,
            response_timeout=3.0,
            show_tx_rx=True,
            retry_count=0
        )
        time.sleep(3.0)

        # ----- 逐通道测试 -----
        for lane_idx in range(4):
            print(f"\n{'#'*60}\n测试 Lane{lane_idx}\n{'#'*60}")
            lane_config = LANE_CONFIGS[lane_idx]
            mm_param = lane_config['mm_param']
            com3_param = lane_config['com3_param']

            # 启用通道
            lane_mask = 1 << lane_idx
            # if lane_idx > 0:
            #     main_controller.send_command_to_com7(com7_ser, f"serdes_start_tx 0 0x0 5", 1.0, 3.0, f"[重置TX-{lane_idx}]", show_tx_rx=True)
            #     main_controller.send_command_to_com7(com7_ser, f"serdes_start_rx 0 0x0 5", 1.0, 3.0, f"[重置RX-{lane_idx}]", show_tx_rx=True)
            #     time.sleep(1.0)
            # main_controller.send_command_to_com7(com7_ser, f"serdes_start_tx 0 0x{lane_mask:x} 5", 1.0, 3.0, f"[启用TX-{lane_idx}]", show_tx_rx=True)
            # main_controller.send_command_to_com7(com7_ser, f"serdes_start_rx 0 0x{lane_mask:x} 5", 1.0, 3.0, f"[启用RX-{lane_idx}]", show_tx_rx=True)
            # time.sleep(2.0)

            # 生成命令
            base_cmds, com3_cmds = generate_batch_commands_for_lane(mm_param, com3_param, lane_idx)

            # 清空临时数据（使用 data_processor 模块的全局变量）
            import data_processor as dp
            dp.voltage_readings.clear()
            dp.com7_md_response_data.clear()
            dp.com3_response_data.clear()

            # 发送COM7批次（批次名含方括号）
            main_controller.send_command_batch_com7_with_voltage(
                ser=com7_ser,
                batch_commands=base_cmds,
                batch_name=f"[Lane{lane_idx}]",
                command_delay=0.2,
                response_timeout=2.5,
                show_tx_rx=False,
                retry_count=1,
                current_lane=f"lane{lane_idx}",
                dmm_addresses=MULTIMETER_ADDRESSES
            )
            # 收集数据到全局
            com7_md_response_data.extend(dp.com7_md_response_data)
            voltage_readings.extend(dp.voltage_readings)
            dp.com7_md_response_data.clear()
            dp.voltage_readings.clear()

            # 发送COM3批次
            main_controller.send_command_batch_com3(
                ser=com3_ser,
                batch_commands=com3_cmds,
                batch_name=f"[Lane{lane_idx}]",
                command_delay=1.0,
                response_timeout=10.0,
                show_tx_rx=True
            )
            com3_response_data.extend(dp.com3_response_data)
            dp.com3_response_data.clear()

            time.sleep(2.0)

        # ----- 保存结果（传入元数据和模式） -----
        print("\n所有通道测试完成，保存数据...")
        save_responses_to_excel_with_extraction(OUTPUT_FILE, metadata, save_mode)

    except KeyboardInterrupt:
        print("用户中断")
        save_responses_to_excel_with_extraction(OUTPUT_FILE, metadata, save_mode)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        save_responses_to_excel_with_extraction(OUTPUT_FILE, metadata, save_mode)
    finally:
        serial_utils.stop_receiving = True
        com7_thread.join(timeout=1)
        com3_thread.join(timeout=1)
        com7_ser.close()
        com3_ser.close()
        print("串口已关闭，程序结束。")

if __name__ == "__main__":
    main()