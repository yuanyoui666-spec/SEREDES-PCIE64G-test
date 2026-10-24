import serial
import time
import threading
from datetime import datetime
import pandas as pd
import os
import re
import warnings

warnings.filterwarnings('ignore')

# 串口配置
SERIAL_PORT_COM7 = 'COM7'  # 串口号 - COM7
SERIAL_PORT_COM3 = 'COM3'  # 串口号 - COM3
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 1.0  # 串口读取超时（秒）

# Excel文件保存路径
EXCEL_FILENAME = f"serial_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

# 响应数据存储列表
com7_md_response_data = []  # COM7的MD命令响应数据
com3_response_data = []  # COM3的响应数据

# 批次配置
# 批次1：初始化阶段 - 较长的延迟和超时
BATCH_1_COMMANDS = [
    "phy_init_only",
    "m3_run",
    "",
    "serdes_start_cm 0 3",
    "",
    "serdes_start_tx 0 0x1 5",
    "",
    "serdes_start_rx 0 0x1 5"
]

# COM3专用指令
COM3_COMMANDS = [
    "dump_ssm_cal_result 0",
    "dump_rx_dll_Deskew_v2 0"
]

# 批次1的配置
BATCH_1_DELAY = 0.5  # 初始化阶段命令间延迟
BATCH_1_RESPONSE_TIMEOUT = 3.0  # 初始化阶段响应超时
BATCH_1_SHOW_TX_RX = True  # 批次1显示发送和接收消息

# 批次2：快速执行阶段 - 较短的延迟
BATCH_2_COMMANDS = [
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x02000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x29000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x2a000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x34000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x35000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x36000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x37000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "mm 0xb0300740 0x00000004",
    "mm 0xb0300790 0x000002a1",
    "mm 0xb0300774 0x00000180"
]

# 批次2的配置
BATCH_2_DELAY = 0.2  # 快速执行阶段命令间延迟
BATCH_2_RESPONSE_TIMEOUT = 2.5  # 快速执行阶段响应超时
BATCH_2_SHOW_TX_RX = False  # 批次2不显示发送和接收消息（除了md命令）
BATCH_2_RETRY_COUNT = 1  # 对MD命令失败时重试次数

# COM3配置
COM3_DELAY = 1.0  # COM3命令间延迟
COM3_RESPONSE_TIMEOUT = 3.0  # COM3响应超时
COM3_SHOW_TX_RX = True  # COM3显示发送和接收消息

# 接收缓冲区
com7_received_data = []
com3_received_data = []
com7_receive_lock = threading.Lock()
com3_receive_lock = threading.Lock()
stop_receiving = False


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
                # 读取所有可用数据
                data = ser.read(ser.in_waiting)
                if data:
                    # 尝试以UTF-8解码
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    # 存储接收到的数据
                    with com7_receive_lock:
                        com7_received_data.append((datetime.now(), decoded_data))

            # 短暂休眠避免过高CPU占用
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
                # 读取所有可用数据
                data = ser.read(ser.in_waiting)
                if data:
                    # 尝试以UTF-8解码
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    # 存储接收到的数据
                    with com3_receive_lock:
                        com3_received_data.append((datetime.now(), decoded_data))

            # 短暂休眠避免过高CPU占用
            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3接收数据时出错: {e}")
            break


