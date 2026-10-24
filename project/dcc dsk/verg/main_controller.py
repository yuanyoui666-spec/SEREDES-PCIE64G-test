# main_controller.py - 主控制器
import time
import threading
from datetime import datetime
import config
import serial_utils
import data_processor
import command_generator

##新增代码  0602 电压读取##
# main_controller.py - 新增电压读取功能
import pyvisa
from datetime import datetime

# 电压读取数据存储
voltage_readings = []

# 万用表配置
DMM_ADDRESSES = [
    "TCPIP0::172.17.17.108::inst0::INSTR",  # 设备1
]


def read_34470a_voltage(visa_address, dmm_index=0):
    """
    读取 Keysight 34470A 万用表电压
    兼容两种设备地址
    """
    try:
        rm = pyvisa.ResourceManager('@py')
        inst = rm.open_resource(visa_address)
        inst.timeout = 5000

        # 配置并读取直流电压
        inst.write("CONF:VOLT:DC")
        voltage = float(inst.query("READ?"))

        inst.close()

        # 保存读取数据
        voltage_readings.append({
            'timestamp': datetime.now(),
            'dmm_address': visa_address,
            'dmm_index': dmm_index,
            'voltage': voltage,
            'lane': 'current_lane_placeholder'  # 将在运行时填充
        })

        return voltage
    except Exception as e:
        print(f"读取失败 {visa_address}：{str(e)}")
        return None


def send_command_batch_com7_with_voltage(ser, batch_commands, batch_name, command_delay,
                                         response_timeout, show_tx_rx, retry_count=0,
                                         current_lane=None, dmm_addresses=DMM_ADDRESSES):
    """
    改进的COM7批次发送函数 - 支持电压读取
    """
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 开始发送批次: {batch_name}")
    print(
        f"批次配置: 命令间延迟={command_delay}s, 响应超时={response_timeout}s, 显示发送接收={show_tx_rx}, 重试次数={retry_count}")

    valid_commands = [cmd for cmd in batch_commands if cmd.strip()]
    print(f"命令总数: {len(valid_commands)} 条")

    md_count = len([cmd for cmd in valid_commands if data_processor.is_md_command(cmd)])
    voltage_count = len([cmd for cmd in valid_commands if cmd.strip() == "READ_VOLTAGE_34470A"])
    print(f"其中MD命令: {md_count} 条")
    print(f"其中电压读取点: {voltage_count} 个")
    print(f"{'=' * 60}")

    valid_count = 0
    md_success_count = 0
    md_fail_count = 0
    voltage_success_count = 0
    voltage_fail_count = 0

    for i, cmd in enumerate(batch_commands, 1):
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        valid_count += 1

        # 检查是否是电压读取命令
        if cmd.strip() == "READ_VOLTAGE_34470A":
            print(f"\n[电压读取点 {voltage_success_count + 1}]")
            print("-" * 40)

            # 读取所有配置的万用表
            for dmm_idx, dmm_addr in enumerate(dmm_addresses):
                voltage = read_34470a_voltage(dmm_addr, dmm_idx)
                if voltage is not None:
                    # 更新电压数据中的通道信息
                    if voltage_readings and current_lane:
                        voltage_readings[-1]['lane'] = current_lane
                        voltage_readings[-1]['batch'] = batch_name
                        voltage_readings[-1]['command_index'] = i

                    voltage_success_count += 1
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] 万用表{dmm_idx + 1} ({dmm_addr}) 电压: {voltage:.6f} V")
                else:
                    voltage_fail_count += 1
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 万用表{dmm_idx + 1} 读取失败")

            time.sleep(1.0)  # 电压读取后等待
            continue

        # 正常的命令发送逻辑
        is_md = data_processor.is_md_command(cmd)

        if is_md and retry_count > 0:
            response, hex_len, is_complete, hex_value = send_command_to_com7_with_retry(
                ser=ser,
                command=cmd,
                command_delay=command_delay,
                response_timeout=response_timeout,
                batch_name=batch_name,
                cmd_index=valid_count,
                total_cmds=len(valid_commands),
                show_tx_rx=show_tx_rx,
                is_md_command_flag=is_md,
                max_retries=retry_count
            )

            if is_complete:
                md_success_count += 1
            else:
                md_fail_count += 1
        else:
            response, hex_len, is_complete, hex_value = send_command_to_com7(
                ser=ser,
                command=cmd,
                command_delay=command_delay,
                response_timeout=response_timeout,
                batch_name=batch_name,
                cmd_index=valid_count,
                total_cmds=len(valid_commands),
                show_tx_rx=show_tx_rx,
                is_md_command_flag=is_md
            )

    print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 批次 {batch_name} 发送完成")
    print(f"  共发送 {valid_count} 条有效命令")
    if md_count > 0:
        print(f"  MD命令: 成功 {md_success_count}/{md_count}, 失败 {md_fail_count}/{md_count}")
    if voltage_count > 0:
        print(
            f"  电压读取: 成功 {voltage_success_count}/{voltage_count * len(dmm_addresses)}, 失败 {voltage_fail_count}/{voltage_count * len(dmm_addresses)}")

    return valid_count
