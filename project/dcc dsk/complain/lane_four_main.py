# lane_four_main.py - 主程序入口
import time
import threading
from datetime import datetime
import config
import serial_utils
import data_processor
import main_controller

#
# def main():
#     """
#     主函数 - 支持4通道测试 (lane0-lane3)
#     """
#     serial_utils.stop_receiving = False
#
#     # Excel文件保存路径
#     EXCEL_FILENAME = f"./xlsx/serial_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
#
#     print("=" * 80)
#     print("四通道串口通信测试程序")
#     print(f"目标串口1: {config.SERIAL_PORT_COM7}, 波特率: {config.BAUD_RATE}")
#     print(f"目标串口2: {config.SERIAL_PORT_COM3}, 波特率: {config.BAUD_RATE}")
#     print(f"Excel输出文件: {EXCEL_FILENAME}")
#     print(f"测试通道: lane0, lane1, lane2, lane3")
#     print("=" * 80)
#
#     # 1. 打开串口
#     com7_ser = serial_utils.setup_serial_port(config.SERIAL_PORT_COM7, config.BAUD_RATE, config.READ_TIMEOUT)
#     com3_ser = serial_utils.setup_serial_port(config.SERIAL_PORT_COM3, config.BAUD_RATE, config.READ_TIMEOUT)
#
#     if not com7_ser or not com3_ser:
#         print("程序退出")
#         if com7_ser:
#             com7_ser.close()
#         if com3_ser:
#             com3_ser.close()
#         return
#
#     com7_receiver_thread = None
#     com3_receiver_thread = None
#
#     try:
#         # 2. 启动接收线程
#         serial_utils.stop_receiving = False
#         com7_receiver_thread = threading.Thread(target=serial_utils.receive_data_thread_com7, args=(com7_ser,), daemon=True)
#         com3_receiver_thread = threading.Thread(target=serial_utils.receive_data_thread_com3, args=(com3_ser,), daemon=True)
#
#         com7_receiver_thread.start()
#         com3_receiver_thread.start()
#         print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动COM7和COM3数据接收线程")
#
#         time.sleep(0.5)
#
#         # 3. 【仅一次】执行COM7初始化阶段
#         print(f"\n{'#' * 80}")
#         print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始COM7初始化阶段")
#         print(f"{'#' * 80}")
#
#         com7_batch1_count = main_controller.send_command_batch_com7(
#             ser=com7_ser,
#             batch_commands=config.BATCH_1_COMMANDS,
#             batch_name="COM7初始化阶段",
#             command_delay=config.BATCH_1_DELAY,
#             response_timeout=config.BATCH_1_RESPONSE_TIMEOUT,
#             show_tx_rx=config.BATCH_1_SHOW_TX_RX,
#             retry_count=0
#         )
#
#         # 初始化完成后等待一段时间
#         init_complete_delay = 3.0
#         print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7初始化完成，等待 {init_complete_delay} 秒...")
#         time.sleep(init_complete_delay)
#
#         # 4. 依次测试4个通道
#         total_com7_commands = 0
#         total_com3_commands = 0
#
#         for lane_index, lane_config in enumerate(config.LANE_CONFIGS):
#             lane_name = lane_config['name']
#             mm_param = lane_config['mm_param']
#             com3_param = lane_config['com3_param']
#
#             print(f"\n{'#' * 80}")
#             print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始测试通道: {lane_name}")
#             print(f"  MM参数: {mm_param}")
#             print(f"  COM3参数: {com3_param}")
#             print(f"{'#' * 80}")
#
#             # 4.1 启用当前通道
#             print(f"[{datetime.now().strftime('%H:%M:%S')}] 启用通道 {lane_name}...")
#
#             lane_mask = 1 << lane_index
#
#             # 在启用新通道前，重置之前的通道
#             if lane_index > 0:
#                 print(f"[{datetime.now().strftime('%H:%M:%S')}] 重置之前的通道，准备测试{lane_name}...")
#
#                 main_controller.send_command_to_com7(
#                     ser=com7_ser,
#                     command=f"serdes_start_tx 0 0x0 5",
#                     command_delay=1.0,
#                     response_timeout=3.0,
#                     batch_name=f"通道重置[{lane_name}]",
#                     show_tx_rx=True
#                 )
#
#                 main_controller.send_command_to_com7(
#                     ser=com7_ser,
#                     command=f"serdes_start_rx 0 0x0 5",
#                     command_delay=1.0,
#                     response_timeout=3.0,
#                     batch_name=f"通道重置[{lane_name}]",
#                     show_tx_rx=True
#                 )
#
#                 time.sleep(1.0)
#
#             # 启用当前通道的TX
#             main_controller.send_command_to_com7(
#                 ser=com7_ser,
#                 command=f"serdes_start_tx 0 0x{lane_mask:x} 5",
#                 command_delay=1.0,
#                 response_timeout=3.0,
#                 batch_name=f"通道启用[{lane_name}]",
#                 cmd_index=1,
#                 total_cmds=2,
#                 show_tx_rx=True,
#                 is_md_command_flag=False
#             )
#
#             # 启用当前通道的RX
#             main_controller.send_command_to_com7(
#                 ser=com7_ser,
#                 command=f"serdes_start_rx 0 0x{lane_mask:x} 5",
#                 command_delay=1.0,
#                 response_timeout=3.0,
#                 batch_name=f"通道启用[{lane_name}]",
#                 cmd_index=2,
#                 total_cmds=2,
#                 show_tx_rx=True,
#                 is_md_command_flag=False
#             )
#
#             # 等待通道启用完成
#             channel_enable_delay = 2.0
#             print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待 {channel_enable_delay} 秒让通道 {lane_name} 完全启用...")
#             time.sleep(channel_enable_delay)
#
#             # 4.2 生成并执行当前通道的快速执行阶段命令
#             import command_generator
#             batch_2_commands, com3_commands = command_generator.generate_batch_commands_for_lane(
#                 mm_param, com3_param, lane_index
#             )
#
#             com7_batch2_count = main_controller.send_command_batch_com7(
#                 ser=com7_ser,
#                 batch_commands=batch_2_commands,
#                 batch_name=f"COM7快速执行阶段[{lane_name}]",
#                 command_delay=config.BATCH_2_DELAY,
#                 response_timeout=config.BATCH_2_RESPONSE_TIMEOUT,
#                 show_tx_rx=config.BATCH_2_SHOW_TX_RX,
#                 retry_count=config.BATCH_2_RETRY_COUNT
#             )
#
#             # COM7完成后等待
#             com7_complete_delay = 2.0
#             print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7 {lane_name} 快速执行阶段完成，等待 {com7_complete_delay} 秒...")
#             time.sleep(com7_complete_delay)
#
#             # 4.3 执行COM3指令
#             com3_count = main_controller.send_command_batch_com3(
#                 ser=com3_ser,
#                 batch_commands=com3_commands,
#                 batch_name=f"COM3专用指令[{lane_name}]",
#                 command_delay=config.COM3_DELAY,
#                 response_timeout=config.COM3_RESPONSE_TIMEOUT,
#                 show_tx_rx=config.COM3_SHOW_TX_RX
#             )
#
#             # 通道间等待
#             lane_interval = 2.0
#             print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 通道 {lane_name} 测试完成，等待 {lane_interval} 秒...")
#             time.sleep(lane_interval)
#
#             total_com7_commands += com7_batch2_count
#             total_com3_commands += com3_count
#
#         print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有4个通道测试完成")
#         print(f"COM7初始化阶段: {com7_batch1_count} 条命令")
#         print(f"COM7快速执行阶段总计: {total_com7_commands} 条命令")
#         print(f"COM3指令总计: {total_com3_commands} 条命令")
#         print(f"总计发送: {com7_batch1_count + total_com7_commands + total_com3_commands} 条命令")
#
#         # 5. 等待最终响应
#         print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待额外响应...")
#         time.sleep(1.0)
#
#         # 6. 保存所有数据到Excel
#         data_processor.save_responses_to_excel_with_lanes(EXCEL_FILENAME)
#
#         print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行完成")
#
#     except KeyboardInterrupt:
#         print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
#         data_processor.save_responses_to_excel_with_lanes(EXCEL_FILENAME)
#     except Exception as e:
#         print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行出错: {e}")
#         data_processor.save_responses_to_excel_with_lanes(EXCEL_FILENAME)
#     finally:
#         # 7. 清理资源
#         print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在清理资源...")
#         serial_utils.stop_receiving = True
#
#         if com7_receiver_thread and com7_receiver_thread.is_alive():
#             com7_receiver_thread.join(timeout=1.0)
#         if com3_receiver_thread and com3_receiver_thread.is_alive():
#             com3_receiver_thread.join(timeout=1.0)
#
#         if com7_ser and com7_ser.is_open:
#             com7_ser.close()
#             print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7串口已关闭")
#
#         if com3_ser and com3_ser.is_open:
#             com3_ser.close()
#             print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3串口已关闭")
#
#         print("程序结束")
#