def save_responses_to_excel():
    """
    保存所有响应数据到Excel文件
    """
    all_response_data = []

    # 添加COM7的MD命令数据
    for record in com7_md_response_data:
        timestamp, cmd, address, value, batch, has_response, retry_count = record
        all_response_data.append([
            timestamp,
            f"COM7: {cmd}",
            address,
            value,
            batch,
            has_response,
            retry_count,
            "COM7"
        ])

    # 添加COM3的响应数据
    for record in com3_response_data:
        timestamp, cmd, response, batch, has_response = record
        all_response_data.append([
            timestamp,
            f"COM3: {cmd}",
            "",
            response[:100] + ("..." if len(response) > 100 else ""),  # 截取前100个字符
            batch,
            has_response,
            "0",
            "COM3"
        ])

    if not all_response_data:
        print("没有响应数据需要保存")
        return

    try:
        # 创建DataFrame
        df = pd.DataFrame(all_response_data, columns=[
            '时间戳',
            '命令',
            '读取地址',  # COM7专用
            '读取值/响应',  # COM7:十六进制值, COM3:响应内容
            '批次',
            '是否有响应',
            '重试次数',
            '串口'
        ])

        # 保存到Excel
        df.to_excel(EXCEL_FILENAME, index=False, engine='openpyxl')

        print(f"响应数据已保存到: {os.path.abspath(EXCEL_FILENAME)}")
        print(f"共保存 {len(all_response_data)} 条记录")
        print(f"  COM7 MD命令: {len(com7_md_response_data)} 条")
        print(f"  COM3 响应: {len(com3_response_data)} 条")

        # 显示保存的数据摘要
        print("\n保存的数据摘要:")

        if com7_md_response_data:
            print("\nCOM7 MD命令摘要:")
            for i, record in enumerate(com7_md_response_data, 1):
                timestamp, cmd, address, value, batch, has_response, retry_count = record
                status = f"✓" if has_response == "是" else f"✗"
                retry_info = f"(重试{retry_count}次)" if int(retry_count) > 0 else ""
                print(f"  {i}. {status} [{timestamp}] 地址: {address} -> 值: {value} {retry_info}")

        if com3_response_data:
            print("\nCOM3 命令摘要:")
            for i, record in enumerate(com3_response_data, 1):
                timestamp, cmd, response, batch, has_response = record
                status = f"✓" if has_response == "是" else f"✗"
                print(f"  {i}. {status} [{timestamp}] 命令: {cmd} -> 响应长度: {len(response)}字符")

    except Exception as e:
        print(f"保存Excel文件时出错: {e}")
        # 尝试简单的保存方法
        try:
            txt_filename = EXCEL_FILENAME.replace('.xlsx', '.txt')
            with open(txt_filename, 'w', encoding='utf-8') as f:
                f.write("时间戳\t命令\t读取地址\t读取值/响应\t批次\t是否有响应\t重试次数\t串口\n")
                for record in all_response_data:
                    f.write("\t".join(record) + "\n")
            print(f"数据已保存为文本文件: {txt_filename}")
        except Exception as e2:
            print(f"保存文本文件也失败: {e2}")


def is_md_command(command):
    """
    判断是否为md开头的命令
    """
    return command.strip().lower().startswith('md')


def parse_md_address(command):
    """
    解析md命令，提取地址参数
    示例: "md 0xb0302078" -> 返回 "0xb0302078"
    """
    if not command or not is_md_command(command):
        return ""

    parts = command.strip().split()
    if len(parts) >= 2:
        return parts[1]  # 返回地址参数
    return ""


def extract_hex_value(raw_response):
    """
    从MD命令的原始响应中提取十六进制值
    改进版：增强对不完整响应的处理
    """
    if not raw_response:
        return ""

    lines = raw_response.strip().split('\n')
    hex_value = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 过滤掉常见的干扰行
        if line.lower().startswith('md '):
            continue
        if 'display in hex:' in line.lower():
            continue
        if 'jingyu:/' in line.lower() or 'jingyu:/$' in line:
            continue
        if line == '$':
            continue

        # 改进的匹配逻辑
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                # 提取十六进制值部分
                value_part = parts[1].strip()
                # 使用正则表达式匹配十六进制值
                hex_pattern = r'[0-9a-fA-F]{8}'  # 匹配8个十六进制字符
                hex_matches = re.findall(hex_pattern, value_part)

                if hex_matches:
                    # 取第一个完整的8字符十六进制值
                    hex_value = hex_matches[0]
                    break
                else:
                    # 如果没有找到完整的8字符值，尝试匹配部分值
                    partial_pattern = r'[0-9a-fA-F]{2,}'  # 匹配至少2个十六进制字符
                    partial_matches = re.findall(partial_pattern, value_part)

                    if partial_matches:
                        # 取最长的部分值
                        longest_match = max(partial_matches, key=len)
                        if len(longest_match) >= 2:
                            hex_value = longest_match
                            # 如果是部分值，可以记录日志
                            if len(hex_value) < 8:
                                return hex_value  # 返回部分值，由上层处理
    return hex_value