##新增代码  0602 电压读取##

def send_command_to_com7(ser, command, command_delay, response_timeout,
                         batch_name="", cmd_index=0, total_cmds=0,
                         show_tx_rx=True, is_md_command_flag=False, retry_count=0):
    """
    向COM7发送单个命令并等待响应
    """
    if not command or command.isspace():
        return None, 0, False, ""

    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()

    try:
        time.sleep(0.1)
        with serial_utils.com7_receive_lock:
            serial_utils.com7_received_data.clear()

        ser.write(command.encode('utf-8'))
        ser.flush()

        if show_tx_rx or is_md_command_flag:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            batch_info = f"[{batch_name}] " if batch_name else ""
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            retry_info = f"[重试{retry_count}] " if retry_count > 0 else ""
            print(f"[{timestamp}] COM7 {batch_info}{retry_info}发送{cmd_info}: {command.strip()}")

        response_text = ""
        response_buffer = ""

        time.sleep(command_delay)

        start_time = time.time()
        collection_count = 0
        max_collections = 10

        while time.time() - start_time < response_timeout and collection_count < max_collections:
            with serial_utils.com7_receive_lock:
                if serial_utils.com7_received_data:
                    for resp_time, resp_data in serial_utils.com7_received_data:
                        response_buffer += resp_data

            with serial_utils.com7_receive_lock:
                serial_utils.com7_received_data.clear()

            if response_buffer:
                start_time = time.time()
            else:
                time.sleep(0.2)

            collection_count += 1

        response_text = response_buffer.strip()

        if is_md_command_flag:
            address = data_processor.parse_md_address(command.strip())

            if response_text:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 MD命令响应: {response_text[:100]}")

                hex_value = serial_utils.extract_hex_value(response_text)

                if hex_value and len(hex_value) >= 2:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 提取到十六进制值: {hex_value}")
                    has_response = "是"

                    data_processor.com7_md_response_data.append([
                        send_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                        command.strip(),
                        address,
                        hex_value,
                        batch_name,
                        has_response,
                        str(retry_count)
                    ])

                    return response_text, len(hex_value), True, hex_value
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 警告: 响应中未提取到有效的十六进制值")
                    has_response = "否"
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 MD命令无响应")
                has_response = "否"
                hex_value = ""

            data_processor.com7_md_response_data.append([
                send_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                command.strip(),
                address,
                "",
                batch_name,
                has_response,
                str(retry_count)
            ])

            return response_text, len(hex_value) if hex_value else 0, has_response == "是", hex_value

        return response_text, 0, True, ""

    except Exception as e:
        error_time = datetime.now().strftime('%H:%M:%S')
        print(f"[{error_time}] COM7 发送命令时出错: {e}")
        return None, 0, False, ""


def send_command_to_com3(ser, command, command_delay, response_timeout,
                         batch_name="", cmd_index=0, total_cmds=0,
                         show_tx_rx=True):
    """
    向COM3发送单个命令并等待响应
    """
    if not command or command.isspace():
        return None, False

    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()

    try:
        ser.reset_input_buffer()
        with serial_utils.com3_receive_lock:
            serial_utils.com3_received_data.clear()

        ser.write(command.encode('utf-8'))
        ser.flush()

        if show_tx_rx:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            print(f"[{timestamp}] COM3 发送{cmd_info}: {command.strip()}")

        response_text = ""
        response_buffer = ""

        time.sleep(command_delay)

        start_time = time.time()
        last_data_time = time.time()

        while time.time() - start_time < response_timeout:
            with serial_utils.com3_receive_lock:
                if serial_utils.com3_received_data:
                    for resp_time, resp_data in serial_utils.com3_received_data:
                        response_buffer += resp_data
                        last_data_time = time.time()

            with serial_utils.com3_receive_lock:
                serial_utils.com3_received_data.clear()

            if not response_buffer and time.time() - last_data_time > 0.5:
                break

            time.sleep(0.1)

        response_text = response_buffer.strip()

        if response_text and show_tx_rx:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 响应: {response_text[:200]}...")

        has_response = "是" if response_text else "否"

        data_processor.com3_response_data.append([
            send_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            command.strip(),
            response_text,
            batch_name,
            has_response
        ])

        return response_text, has_response == "是"

    except Exception as e:
        error_time = datetime.now().strftime('%H:%M:%S')
        print(f"[{error_time}] COM3 发送命令时出错: {e}")
        return None, False


