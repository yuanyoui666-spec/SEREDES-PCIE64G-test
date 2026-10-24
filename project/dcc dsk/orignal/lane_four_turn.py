
import serial
import time
import threading
from datetime import datetime
import pandas as pd
import os
import re
import warnings


warnings.filterwarnings('ignore')

# ========== 串口配置 ==========
SERIAL_PORT_COM7 = 'COM7'  # 串口号 - jingyu
SERIAL_PORT_COM3 = 'COM21'  # 串口号 - shell
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 1.0  # 串口读取超时（秒）

# Excel文件保存路径
EXCEL_FILENAME = f"./xlsx/serial_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

# ========== 响应数据存储列表 ==========
com7_md_response_data = []  # COM7的MD命令响应数据
com3_response_data = []  # COM3的响应数据

# ========== 通道配置 ==========
# 只有4个通道（lane0-lane3），每个通道有特定的参数
LANE_CONFIGS = [
    {
        'name': 'lane0',
        'mm_param': '0x00000000',  # 第一个字节为0x01
        'com3_param': '0'  # COM3函数参数
    },
    {
        'name': 'lane1',
        'mm_param': '0x00000001',  # 第一个字节为0x02
        'com3_param': '1'  # COM3函数参数
    },
    {
        'name': 'lane2',
        'mm_param': '0x00000002',  # 第一个字节为0x03
        'com3_param': '2'  # COM3函数参数
    },
    {
        'name': 'lane3',
        'mm_param': '0x00000003',  # 第一个字节为0x04
        'com3_param': '3'  # COM3函数参数
    }
]

# ========== 批次配置 ==========
# 批次1：初始化阶段 - 较长的延迟和超时
BATCH_1_COMMANDS = [
    "phy_init_only",
    "m3_run",
    "",
    "serdes_start_cm 0 3",
    "",
    "echo 基础初始化完成，准备通道测试...",  # 调试信息
]

# 批次1的配置
BATCH_1_DELAY = 0.5  # 初始化阶段命令间延迟
BATCH_1_RESPONSE_TIMEOUT = 3.0  # 初始化阶段响应超时
BATCH_1_SHOW_TX_RX = True  # 批次1显示发送和接收消息

# 批次2的配置
BATCH_2_DELAY = 0.2  # 快速执行阶段命令间延迟
BATCH_2_RESPONSE_TIMEOUT = 2.5  # 快速执行阶段响应超时
BATCH_2_SHOW_TX_RX = False  # 批次2不显示发送和接收消息（除了md命令）
BATCH_2_RETRY_COUNT = 1  # 对MD命令失败时重试次数

# COM3配置
COM3_DELAY = 1.0  # COM3命令间延迟
COM3_RESPONSE_TIMEOUT = 3.0  # COM3响应超时
COM3_SHOW_TX_RX = True  # COM3显示发送和接收消息

# ========== 接收缓冲区 ==========
com7_received_data = []
com3_received_data = []
com7_receive_lock = threading.Lock()
com3_receive_lock = threading.Lock()
stop_receiving = False


# ========== 工具函数 ==========
def setup_serial_port(port_name, baud_rate=BAUD_RATE, timeout=READ_TIMEOUT):
    """
    设置并打开串口
    """
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )

        if ser.is_open:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口 {port_name} 已成功打开，波特率 {baud_rate}")
            return ser
        else:
            print(f"错误: 无法打开串口 {port_name}")
            return None

    except serial.SerialException as e:
        print(f"串口 {port_name} 错误: {e}")
        print(f"请检查: 1) 串口 {port_name} 是否存在 2) 是否有其他程序占用 3) 驱动程序是否正确安装")
        return None
    except Exception as e:
        print(f"串口 {port_name} 未知错误: {e}")
        return None


def receive_data_thread_com7(ser):
    """
    COM7接收串口数据的线程函数
    """
    global stop_receiving

    while not stop_receiving:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    with com7_receive_lock:
                        com7_received_data.append((datetime.now(), decoded_data))

            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7接收数据时出错: {e}")
            break


def receive_data_thread_com3(ser):
    """
    COM3接收串口数据的线程函数
    """
    global stop_receiving

    while not stop_receiving:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    with com3_receive_lock:
                        com3_received_data.append((datetime.now(), decoded_data))

            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3接收数据时出错: {e}")
            break