def send_command_to_com7_with_improved_response(ser, command, command_delay, response_timeout,
                                                batch_name="", cmd_index=0, total_cmds=0,
                                                show_tx_rx=True, is_md_command_flag=False, retry_count=0):
    """
    向COM7发送单个命令并等待响应
    增强响应检测逻辑
    """
    if not command or command.isspace():
        return None, 0, False

    # 确保命令以换行符结束
    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()

    try:
        # 1. 发送命令前检查硬件状态
        if is_md_command_flag:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 检查硬件状态...")
            # 可以发送一个简单的测试命令检查硬件是否响应
            test_cmd = "echo test\n"
            ser.write(test_cmd.encode('utf-8'))
            ser.flush()
            time.sleep(0.1)

            # 检查是否有响应
            if ser.in_waiting == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 警告: 硬件无响应，可能未正确初始化")

        # 2. 清空接收缓冲区
        ser.reset_input_buffer()
        with com7_receive_lock:
            com7_received_data.clear()

        # 3. 发送命令
        ser.write(command.encode('utf-8'))
        ser.flush()

        # 显示发送信息
        if show_tx_rx or is_md_command_flag:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            batch_info = f"[{batch_name}] " if batch_name else ""
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            retry_info = f"[重试{retry_count}] " if retry_count > 0 else ""
            print(f"[{timestamp}] COM7 {batch_info}{retry_info}发送{cmd_info}: {command.strip()}")

        # 4. 改进的响应收集逻辑
        response_text = ""
        response_buffer = ""

        # 等待基本延迟
        time.sleep(command_delay)

        # 分段收集响应
        start_time = time.time()
        collection_count = 0
        max_collections = 10  # 最多收集10次

        while time.time() - start_time < response_timeout and collection_count < max_collections:
            # 收集数据
            with com7_receive_lock:
                if com7_received_data:
                    for resp_time, resp_data in com7_received_data:
                        response_buffer += resp_data
                        # 显示收到的数据片段用于调试
                        if is_md_command_flag and resp_data.strip():
                            print(f"[{resp_time.strftime('%H:%M:%S.%f')[:-3]}] 收到数据: {resp_data.strip()[:50]}")

            # 清理已处理的数据
            with com7_receive_lock:
                com7_received_data.clear()

            # 如果有数据，延长等待时间
            if response_buffer:
                # 重置超时计数器，继续等待更多数据
                start_time = time.time()
            else:
                # 无数据，增加等待间隔
                time.sleep(0.2)

            collection_count += 1

        response_text = response_buffer.strip()

        # 5. 处理MD命令响应
        if is_md_command_flag:
            # 记录调试信息
            if response_text:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 MD命令响应: {response_text[:100]}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 MD命令无响应")

            # 提取地址参数
            address = parse_md_address(command.strip())

            # 提取十六进制值
            hex_value = extract_hex_value(response_text)
            has_response = "是" if hex_value and len(hex_value) >= 2 else "否"

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

            return response_text, len(hex_value) if hex_value else 0, has_response == "是"

        return response_text, 0, True

    except Exception as e:
        error_time = datetime.now().strftime('%H:%M:%S')
        print(f"[{error_time}] COM7 发送命令时出错: {e}")
        return None, 0, False