# lane_four_main.py - 修改主程序
def main():
    """
    主函数 - 支持4通道测试，并集成电压读取功能
    """
    serial_utils.stop_receiving = False

    # 初始化电压读取数据存储
    from main_controller import voltage_readings

    # Excel文件保存路径
    EXCEL_FILENAME = f"./xlsx/serial_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    print("=" * 80)
    print("四通道串口通信测试程序 - 集成电压读取功能")
    print(f"目标串口1: {config.SERIAL_PORT_COM7}, 波特率: {config.BAUD_RATE}")
    print(f"目标串口2: {config.SERIAL_PORT_COM3}, 波特率: {config.BAUD_RATE}")
    print(f"万用表地址: {main_controller.DMM_ADDRESSES}")
    print(f"Excel输出文件: {EXCEL_FILENAME}")
    print(f"测试通道: lane0, lane1, lane2, lane3")
    print("=" * 80)

    # 清空之前的电压读数
    voltage_readings.clear()


    # 1. 打开串口
    com7_ser = serial_utils.setup_serial_port(config.SERIAL_PORT_COM7, config.BAUD_RATE, config.READ_TIMEOUT)
    com3_ser = serial_utils.setup_serial_port(config.SERIAL_PORT_COM3, config.BAUD_RATE, config.READ_TIMEOUT)

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
        com7_receiver_thread = threading.Thread(target=serial_utils.receive_data_thread_com7, args=(com7_ser,), daemon=True)
        com3_receiver_thread = threading.Thread(target=serial_utils.receive_data_thread_com3, args=(com3_ser,), daemon=True)

        com7_receiver_thread.start()
        com3_receiver_thread.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动COM7和COM3数据接收线程")

        time.sleep(0.5)

        # 3. 【仅一次】执行COM7初始化阶段
        print(f"\n{'#' * 80}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始COM7初始化阶段")
        print(f"{'#' * 80}")

        com7_batch1_count = main_controller.send_command_batch_com7(
            ser=com7_ser,
            batch_commands=config.BATCH_1_COMMANDS,
            batch_name="COM7初始化阶段",
            command_delay=config.BATCH_1_DELAY,
            response_timeout=config.BATCH_1_RESPONSE_TIMEOUT,
            show_tx_rx=config.BATCH_1_SHOW_TX_RX,
            retry_count=0
        )

        # 初始化完成后等待一段时间
        init_complete_delay = 3.0
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7初始化完成，等待 {init_complete_delay} 秒...")
        time.sleep(init_complete_delay)

        # 4. 依次测试4个通道
        total_com7_commands = 0
        total_com3_commands = 0

        # 在测试通道循环中，修改COM7批次调用
        for lane_index, lane_config in enumerate(config.LANE_CONFIGS):
            lane_name = lane_config['name']
            mm_param = lane_config['mm_param']
            com3_param = lane_config['com3_param']

            print(f"\n{'#' * 80}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始测试通道: {lane_name}")
            print(f"  MM参数: {mm_param}")
            print(f"  COM3参数: {com3_param}")
            print(f"{'#' * 80}")

            # 4.1 启用当前通道
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 启用通道 {lane_name}...")

            lane_mask = 1 << lane_index

            # 在启用新通道前，重置之前的通道
            if lane_index > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 重置之前的通道，准备测试{lane_name}...")

                main_controller.send_command_to_com7(
                    ser=com7_ser,
                    command=f"serdes_start_tx 0 0x0 5",
                    command_delay=1.0,
                    response_timeout=3.0,
                    batch_name=f"通道重置[{lane_name}]",
                    show_tx_rx=True
                )

                main_controller.send_command_to_com7(
                    ser=com7_ser,
                    command=f"serdes_start_rx 0 0x0 5",
                    command_delay=1.0,
                    response_timeout=3.0,
                    batch_name=f"通道重置[{lane_name}]",
                    show_tx_rx=True
                )

                time.sleep(1.0)

            # 启用当前通道的TX
            main_controller.send_command_to_com7(
                ser=com7_ser,
                command=f"serdes_start_tx 0 0x{lane_mask:x} 5",
                command_delay=1.0,
                response_timeout=3.0,
                batch_name=f"通道启用[{lane_name}]",
                cmd_index=1,
                total_cmds=2,
                show_tx_rx=True,
                is_md_command_flag=False
            )

            # 启用当前通道的RX
            main_controller.send_command_to_com7(
                ser=com7_ser,
                command=f"serdes_start_rx 0 0x{lane_mask:x} 5",
                command_delay=1.0,
                response_timeout=3.0,
                batch_name=f"通道启用[{lane_name}]",
                cmd_index=2,
                total_cmds=2,
                show_tx_rx=True,
                is_md_command_flag=False
            )

            # 等待通道启用完成
            channel_enable_delay = 2.0
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] 等待 {channel_enable_delay} 秒让通道 {lane_name} 完全启用...")
            time.sleep(channel_enable_delay)

            # 4.2 生成并执行当前通道的快速执行阶段命令
            import command_generator
            batch_2_commands, com3_commands = command_generator.generate_batch_commands_for_lane(
                mm_param, com3_param, lane_index
            )

            # 修改这部分，使用新的带电压读取的批次发送函数
            com7_batch2_count = main_controller.send_command_batch_com7_with_voltage(
                ser=com7_ser,
                batch_commands=batch_2_commands,
                batch_name=f"COM7快速执行阶段[{lane_name}]",
                command_delay=config.BATCH_2_DELAY,
                response_timeout=config.BATCH_2_RESPONSE_TIMEOUT,
                show_tx_rx=config.BATCH_2_SHOW_TX_RX,
                retry_count=config.BATCH_2_RETRY_COUNT,
                current_lane=lane_name,  # 传递当前通道信息
                dmm_addresses=main_controller.DMM_ADDRESSES
            )
            # COM7完成后等待
            com7_complete_delay = 2.0
            print(
                f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7 {lane_name} 快速执行阶段完成，等待 {com7_complete_delay} 秒...")
            time.sleep(com7_complete_delay)

            # 4.3 执行COM3指令
            com3_count = main_controller.send_command_batch_com3(
                ser=com3_ser,
                batch_commands=com3_commands,
                batch_name=f"COM3专用指令[{lane_name}]",
                command_delay=config.COM3_DELAY,
                response_timeout=config.COM3_RESPONSE_TIMEOUT,
                show_tx_rx=config.COM3_SHOW_TX_RX
            )

            # 通道间等待
            lane_interval = 2.0
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 通道 {lane_name} 测试完成，等待 {lane_interval} 秒...")
            time.sleep(lane_interval)

            total_com7_commands += com7_batch2_count
            total_com3_commands += com3_count

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有4个通道测试完成")
        print(f"COM7初始化阶段: {com7_batch1_count} 条命令")
        print(f"COM7快速执行阶段总计: {total_com7_commands} 条命令")
        print(f"COM3指令总计: {total_com3_commands} 条命令")
        print(f"总计发送: {com7_batch1_count + total_com7_commands + total_com3_commands} 条命令")

        # 5. 等待最终响应
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待额外响应...")
        time.sleep(1.0)

        # 6. 保存所有数据到Excel
        # 在保存数据时，保存所有数据
        # data_processor.save_all_data_to_excel(EXCEL_FILENAME, voltage_readings)
        data_processor.save_responses_to_excel_with_voltage(EXCEL_FILENAME)
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行完成")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
        data_processor.save_responses_to_excel_with_lanes(EXCEL_FILENAME)
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行出错: {e}")
        data_processor.save_responses_to_excel_with_lanes(EXCEL_FILENAME)
    finally:
        # 7. 清理资源
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

        print("程序结束")


if __name__ == "__main__":
    main()