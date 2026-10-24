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
SERIAL_PORT = 'COM7'  # 串口号
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 1.0  # 串口读取超时（秒）

# Excel文件保存路径
EXCEL_FILENAME = f"md_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

# MD命令响应数据存储列表
md_response_data = []

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

# 批次1的配置
BATCH_1_DELAY = 0.5  # 初始化阶段命令间延迟
BATCH_1_RESPONSE_TIMEOUT = 3.0  # 初始化阶段响应超时
BATCH_1_SHOW_TX_RX = True  # 批次1显示发送和接收消息

# 批次2：快速执行阶段 - 较短的延迟
BATCH_2_COMMANDS = [
    "1.",
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x02000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "",
    "2.",
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
    "3.",
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x34000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "",
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x35000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "",
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x36000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078",  # MD命令 - 需要显示响应
    "",
    "mm 0xb0303434 0x00000000",
    "mm 0xb0303438 0x37000000",
    "mm 0xb030341c 0x00000008",
    "mm 0xb030204c 0x0000019e",
    "mm 0xb0302028 0x000009c0",
    "mm 0xb0302010 0x00000040",
    "mm 0xb0302028 0x00000840",
    "mm 0xb0302010 0x00000040",
    "md 0xb0302078"  # MD命令 - 需要显示响应
]

# 批次2的配置
BATCH_2_DELAY = 0.2  # 快速执行阶段命令间延迟（增加为0.2秒）
BATCH_2_RESPONSE_TIMEOUT = 2.5  # 快速执行阶段响应超时（增加到2.5秒）
BATCH_2_SHOW_TX_RX = False  # 批次2不显示发送和接收消息（除了md命令）
BATCH_2_RETRY_COUNT = 1  # 对MD命令失败时重试次数

# 接收缓冲区
received_data = []
receive_lock = threading.Lock()
stop_receiving = False


def setup_serial_port():
    """
    设置并打开串口
    """
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=READ_TIMEOUT
        )

        if ser.is_open:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口 {SERIAL_PORT} 已成功打开，波特率 {BAUD_RATE}")
            return ser
        else:
            print(f"错误: 无法打开串口 {SERIAL_PORT}")
            return None

    except serial.SerialException as e:
        print(f"串口错误: {e}")
        print(f"请检查: 1) 串口 {SERIAL_PORT} 是否存在 2) 是否有其他程序占用 3) 驱动程序是否正确安装")
        return None
    except Exception as e:
        print(f"未知错误: {e}")
        return None