def send_command_to_com7_with_retry(ser, command, command_delay, response_timeout,
                                    batch_name="", cmd_index=0, total_cmds=0,
                                    show_tx_rx=True, is_md_command_flag=False, max_retries=1):
    """
    向COM7发送命令（带重试机制）
    """
    if not is_md_command_flag or max_retries <= 0:
        response, hex_len, is_complete, hex_value = send_command_to_com7(
            ser, command, command_delay, response_timeout,
            batch_name, cmd_index, total_cmds, show_tx_rx, is_md_command_flag, 0
        )
        return response, hex_len, is_complete, hex_value

    best_hex_value = ""
    best_response = None
    best_hex_len = 0
    is_complete = False

    for attempt in range(max_retries + 1):
        response, hex_len, is_complete_attempt, hex_value = send_command_to_com7(
            ser, command, command_delay, response_timeout,
            batch_name, cmd_index, total_cmds, show_tx_rx, is_md_command_flag, attempt
        )

        if hex_value and len(hex_value) >= 8:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试成功获取完整值: {hex_value}")
            best_hex_value = hex_value
            best_response = response
            best_hex_len = hex_len
            is_complete = True
            break
        elif hex_value:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试获得不完整值: {hex_value}")
            if len(hex_value) > len(best_hex_value):
                best_hex_value = hex_value
                best_response = response
                best_hex_len = hex_len
        elif response:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试收到响应: {response[:50]}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试无响应")

        if attempt < max_retries and not is_complete:
            retry_delay = 0.5
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 等待{retry_delay}秒后重试...")
            time.sleep(retry_delay)

    return best_response, best_hex_len, is_complete, best_hex_value


def send_command_batch_com7(ser, batch_commands, batch_name, command_delay, response_timeout, show_tx_rx,
                            retry_count=0):
    """
    向COM7发送一批命令
    """
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 开始发送批次: {batch_name}")
    print(f"批次配置: 命令间延迟={command_delay}s, 响应超时={response_timeout}s, 显示发送接收={show_tx_rx}, 重试次数={retry_count}")

    valid_commands = [cmd for cmd in batch_commands if cmd.strip()]
    print(f"命令总数: {len(valid_commands)} 条")

    md_count = len([cmd for cmd in valid_commands if data_processor.is_md_command(cmd)])
    print(f"其中MD命令: {md_count} 条")
    print(f"{'=' * 60}")

    valid_count = 0
    md_success_count = 0
    md_fail_count = 0

    for i, cmd in enumerate(batch_commands, 1):
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        valid_count += 1
        is_md = data_processor.is_md_command(cmd)

        if is_md and retry_count > 0:
            response, hex_len, is_complete, hex_value = send_command_to_com7_with_retry(
                ser=ser,
                command=cmd,
                command_delay=command_delay,
                response_timeout=response_timeout,
                batch_name=batch_name,
                cmd_index=valid_count,
                total_cmds=len(valid_commands),
                show_tx_rx=show_tx_rx,
                is_md_command_flag=is_md,
                max_retries=retry_count
            )

            if is_complete:
                md_success_count += 1
            else:
                md_fail_count += 1
        else:
            response, hex_len, is_complete, hex_value = send_command_to_com7(
                ser=ser,
                command=cmd,
                command_delay=command_delay,
                response_timeout=response_timeout,
                batch_name=batch_name,
                cmd_index=valid_count,
                total_cmds=len(valid_commands),
                show_tx_rx=show_tx_rx,
                is_md_command_flag=is_md
            )

    print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 批次 {batch_name} 发送完成")
    print(f"  共发送 {valid_count} 条有效命令")
    if md_count > 0:
        print(f"  MD命令: 成功 {md_success_count}/{md_count}, 失败 {md_fail_count}/{md_count}")

    return valid_count


def send_command_batch_com3(ser, batch_commands, batch_name, command_delay, response_timeout, show_tx_rx):
    """
    向COM3发送一批命令
    """
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 开始发送批次: {batch_name}")
    print(f"批次配置: 命令间延迟={command_delay}s, 响应超时={response_timeout}s, 显示发送接收={show_tx_rx}")

    valid_commands = [cmd for cmd in batch_commands if cmd.strip()]
    print(f"命令总数: {len(valid_commands)} 条")
    print(f"{'=' * 60}")

    valid_count = 0
    success_count = 0

    for i, cmd in enumerate(batch_commands, 1):
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        valid_count += 1

        response, is_success = send_command_to_com3(
            ser=ser,
            command=cmd,
            command_delay=command_delay,
            response_timeout=response_timeout,
            batch_name=batch_name,
            cmd_index=valid_count,
            total_cmds=len(valid_commands),
            show_tx_rx=show_tx_rx
        )

        if is_success:
            success_count += 1

    print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 批次 {batch_name} 发送完成")
    print(f"  共发送 {valid_count} 条命令，成功 {success_count} 条")

    return valid_count