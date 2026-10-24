"""
四通道串口通信测试程序 - 主入口（含元数据输入）
"""

import os
import time
import threading
from datetime import datetime
import serial_utils
import data_processor
import main_controller
from command_generator import generate_batch_commands_for_lane
from config import LANE_CONFIGS, SERIAL_PORT_COM7 as CFG_COM7, SERIAL_PORT_COM3 as CFG_COM3, BAUD_RATE as CFG_BAUD


# ========== 新增：元数据获取函数（与其它测试项保持一致） ==========
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


def main():
    # ========== 配置参数（使用 config.py 中的配置）==========
    SERIAL_PORT_COM7 = CFG_COM7
    SERIAL_PORT_COM3 = CFG_COM3
    BAUD_RATE = CFG_BAUD
    MULTIMETER_ADDRESSES = ['TCPIP0::172.17.17.108::inst0::INSTR']

    # 先获取元数据
    metadata = get_metadata()

    # 输出文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_FILE = f"./xlsx/serial_responses_{timestamp}.xlsx"

    # 确保输出目录存在
    os.makedirs("../temp4_main/xlsx", exist_ok=True)

    # ========== 打印配置信息 ==========
    print("=" * 96)
    print("四通道串口通信测试程序 - 集成电压读取功能（含元数据）")
    print(f"目标串口1 (COM7): {SERIAL_PORT_COM7}, 波特率: {BAUD_RATE}")
    print(f"目标串口2 (COM3): {SERIAL_PORT_COM3}, 波特率: {BAUD_RATE}")
    print(f"万用表地址: {MULTIMETER_ADDRESSES}")
    print(f"Excel输出文件: {OUTPUT_FILE}")
    print(f"测试通道: lane0, lane1, lane2, lane3")
    print("=" * 96)

    # 清空之前的电压读数
    data_processor.voltage_readings.clear()

    # 1. 打开串口
    com7_ser = serial_utils.setup_serial_port(SERIAL_PORT_COM7, BAUD_RATE, 1.0)
    com3_ser = serial_utils.setup_serial_port(SERIAL_PORT_COM3, BAUD_RATE, 1.0)

    if not com7_ser or not com3_ser:
        print("程序退出")
        if com7_ser:
            com7_ser.close()
        if com3_ser:
            com3_ser.close()
        return

    com7_receiver_thread = None
    com3_receiver_thread = None

    try:
        # 2. 启动接收线程
        serial_utils.stop_receiving = False
        com7_receiver_thread = threading.Thread(
            target=serial_utils.receive_data_thread_com7,
            args=(com7_ser,),
            daemon=True
        )
        com3_receiver_thread = threading.Thread(
            target=serial_utils.receive_data_thread_com3,
            args=(com3_ser,),
            daemon=True
        )

        com7_receiver_thread.start()
        com3_receiver_thread.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动COM7和COM3数据接收线程")

        time.sleep(0.5)

        # ========== 初始化阶段 ==========
        print(f"\n{'#' * 76}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始COM7初始化阶段")
        print(f"{'#' * 76}")

        init_commands = [
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
            batch_commands=init_commands,
            batch_name="COM7初始化阶段",
            command_delay=0.5,
            response_timeout=3.0,
            show_tx_rx=True,
            retry_count=0
        )

        print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7初始化完成，等待 3.0 秒...")
        time.sleep(3.0)

        # ========== 逐通道测试 ==========
        for lane_index in range(4):
            print(f"\n{'#' * 76}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始测试通道: lane{lane_index}")

            lane_config = LANE_CONFIGS[lane_index]
            mm_param = lane_config['mm_param']
            com3_param = lane_config['com3_param']

            print(f"  MM参数: {mm_param}")
            print(f"  COM3参数: {com3_param}")
            print(f"{'#' * 76}")

            # ---- 通道启用 ----
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 启用通道 lane{lane_index}...")

            lane_mask = 1 << lane_index

            # # 重置之前的通道
            # if lane_index > 0:
            #     print(f"[{datetime.now().strftime('%H:%M:%S')}] 重置之前的通道，准备测试lane{lane_index}...")
            #     main_controller.send_command_to_com7(
            #         ser=com7_ser,
            #         command=f"serdes_start_tx 0 0x0 5",
            #         command_delay=1.0,
            #         response_timeout=3.0,
            #         batch_name=f"通道重置[lane{lane_index}]",
            #         show_tx_rx=True
            #     )
            #     main_controller.send_command_to_com7(
            #         ser=com7_ser,
            #         command=f"serdes_start_rx 0 0x0 5",
            #         command_delay=1.0,
            #         response_timeout=3.0,
            #         batch_name=f"通道重置[lane{lane_index}]",
            #         show_tx_rx=True
            #     )
            #     time.sleep(1.0)
            #
            # # 启用当前通道
            # main_controller.send_command_to_com7(
            #     ser=com7_ser,
            #     command=f"serdes_start_tx 0 0x{lane_mask:x} 5",
            #     command_delay=1.0,
            #     response_timeout=3.0,
            #     batch_name=f"通道启用[lane{lane_index}]",
            #     cmd_index=1,
            #     total_cmds=2,
            #     show_tx_rx=True,
            #     is_md_command_flag=False
            # )
            # main_controller.send_command_to_com7(
            #     ser=com7_ser,
            #     command=f"serdes_start_rx 0 0x{lane_mask:x} 5",
            #     command_delay=1.0,
            #     response_timeout=3.0,
            #     batch_name=f"通道启用[lane{lane_index}]",
            #     cmd_index=2,
            #     total_cmds=2,
            #     show_tx_rx=True,
            #     is_md_command_flag=False
            # )
            #
            # print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待 2.0 秒让通道 lane{lane_index} 完全启用...")
            # time.sleep(2.0)

            # ---- 生成并执行快速执行阶段命令 ----
            base_template, com3_commands = generate_batch_commands_for_lane(
                mm_param, com3_param, lane_index
            )

            # 统计命令数量
            md_count = sum(1 for c in base_template if c.strip().startswith("md ") or c.strip().startswith("MD "))
            voltage_count = sum(1 for c in base_template if c.strip() == "READ_VOLTAGE_34470A")

            print(f"\n{'=' * 62}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 开始发送批次: COM7快速执行阶段[lane{lane_index}]")
            print(f"批次配置: 命令间延迟=0.2s, 响应超时=2.5s, 显示发送接收=False, 重试次数=1")
            print(f"电压读取点: {voltage_count} 个")
            print(f"命令总数: {len([c for c in base_template if c.strip()])} 条")
            print(f"其中MD命令: {md_count} 条")
            print(f"其中电压读取点: {voltage_count} 个")
            print(f"{'=' * 62}")

            com7_count = main_controller.send_command_batch_com7_with_voltage(
                ser=com7_ser,
                batch_commands=base_template,
                batch_name=f"COM7快速执行阶段[lane{lane_index}]",
                command_delay=0.2,
                response_timeout=2.5,
                show_tx_rx=False,
                retry_count=1,
                current_lane=f"lane{lane_index}",
                dmm_addresses=MULTIMETER_ADDRESSES
            )

            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 lane{lane_index} 快速执行阶段完成，等待 2.0 秒...")
            time.sleep(2.0)

            print(f"\n{'=' * 66}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 开始发送批次: COM3专用指令[lane{lane_index}]")
            print(f"批次配置: 命令间延迟=1.0s, 响应超时=10.0s (大数据量), 显示发送接收=True")
            print(f"命令总数: 2 条")
            print(f"{'=' * 66}")

            com3_count = main_controller.send_command_batch_com3(
                ser=com3_ser,
                batch_commands=com3_commands,
                batch_name=f"COM3专用指令[lane{lane_index}]",
                command_delay=1.0,
                response_timeout=10.0,  # 增加到10秒，适应大数据量
                show_tx_rx=True
            )

            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 批次 COM3专用指令[lane{lane_index}] 发送完成")
            print(f"  共发送 2 条命令，成功 2 条")

            print(f"[{datetime.now().strftime('%H:%M:%S')}] 通道 lane{lane_index} 测试完成，等待 2.0 秒...")
            time.sleep(2.0)

        # ========== 所有通道测试完成，保存结果（传入元数据） ==========
        print(f"\n{'=' * 65}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 所有通道测试完成，正在保存结果...")

        # 修改调用：传入 metadata
        data_processor.save_responses_to_excel_with_voltage(OUTPUT_FILE, metadata)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 程序执行完毕")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
        data_processor.save_responses_to_excel_with_voltage(OUTPUT_FILE, metadata)
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序出错: {str(e)}")
        import traceback
        traceback.print_exc()
        data_processor.save_responses_to_excel_with_voltage(OUTPUT_FILE, metadata)
    finally:
        # 清理资源
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在清理资源...")
        serial_utils.stop_receiving = True

        if com7_receiver_thread and com7_receiver_thread.is_alive():
            com7_receiver_thread.join(timeout=1.0)
        if com3_receiver_thread and com3_receiver_thread.is_alive():
            com3_receiver_thread.join(timeout=1.0)

        if com7_ser and com7_ser.is_open:
            com7_ser.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7串口已关闭")
        if com3_ser and com3_ser.is_open:
            com3_ser.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3串口已关闭")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口已关闭")


if __name__ == "__main__":
    main()