def send_command_to_com3(ser, command, command_delay, response_timeout,
                         batch_name="", cmd_index=0, total_cmds=0,
                         show_tx_rx=True):
    """
    向COM3发送单个命令并等待响应
    """
    if not command or command.isspace():
        return None, False

    # 确保命令以换行符结束
    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()

    try:
        # 发送命令前清空接收缓冲区
        ser.reset_input_buffer()  # 清空串口输入缓冲区
        with com3_receive_lock:
            com3_received_data.clear()  # 清空全局接收缓冲区

        # 发送命令
        ser.write(command.encode('utf-8'))
        ser.flush()

        # 显示发送信息
        if show_tx_rx:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            print(f"[{timestamp}] COM3 发送{cmd_info}: {command.strip()}")

        # 响应收集逻辑
        response_text = ""
        response_buffer = ""

        # 等待基本延迟
        time.sleep(command_delay)

        # 分段收集响应
        start_time = time.time()
        last_data_time = time.time()

        while time.time() - start_time < response_timeout:
            # 收集数据
            with com3_receive_lock:
                if com3_received_data:
                    for resp_time, resp_data in com3_received_data:
                        response_buffer += resp_data
                        last_data_time = time.time()  # 更新最后收到数据的时间

            # 清理已处理的数据
            with com3_receive_lock:
                com3_received_data.clear()

            # 如果没有新数据且已经等待了一段时间，尝试结束
            if not response_buffer and time.time() - last_data_time > 0.5:
                break

            time.sleep(0.1)

        response_text = response_buffer.strip()

        # 显示响应
        if response_text and show_tx_rx:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3 响应: {response_text[:200]}...")

        has_response = "是" if response_text else "否"

        # 保存COM3响应数据
        com3_response_data.append([
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
    优化重试策略
    """
    if not is_md_command_flag or max_retries <= 0:
        # 如果不是MD命令或不需要重试，直接发送
        response, hex_len, is_complete = send_command_to_com7_with_improved_response(
            ser, command, command_delay, response_timeout,
            batch_name, cmd_index, total_cmds, show_tx_rx, is_md_command_flag, 0
        )
        return response, hex_len, is_complete

    # 对MD命令进行重试
    for attempt in range(max_retries + 1):
        response, hex_len, is_complete = send_command_to_com7_with_improved_response(
            ser, command, command_delay, response_timeout,
            batch_name, cmd_index, total_cmds, show_tx_rx, is_md_command_flag, attempt
        )

        if response and hex_len >= 8:  # 完整值应该是8个字符
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试成功获取完整值")
            return response, hex_len, True
        elif response:  # 有响应但不是完整值
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试收到响应: {response[:50]}")
            # 如果收到响应但不是十六进制值，可能是错误信息
            if 'error' in response.lower() or 'not found' in response.lower():
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 命令错误: {response}")
                return response, hex_len, False
        elif hex_len > 0 and hex_len < 8:  # 有不完整值
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试获得不完整值，长度: {hex_len}")
        else:  # 无值
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 第{attempt + 1}次尝试无响应")

        # 如果不是最后一次尝试，等待后重试
        if attempt < max_retries:
            retry_delay = 0.5  # 重试延迟
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7 等待{retry_delay}秒后重试...")
            time.sleep(retry_delay)

    return response, hex_len, is_complete

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

    # 统计MD命令数量
    md_count = len([cmd for cmd in valid_commands if is_md_command(cmd)])
    print(f"其中MD命令: {md_count} 条")
    print(f"{'=' * 60}")

    valid_count = 0
    md_success_count = 0
    md_fail_count = 0

    for i, cmd in enumerate(batch_commands, 1):
        # 空行只做延迟，不发送
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        valid_count += 1
        is_md = is_md_command(cmd)

        # 发送命令（MD命令带重试机制）
        if is_md and retry_count > 0:
            response, hex_len, is_complete = send_command_to_com7_with_retry(
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
            # 非MD命令或不需要重试的命令
            response, hex_len, is_complete = send_command_to_com7_with_improved_response(
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
        # 空行只做延迟，不发送
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        valid_count += 1

        # 发送命令
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


def main():
    """
    主函数
    修改执行顺序：先执行COM7，再执行COM3
    """
    global stop_receiving

    print("=" * 80)
    print("双串口通信程序 - 分批次配置延迟参数")
    print(f"目标串口1: {SERIAL_PORT_COM7}, 波特率: {BAUD_RATE}")
    print(f"目标串口2: {SERIAL_PORT_COM3}, 波特率: {BAUD_RATE}")
    print(f"Excel输出文件: {EXCEL_FILENAME}")
    print("=" * 80)
    print("执行顺序：先执行COM7全部指令，再执行COM3指令")
    print("COM7 批次配置详情:")
    print(f"1. 初始化阶段: 命令数={len([c for c in BATCH_1_COMMANDS if c.strip()])}条, "
          f"延迟={BATCH_1_DELAY}s, 超时={BATCH_1_RESPONSE_TIMEOUT}s, 显示发送接收={BATCH_1_SHOW_TX_RX}")
    print(f"2. 快速执行阶段: 命令数={len([c for c in BATCH_2_COMMANDS if c.strip()])}条, "
          f"延迟={BATCH_2_DELAY}s, 超时={BATCH_2_RESPONSE_TIMEOUT}s, 显示发送接收={BATCH_2_SHOW_TX_RX}")
    print(f"  重试次数: {BATCH_2_RETRY_COUNT} 次")
    print(f"COM3 批次配置:")
    print(f"  专用指令: 命令数={len(COM3_COMMANDS)}条, "
          f"延迟={COM3_DELAY}s, 超时={COM3_RESPONSE_TIMEOUT}s, 显示发送接收={COM3_SHOW_TX_RX}")
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

        # 等待接收线程启动
        time.sleep(0.5)

        # 3. 先发送COM7批次1：初始化阶段
        com7_batch1_count = send_command_batch_com7(
            ser=com7_ser,
            batch_commands=BATCH_1_COMMANDS,
            batch_name="COM7初始化阶段",
            command_delay=BATCH_1_DELAY,
            response_timeout=BATCH_1_RESPONSE_TIMEOUT,
            show_tx_rx=BATCH_1_SHOW_TX_RX,
            retry_count=0
        )

        # COM7批次间额外等待
        batch_interval = 1.0
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7批次间等待 {batch_interval} 秒...")
        time.sleep(batch_interval)

        # 4. 发送COM7批次2：快速执行阶段
        com7_batch2_count = send_command_batch_com7(
            ser=com7_ser,
            batch_commands=BATCH_2_COMMANDS,
            batch_name="COM7快速执行阶段",
            command_delay=BATCH_2_DELAY,
            response_timeout=BATCH_2_RESPONSE_TIMEOUT,
            show_tx_rx=BATCH_2_SHOW_TX_RX,
            retry_count=BATCH_2_RETRY_COUNT
        )

        # COM7完成后等待一段时间
        com7_complete_delay = 2.0
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COM7全部指令发送完成，等待 {com7_complete_delay} 秒...")
        time.sleep(com7_complete_delay)

        # 5. 再发送COM3指令
        com3_count = send_command_batch_com3(
            ser=com3_ser,
            batch_commands=COM3_COMMANDS,
            batch_name="COM3专用指令",
            command_delay=COM3_DELAY,
            response_timeout=COM3_RESPONSE_TIMEOUT,
            show_tx_rx=COM3_SHOW_TX_RX
        )

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有批次指令发送完成")
        print(f"COM7批次1发送: {com7_batch1_count} 条命令")
        print(f"COM7批次2发送: {com7_batch2_count} 条命令")
        print(f"COM3 发送: {com3_count} 条命令")
        print(f"总计发送: {com7_batch1_count + com7_batch2_count + com3_count} 条命令")

        # 6. 等待最终响应
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待额外响应...")
        time.sleep(1.0)

        # 7. 保存所有数据到Excel
        save_responses_to_excel()

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行完成")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
        save_responses_to_excel()
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行出错: {e}")
        save_responses_to_excel()
    finally:
        # 8. 清理资源
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