def clean_special_chars(text):
    """
    清理文本中的特殊字符
    """
    if not text:
        return ""

    cleaned = ''.join(char for char in text if ord(char) >= 32 or char == '\n' or char == '\t')

    # 移除其他可能影响Excel的特殊字符
    for i in range(1, 32):
        if i not in (9, 10, 13):  # 保留制表符、换行符、回车符
            cleaned = cleaned.replace(chr(i), '')

    return cleaned.strip()


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


def extract_hex_value(raw_response):
    """
    从MD命令的原始响应中提取十六进制值
    """
    if not raw_response:
        return ""

    lines = raw_response.strip().split('\n')
    hex_value = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 过滤干扰行
        if line.lower().startswith('md '):
            continue
        if 'display in hex:' in line.lower():
            continue
        if 'jingyu:/' in line.lower() or 'jingyu:/$' in line:
            continue
        if line == '$':
            continue

        # 匹配十六进制值
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                value_part = parts[1].strip()
                hex_pattern = r'[0-9a-fA-F]{8}'
                hex_matches = re.findall(hex_pattern, value_part)

                if hex_matches:
                    hex_value = hex_matches[0]
                    break

    return hex_value


# ========== 命令生成函数 ==========
def generate_batch_commands_for_lane(mm_param, com3_param, lane_index=0):
    """
    为指定通道生成批次命令
    mm_param: mm 0xb0303434 命令的参数
    com3_param: COM3函数的参数
    lane_index: 0=lane0, 1=lane1, 2=lane2, 3=lane3
    """


    # 计算通道掩码
    lane_masks = [0x1, 0x2, 0x4, 0x8]  # lane0-lane3的掩码
    lane_mask = lane_masks[lane_index]

    # 根据lane_index计算地址偏移 (每个lane增加0x400)
    addr_offset = lane_index * 0x400

    # 计算每个受影响的寄存器地址
    addr_204c = 0xb030204c + addr_offset
    addr_2028 = 0xb0302028 + addr_offset
    addr_2010 = 0xb0302010 + addr_offset
    addr_2078 = 0xb0302078 + addr_offset

    # COM3命令保持不变
    com3_commands = [
        f"dump_ssm_cal_result {com3_param}",
        f"dump_rx_dll_Deskew_v2 {com3_param}"
    ]

    # 基础命令模板 - 将所有硬编码地址替换为动态计算的地址
    base_template = [
        f"0. 启用通道lane{lane_index}",
        f"serdes_start_tx 0 0x{lane_mask:x} 5",
        f"serdes_start_rx 0 0x{lane_mask:x} 5",
        "等待通道启用...",
        "",
        "1.",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x02000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        "",
        "2.",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x29000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址 - 这是关键！
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x2a000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址 - 这是关键！
        "3.",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x34000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址 - 这是关键！
        "",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x35000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址 - 这是关键！
        "",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x36000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址 - 这是关键！
        "",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x37000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}"  # 动态地址 - 这是关键！
    ]
    print(f"DEBUG: lane{lane_index} - addr_offset=0x{addr_offset:08x}, addr_2078=0x{addr_2078:08x}")
    return base_template, com3_commands