def receive_data_thread(ser):
    """
    接收串口数据的线程函数
    修复时间戳问题
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

                    # 使用当前时间戳，避免时间错乱
                    current_time = datetime.now()

                    # 存储接收到的数据
                    with receive_lock:
                        received_data.append((current_time, decoded_data))

            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 接收数据时出错: {e}")
            break

def save_md_responses_to_excel():
    """
    保存MD命令响应数据到Excel文件
    包含命令、地址参数和读取的十六进制值
    """
    if not md_response_data:
        print("没有MD命令响应数据需要保存")
        return

    try:
        # 创建DataFrame
        df = pd.DataFrame(md_response_data, columns=[
            '时间戳',
            'MD命令',
            '读取地址',  # 新增：地址参数
            '读取值',  # 新增：十六进制值
            '批次',
            '是否有响应',
            '重试次数'  # 新增：记录重试次数
        ])

        # 保存到Excel
        df.to_excel(EXCEL_FILENAME, index=False, engine='openpyxl')

        print(f"MD命令响应数据已保存到: {os.path.abspath(EXCEL_FILENAME)}")
        print(f"共保存 {len(md_response_data)} 条MD命令记录")

        # 显示保存的数据摘要
        print("\n保存的MD命令摘要:")
        for i, record in enumerate(md_response_data, 1):
            timestamp, cmd, address, value, batch, has_response, retry_count = record
            status = f"✓" if has_response == "是" else f"✗"
            retry_info = f"(重试{retry_count}次)" if int(retry_count) > 0 else ""
            print(f"{i}. {status} [{timestamp}] 地址: {address} -> 值: {value} {retry_info}")

    except Exception as e:
        print(f"保存Excel文件时出错: {e}")
        # 尝试简单的保存方法
        try:
            txt_filename = EXCEL_FILENAME.replace('.xlsx', '.txt')
            with open(txt_filename, 'w', encoding='utf-8') as f:
                f.write("时间戳\tMD命令\t读取地址\t读取值\t批次\t是否有响应\t重试次数\n")
                for record in md_response_data:
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


def send_command_with_improved_response(ser, command, command_delay, response_timeout,
                                        batch_name="", cmd_index=0, total_cmds=0,
                                        show_tx_rx=True, is_md_command_flag=False, retry_count=0):
    """
    发送单个命令并等待响应（改进版）
    修复数据污染问题
    """
    if not command or command.isspace():
        return None, 0, False

    # 确保命令以换行符结束
    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()

    try:
        # 1. 发送命令前清空接收缓冲区
        ser.reset_input_buffer()  # 清空串口输入缓冲区
        with receive_lock:
            received_data.clear()  # 清空全局接收缓冲区

        # 2. 发送命令
        ser.write(command.encode('utf-8'))
        ser.flush()

        # 显示发送信息
        if show_tx_rx or is_md_command_flag:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            batch_info = f"[{batch_name}] " if batch_name else ""
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            retry_info = f"[重试{retry_count}] " if retry_count > 0 else ""
            print(f"[{timestamp}] {batch_info}{retry_info}发送{cmd_info}: {command.strip()}")

        # 3. 改进的响应收集逻辑
        response_text = ""
        response_buffer = ""

        # 等待基本延迟
        time.sleep(command_delay)

        # 分段收集响应
        start_time = time.time()
        last_data_time = time.time()

        while time.time() - start_time < response_timeout:
            # 收集数据
            with receive_lock:
                if received_data:
                    for resp_time, resp_data in received_data:
                        response_buffer += resp_data
                        last_data_time = time.time()  # 更新最后收到数据的时间
            received_data.clear()  # 清理已处理的数据

            # 如果没有新数据且已经等待了一段时间，尝试结束
            if not response_buffer and time.time() - last_data_time > 0.5:
                break

            time.sleep(0.1)

        response_text = response_buffer.strip()

        # 4. 处理MD命令响应
        if is_md_command_flag:
            # 提取地址参数
            address = parse_md_address(command.strip())

            # 调试：显示原始响应
            if response_text:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 原始响应: {response_text[:100]}...")

            # 改进的十六进制值提取
            hex_value = ""
            if response_text:
                # 查找特定模式的响应
                lines = response_text.split('\n')
                for i, line in enumerate(lines):
                    line = line.strip()
                    # 查找包含MD命令地址的响应行
                    if 'b0302070:' in line.lower() and ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            # 提取十六进制值
                            value_part = parts[1].strip()
                            hex_pattern = r'[0-9a-fA-F]{8}'
                            hex_matches = re.findall(hex_pattern, value_part)
                            if hex_matches:
                                hex_value = hex_matches[0]
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] 从行中找到十六进制值: {hex_value}")
                                break
                else:
                    # 如果没有找到，尝试通用提取
                    hex_value = extract_hex_value(response_text)
                    if hex_value:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 通用提取到十六进制值: {hex_value}")

            has_response = "是" if hex_value and len(hex_value) >= 2 else "否"

            # 保存数据
            md_response_data.append([
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
        print(f"[{error_time}] 发送命令时出错: {e}")
        return None, 0, False


def send_command_with_retry(ser, command, command_delay, response_timeout,
                            batch_name="", cmd_index=0, total_cmds=0,
                            show_tx_rx=True, is_md_command_flag=False, max_retries=1):
    """
    带重试机制的发送命令函数
    对MD命令失败时进行重试
    """
    if not is_md_command_flag or max_retries <= 0:
        # 如果不是MD命令或不需要重试，直接发送
        response, hex_len, is_complete = send_command_with_improved_response(
            ser, command, command_delay, response_timeout,
            batch_name, cmd_index, total_cmds, show_tx_rx, is_md_command_flag, 0
        )
        return response, hex_len, is_complete

    # 对MD命令进行重试
    for attempt in range(max_retries + 1):
        response, hex_len, is_complete = send_command_with_improved_response(
            ser, command, command_delay, response_timeout,
            batch_name, cmd_index, total_cmds, show_tx_rx, is_md_command_flag, attempt
        )

        if response and hex_len >= 8:  # 完整值应该是8个字符
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 第{attempt + 1}次尝试成功获取完整值")
            return response, hex_len, True
        elif hex_len > 0 and hex_len < 8:  # 有不完整值
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 第{attempt + 1}次尝试获得不完整值，长度: {hex_len}")
        else:  # 无值
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 第{attempt + 1}次尝试无响应")

        # 如果不是最后一次尝试，等待后重试
        if attempt < max_retries:
            retry_delay = 0.5  # 重试延迟
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待{retry_delay}秒后重试...")
            time.sleep(retry_delay)

    return response, hex_len, is_complete


def send_command_batch(ser, batch_commands, batch_name, command_delay, response_timeout, show_tx_rx, retry_count=0):
    """
    发送一批命令
    """
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始发送批次: {batch_name}")
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
            response, hex_len, is_complete = send_command_with_retry(
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
            response, hex_len, is_complete = send_command_with_improved_response(
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

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 批次 {batch_name} 发送完成")
    print(f"  共发送 {valid_count} 条有效命令")
    if md_count > 0:
        print(f"  MD命令: 成功 {md_success_count}/{md_count}, 失败 {md_fail_count}/{md_count}")

    return valid_count


def main():
    """
    主函数
    """
    global stop_receiving

    print("=" * 80)
    print("串口通信程序 - 分批次配置延迟参数（改进版）")
    print(f"目标串口: {SERIAL_PORT}, 波特率: {BAUD_RATE}")
    print(f"Excel输出文件: {EXCEL_FILENAME}")
    print("=" * 80)
    print("批次配置详情:")
    print(f"1. 初始化阶段: 命令数={len([c for c in BATCH_1_COMMANDS if c.strip()])}条, "
          f"延迟={BATCH_1_DELAY}s, 超时={BATCH_1_RESPONSE_TIMEOUT}s, 显示发送接收={BATCH_1_SHOW_TX_RX}")
    print(f"2. 快速执行阶段: 命令数={len([c for c in BATCH_2_COMMANDS if c.strip()])}条, "
          f"延迟={BATCH_2_DELAY}s, 超时={BATCH_2_RESPONSE_TIMEOUT}s, 显示发送接收={BATCH_2_SHOW_TX_RX}")
    print(f"  重试次数: {BATCH_2_RETRY_COUNT} 次")
    print("   * 快速执行阶段只显示md命令的发送和响应")
    print("   * 只保存md命令的响应数据到Excel文件")
    print("   * 提取地址参数和十六进制值")
    print("   * 对MD命令失败时进行重试")
    print("=" * 80)

    # 1. 打开串口
    ser = setup_serial_port()
    if not ser:
        print("程序退出")
        return

    receiver_thread = None

    try:
        # 2. 启动接收线程
        stop_receiving = False
        receiver_thread = threading.Thread(target=receive_data_thread, args=(ser,), daemon=True)
        receiver_thread.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动数据接收线程")

        # 等待接收线程启动
        time.sleep(0.5)

        # 3. 发送批次1：初始化阶段
        batch1_count = send_command_batch(
            ser=ser,
            batch_commands=BATCH_1_COMMANDS,
            batch_name="初始化阶段",
            command_delay=BATCH_1_DELAY,
            response_timeout=BATCH_1_RESPONSE_TIMEOUT,
            show_tx_rx=BATCH_1_SHOW_TX_RX,
            retry_count=0
        )

        # 批次间额外等待
        batch_interval = 1.0
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 批次间等待 {batch_interval} 秒...")
        time.sleep(batch_interval)

        # 4. 发送批次2：快速执行阶段
        batch2_count = send_command_batch(
            ser=ser,
            batch_commands=BATCH_2_COMMANDS,
            batch_name="快速执行阶段",
            command_delay=BATCH_2_DELAY,
            response_timeout=BATCH_2_RESPONSE_TIMEOUT,
            show_tx_rx=BATCH_2_SHOW_TX_RX,
            retry_count=BATCH_2_RETRY_COUNT
        )

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有批次指令发送完成")
        print(f"批次1发送: {batch1_count} 条命令")
        print(f"批次2发送: {batch2_count} 条命令")
        print(f"总计发送: {batch1_count + batch2_count} 条命令")

        # 5. 等待最终响应
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待额外响应...")
        time.sleep(1.0)

        # 6. 保存MD命令数据到Excel
        save_md_responses_to_excel()

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行完成")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
        if md_response_data:
            save_md_responses_to_excel()
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行出错: {e}")
        if md_response_data:
            save_md_responses_to_excel()
    finally:
        # 7. 清理资源
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在清理资源...")
        stop_receiving = True

        if receiver_thread and receiver_thread.is_alive():
            receiver_thread.join(timeout=1.0)

        if ser and ser.is_open:
            ser.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口已关闭")

        print("程序结束")


if __name__ == "__main__":
    main()