# ========== 命令发送函数 ==========
def send_command_to_com7(ser, command, command_delay, response_timeout,
                         batch_name="", cmd_index=0, total_cmds=0,
                         show_tx_rx=True, is_md_command_flag=False, retry_count=0):
    """
    向COM7发送单个命令并等待响应
    修复：移除所有硬件检查逻辑
    """
    if not command or command.isspace():
        return None, 0, False, ""

    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()

    try:
        # 【修复】完全移除硬件检查逻辑

        # 1. 清空软件缓冲区（不重置硬件缓冲区）
        time.sleep(0.1)  # 短暂延迟
        with com7_receive_lock:
            com7_received_data.clear()

        # 2. 发送命令
        ser.write(command.encode('utf-8'))
        ser.flush()

        # 显示发送信息
        if show_tx_rx or is_md_command_flag:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            batch_info = f"[{batch_name}] " if batch_name else ""
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            retry_info = f"[重试{retry_count}] " if retry_count > 0 else ""
            print(f"[{timestamp}] COM7 {batch_info}{retry_info}发送{cmd_info}: {command.strip()}")

        # 3. 收集响应
        response_text = ""
        response_buffer = ""

        time.sleep(command_delay)

        start_time = time.time()
        collection_count = 0
        max_collections = 10

        while time.time() - start_time < response_timeout and collection_count < max_collections:
            with com7_receive_lock:
                if com7_received_data:
                    for resp_time, resp_data in com7_received_data:
                        response_buffer += resp_data

            with com7_receive_lock:
                com7_received_data.clear()

            if response_buffer:
                start_time = time.time()  # 有数据，重置超时
            else:
                time.sleep(0.2)

            collection_count += 1

        response_text = response_buffer.strip()

        # 4. 处理MD命令响应
        if is_md_command_flag:
            address = parse_md_address(command.strip())

            if response_text:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 MD命令响应: {response_text[:100]}")

                hex_value = extract_hex_value(response_text)

                if hex_value and len(hex_value) >= 2:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 提取到十六进制值: {hex_value}")
                    has_response = "是"

                    # 保存数据
                    com7_md_response_data.append([
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

            # 即使失败也记录
            com7_md_response_data.append([
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
        with com3_receive_lock:
            com3_received_data.clear()

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
            with com3_receive_lock:
                if com3_received_data:
                    for resp_time, resp_data in com3_received_data:
                        response_buffer += resp_data
                        last_data_time = time.time()

            with com3_receive_lock:
                com3_received_data.clear()

            if not response_buffer and time.time() - last_data_time > 0.5:
                break

            time.sleep(0.1)

        response_text = response_buffer.strip()

        if response_text and show_tx_rx:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 响应: {response_text[:200]}...")

        has_response = "是" if response_text else "否"

        # 保存COM3响应数据（包含通道信息）
        com3_response_data.append([
            send_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            command.strip(),
            response_text,
            batch_name,  # 包含通道信息，如"COM3专用指令[lane0]"
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
    print(
        f"批次配置: 命令间延迟={command_delay}s, 响应超时={response_timeout}s, 显示发送接收={show_tx_rx}, 重试次数={retry_count}")

    valid_commands = [cmd for cmd in batch_commands if cmd.strip()]
    print(f"命令总数: {len(valid_commands)} 条")

    md_count = len([cmd for cmd in valid_commands if is_md_command(cmd)])
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
        is_md = is_md_command(cmd)

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

# ========== 数据保存函数 ==========
def save_responses_to_excel_with_lanes():
    """
    保存多通道响应数据到Excel文件
    支持lane0-lane3四个通道的数据分类保存
    新增：转换后的值列
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
        # 跳过初始化阶段的数据（不包含通道信息）
        if "初始化阶段" in batch and "[" not in batch:
            continue  # 跳过初始化阶段的数据
        if value and has_response == "是":
            # 从批次名称提取通道信息
            lane_name = "lane0"  # 默认

            if "[" in batch and "]" in batch:
                lane_info = batch.split("[")[1].split("]")[0]
                if lane_info.startswith("lane"):
                    lane_name = lane_info
            else:
                # 如果批次名称不包含通道信息，根据记录顺序分配
                total_records = len(com7_md_response_data)
                if total_records > 0:
                    # 假设每个通道有6个MD命令
                    record_index = com7_md_response_data.index(record)
                    lane_index = record_index // 6
                    if lane_index < 4:
                        lane_name = f"lane{lane_index}"

            # 确定这是当前通道的第几个MD命令
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

            # 【新增】提取转换后的值
            converted_value = ""
            if value and len(value) == 8:  # 确保是8位十六进制
                converted_value = extract_data_safe(value)  # 使用安全提取方法
                if converted_value is not None:
                    print(f"转换值: {value} -> {converted_value}")

            # 保存数据：通道, 参数, 值, 转换后的值, 数据类型
            lane_data[lane_name]['md'].append([
                lane_name,  # 通道
                param_name,  # 参数
                value,  # 原始十六进制值
                converted_value,  # 【新增】转换后的值
                f"MD读取"  # 数据类型
            ])

    # 处理COM3的响应数据
    for record in com3_response_data:
        timestamp, cmd, response, batch, has_response = record

        if response and has_response in ["执行成功", "是"]:
            cleaned_response = clean_special_chars(response)

            if cleaned_response:
                lane_name = "lane0"  # 默认

                if "[" in batch and "]" in batch:
                    lane_info = batch.split("[")[1].split("]")[0]
                    if lane_info.startswith("lane"):
                        lane_name = lane_info
                else:
                    # 如果批次名称不包含通道信息，根据记录顺序分配
                    total_records = len(com3_response_data)
                    if total_records > 0:
                        # 假设每个通道有2个COM3命令
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

                # COM3数据没有转换值，所以转换值为空
                lane_data[lane_name]['com3'].append([
                    lane_name,  # 通道
                    param_name,  # 参数
                    cleaned_response[:3500] + ("..." if len(cleaned_response) > 3500 else ""),  # 响应结果
                    "",  # 【新增】转换后的值（COM3数据为空）
                    f"COM3执行"  # 数据类型
                ])

    # 将所有通道的数据按顺序合并
    for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
        for md_record in lane_data[lane_name]['md']:
            channel, param_name, value, converted_value, data_type = md_record
            all_response_data.append([
                channel,  # 通道
                param_name,  # 参数
                value,  # 读取值（十六进制）
                converted_value,  # 【新增】转换后的值
                data_type  # 数据类型
            ])

        for com3_record in lane_data[lane_name]['com3']:
            channel, param_name, response, converted_value, data_type = com3_record
            all_response_data.append([
                channel,  # 通道
                param_name,  # 参数
                response,  # 响应结果
                converted_value,  # 【新增】转换后的值
                data_type  # 数据类型
            ])

    if not all_response_data:
        print("没有有效的响应数据需要保存")
        return

    try:
        # 更新列名，增加"转换后的值"列
        df = pd.DataFrame(all_response_data, columns=[
            '通道',
            '参数',
            '读取值/响应结果',
            '转换后的值',  # 【新增列】
            '数据类型'
        ])

        df.to_excel(EXCEL_FILENAME, index=False, engine='openpyxl')

        print(f"多通道响应数据已保存到: {os.path.abspath(EXCEL_FILENAME)}")
        print(f"共保存 {len(all_response_data)} 条记录")

        # 显示转换后的值统计
        print("\n转换后的值统计:")
        print("=" * 60)
        conversion_count = 0
        for lane_name in ['lane0', 'lane1', 'lane2', 'lane3']:
            lane_conversions = []
            for record in lane_data[lane_name]['md']:
                if record[3] is not None and record[3] != "":  # 检查转换后的值
                    lane_conversions.append(record[3])
            if lane_conversions:
                print(f"  {lane_name}: {len(lane_conversions)} 个转换值: {lane_conversions}")
                conversion_count += len(lane_conversions)
        print(f"总计转换 {conversion_count} 个MD读取值")
        print("=" * 60)

    except Exception as e:
        print(f"保存Excel文件时出错: {e}")
        try:
            csv_filename = EXCEL_FILENAME.replace('.xlsx', '.csv')
            df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
            print(f"数据已保存为CSV文件: {csv_filename}")
        except Exception as e2:
            print(f"保存CSV文件也失败: {e2}")


# ========== 寄存器提取功能 ==========
def extract_bitfield(reg_value, start_bit, length):
    """
    从32位寄存器值中提取指定位域
    :param reg_value: 32位寄存器值（整数）
    :param start_bit: 起始位（从0开始）
    :param length: 位域长度
    :return: 提取的值
    """
    if length == 0 or length > 32:
        return 0
    mask = (1 << length) - 1
    return (reg_value >> start_bit) & mask


def extract_data_from_register(reg_value_str):
    """
    从32位十六进制字符串中提取数据位（11-19位）
    :param reg_value_str: 32位十六进制字符串，如 "3e361a0e"
    :return: 提取的数据值（整数），如果无效返回None
    """
    if not reg_value_str or not isinstance(reg_value_str, str):
        return None

    # 清理字符串
    reg_value_str = reg_value_str.strip().lower()

    # 确保是8位十六进制字符串
    if len(reg_value_str) != 8:
        return None

    try:
        # 转换为整数
        reg_value = int(reg_value_str, 16)

        # 提取数据位（11-19位，共9位）
        data = extract_bitfield(reg_value, 11, 9)

        return data
    except (ValueError, TypeError):
        return None


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

# ========== 主函数 ==========
def main():
    """
    主函数 - 支持4通道测试 (lane0-lane3)
    修正：1. COM7初始化阶段只执行一次
          2. 在每个通道测试前单独启用该通道
    """
    global stop_receiving

    print("=" * 80)
    print("四通道串口通信测试程序")
    print(f"目标串口1: {SERIAL_PORT_COM7}, 波特率: {BAUD_RATE}")
    print(f"目标串口2: {SERIAL_PORT_COM3}, 波特率: {BAUD_RATE}")
    print(f"Excel输出文件: {EXCEL_FILENAME}")
    print(f"测试通道: lane0, lane1, lane2, lane3")
    print("=" * 80)

    # 1. 打开串口
    com7_ser = setup_serial_port(SERIAL_PORT_COM7)
    com3_ser = setup_serial_port(SERIAL_PORT_COM3)

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
        stop_receiving = False
        com7_receiver_thread = threading.Thread(target=receive_data_thread_com7, args=(com7_ser,), daemon=True)
        com3_receiver_thread = threading.Thread(target=receive_data_thread_com3, args=(com3_ser,), daemon=True)

        com7_receiver_thread.start()
        com3_receiver_thread.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动COM7和COM3数据接收线程")

        time.sleep(0.5)

        # 3. 【仅一次】执行COM7初始化阶段
        print(f"\n{'#' * 80}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始COM7初始化阶段")
        print(f"{'#' * 80}")

        com7_batch1_count = send_command_batch_com7(
            ser=com7_ser,
            batch_commands=BATCH_1_COMMANDS,
            batch_name="COM7初始化阶段",  # 注意：这里不包含通道信息
            command_delay=BATCH_1_DELAY,
            response_timeout=BATCH_1_RESPONSE_TIMEOUT,
            show_tx_rx=BATCH_1_SHOW_TX_RX,
            retry_count=0
        )

        # 初始化完成后等待一段时间
        init_complete_delay = 3.0
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7初始化完成，等待 {init_complete_delay} 秒...")
        time.sleep(init_complete_delay)

        # 4. 依次测试4个通道
        total_com7_commands = 0
        total_com3_commands = 0

        for lane_index, lane_config in enumerate(LANE_CONFIGS):  # 修改：使用enumerate获取索引
            lane_name = lane_config['name']
            mm_param = lane_config['mm_param']
            com3_param = lane_config['com3_param']

            print(f"\n{'#' * 80}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始测试通道: {lane_name}")
            print(f"  MM参数: {mm_param}")
            print(f"  COM3参数: {com3_param}")
            print(f"{'#' * 80}")

            # 4.1 先单独启用当前通道
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 启用通道 {lane_name}...")

            # 计算通道掩码
            # lane0: 0x1, lane1: 0x2, lane2: 0x4, lane3: 0x8
            lane_mask = 1 << lane_index  # 通过位运算计算掩码
            # 在启用新通道前，重置之前的通道
            if lane_index > 0:  # 从lane1开始
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 重置之前的通道，准备测试{lane_name}...")

                # 禁用之前的通道
                prev_lane_mask = 1 << (lane_index - 1)
                send_command_to_com7(
                    ser=com7_ser,
                    command=f"serdes_start_tx 0 0x0 5",  # 禁用所有TX
                    command_delay=1.0,
                    response_timeout=3.0,
                    batch_name=f"通道重置[{lane_name}]",
                    show_tx_rx=True
                )

                send_command_to_com7(
                    ser=com7_ser,
                    command=f"serdes_start_rx 0 0x0 5",  # 禁用所有RX
                    command_delay=1.0,
                    response_timeout=3.0,
                    batch_name=f"通道重置[{lane_name}]",
                    show_tx_rx=True
                )

                time.sleep(1.0)  # 等待重置完成
            # 启用当前通道的TX
            send_command_to_com7(
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
            send_command_to_com7(
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

            # 4.2 生成当前通道的快速执行阶段命令
            batch_2_commands, com3_commands = generate_batch_commands_for_lane(mm_param, com3_param, lane_index)


            # 4.3 执行COM7快速执行阶段
            com7_batch2_count = send_command_batch_com7(
                ser=com7_ser,
                batch_commands=batch_2_commands,
                batch_name=f"COM7快速执行阶段[{lane_name}]",  # 包含通道信息
                command_delay=BATCH_2_DELAY,
                response_timeout=BATCH_2_RESPONSE_TIMEOUT,
                show_tx_rx=BATCH_2_SHOW_TX_RX,
                retry_count=BATCH_2_RETRY_COUNT
            )

            # COM7完成后等待
            com7_complete_delay = 2.0
            print(
                f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7 {lane_name} 快速执行阶段完成，等待 {com7_complete_delay} 秒...")
            time.sleep(com7_complete_delay)

            # 4.4 执行COM3指令
            com3_count = send_command_batch_com3(
                ser=com3_ser,
                batch_commands=com3_commands,
                batch_name=f"COM3专用指令[{lane_name}]",  # 包含通道信息
                command_delay=COM3_DELAY,
                response_timeout=COM3_RESPONSE_TIMEOUT,
                show_tx_rx=COM3_SHOW_TX_RX
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
        save_responses_to_excel_with_lanes()

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行完成")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
        save_responses_to_excel_with_lanes()
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行出错: {e}")
        save_responses_to_excel_with_lanes()
    finally:
        # 7. 清理资源
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在清理资源...")
        stop_receiving = True

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