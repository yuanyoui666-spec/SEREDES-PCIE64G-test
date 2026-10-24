import serial
import time
import threading
from datetime import datetime
import pandas as pd
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
import warnings

warnings.filterwarnings('ignore')

# 串口配置
SERIAL_PORT = 'COM7'  # 串口号
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 3.0  # 串口读取超时（秒）

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
BATCH_2_DELAY = 0.1  # 快速执行阶段命令间延迟
BATCH_2_RESPONSE_TIMEOUT = 1.0  # 快速执行阶段响应超时
BATCH_2_SHOW_TX_RX = False  # 批次2不显示发送和接收消息（除了md命令）

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
                    with receive_lock:
                        received_data.append((datetime.now(), decoded_data))

            # 短暂休眠避免过高CPU占用
            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 接收数据时出错: {e}")
            break


def save_md_responses_to_excel():
    """
    保存MD命令响应数据到Excel文件
    """
    if not md_response_data:
        print("没有MD命令响应数据需要保存")
        return

    try:
        # 创建DataFrame
        df = pd.DataFrame(md_response_data, columns=[
            '时间戳',
            'MD命令',
            '响应内容',
            '批次',
            '是否有响应'
        ])

        # 保存到Excel
        df.to_excel(EXCEL_FILENAME, index=False, engine='openpyxl')

        print(f"MD命令响应数据已保存到: {os.path.abspath(EXCEL_FILENAME)}")
        print(f"共保存 {len(md_response_data)} 条MD命令记录")

        # 显示保存的数据摘要
        print("\n保存的MD命令摘要:")
        for i, record in enumerate(md_response_data, 1):
            timestamp, cmd, response, batch, has_response = record
            print(f"{i}. [{timestamp}] {cmd} - 响应: {response[:50]}{'...' if len(response) > 50 else ''}")

    except Exception as e:
        print(f"保存Excel文件时出错: {e}")
        # 尝试简单的保存方法
        try:
            with open(EXCEL_FILENAME.replace('.xlsx', '.txt'), 'w', encoding='utf-8') as f:
                f.write("时间戳\tMD命令\t响应内容\t批次\t是否有响应\n")
                for record in md_response_data:
                    f.write("\t".join(record) + "\n")
            print(f"数据已保存为文本文件: {EXCEL_FILENAME.replace('.xlsx', '.txt')}")
        except Exception as e2:
            print(f"保存文本文件也失败: {e2}")


def is_md_command(command):
    """
    判断是否为md开头的命令
    """
    return command.strip().lower().startswith('md')


def extract_md_response(raw_response):
    """
    从原始响应中提取有效的MD响应数据
    过滤掉命令回显和提示符
    """
    if not raw_response:
        return ""

    lines = raw_response.strip().split('\n')
    filtered_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 过滤掉常见的干扰行
        if line.lower().startswith('md '):
            continue
        if 'jingyu:/' in line or 'jingyu:/$' in line:
            continue
        if line == '$':
            continue
        filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def send_command_with_params(ser, command, command_delay, response_timeout,
                             batch_name="", cmd_index=0, total_cmds=0,
                             show_tx_rx=True, is_md_command_flag=False):
    """
    发送单个命令并等待响应
    """
    if not command or command.isspace():
        return None

    # 确保命令以换行符结束
    if not command.endswith('\n'):
        command = command + '\n'

    send_time = datetime.now()
    responses = []

    try:
        # 发送命令
        ser.write(command.encode('utf-8'))
        ser.flush()

        # 显示发送信息（根据配置）
        if show_tx_rx or is_md_command_flag:
            timestamp = send_time.strftime('%H:%M:%S.%f')[:-3]
            batch_info = f"[{batch_name}] " if batch_name else ""
            cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
            print(f"[{timestamp}] {batch_info}发送{cmd_info}: {command.strip()}")

        # 等待响应
        time.sleep(command_delay)

        # 收集响应
        start_time = time.time()
        while time.time() - start_time < response_timeout:
            with receive_lock:
                if received_data:
                    for timestamp, data in received_data:
                        responses.append((timestamp, data))
                    received_data.clear()
            time.sleep(0.05)

        # 处理响应
        response_text = ""
        if responses:
            # 合并所有响应
            response_parts = []
            for resp_time, resp_data in responses:
                response_parts.append(resp_data.strip())
            response_text = "\n".join(filter(None, response_parts))

            # 显示响应（md命令或配置为显示时）
            if is_md_command_flag or (show_tx_rx and response_text):
                for resp_time, resp_data in responses:
                    if resp_data.strip():
                        timestamp = resp_time.strftime('%H:%M:%S.%f')[:-3]
                        print(f"[{timestamp}] 响应: {resp_data.strip()}")

            # 如果是MD命令，保存到数据列表
            if is_md_command_flag:
                cleaned_response = extract_md_response(response_text)
                has_response = "是" if cleaned_response else "否"

                md_response_data.append([
                    send_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    command.strip(),
                    cleaned_response,
                    batch_name,
                    has_response
                ])

            return response_text

        else:
            if show_tx_rx or is_md_command_flag:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] 警告: 命令 '{command.strip()}' 未收到响应 (超时: {response_timeout}s)")

            # 如果是MD命令，保存无响应的情况
            if is_md_command_flag:
                md_response_data.append([
                    send_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    command.strip(),
                    "无响应",
                    batch_name,
                    "否"
                ])

            return None

    except Exception as e:
        error_time = datetime.now().strftime('%H:%M:%S')
        print(f"[{error_time}] 发送命令时出错: {e}")
        return None


def send_command_batch(ser, batch_commands, batch_name, command_delay, response_timeout, show_tx_rx):
    """
    发送一批命令
    """
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始发送批次: {batch_name}")
    print(f"批次配置: 命令间延迟={command_delay}s, 响应超时={response_timeout}s, 显示发送接收={show_tx_rx}")

    valid_commands = [cmd for cmd in batch_commands if cmd.strip()]
    print(f"命令总数: {len(valid_commands)} 条")

    # 统计MD命令数量
    md_count = len([cmd for cmd in valid_commands if is_md_command(cmd)])
    print(f"其中MD命令: {md_count} 条")
    print(f"{'=' * 60}")

    valid_count = 0
    for i, cmd in enumerate(batch_commands, 1):
        # 空行只做延迟，不发送
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        valid_count += 1
        is_md = is_md_command(cmd)

        # 发送命令
        response = send_command_with_params(
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

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 批次 {batch_name} 发送完成，共发送 {valid_count} 条有效命令")
    return valid_count


def main():
    """
    主函数
    """
    global stop_receiving

    print("=" * 80)
    print("串口通信程序 - 分批次配置延迟参数")
    print(f"目标串口: {SERIAL_PORT}, 波特率: {BAUD_RATE}")
    print(f"Excel输出文件: {EXCEL_FILENAME}")
    print("=" * 80)
    print("批次配置详情:")
    print(f"1. 初始化阶段: 命令数={len([c for c in BATCH_1_COMMANDS if c.strip()])}条, "
          f"延迟={BATCH_1_DELAY}s, 超时={BATCH_1_RESPONSE_TIMEOUT}s, 显示发送接收={BATCH_1_SHOW_TX_RX}")
    print(f"2. 快速执行阶段: 命令数={len([c for c in BATCH_2_COMMANDS if c.strip()])}条, "
          f"延迟={BATCH_2_DELAY}s, 超时={BATCH_2_RESPONSE_TIMEOUT}s, 显示发送接收={BATCH_2_SHOW_TX_RX}")
    print("   * 快速执行阶段只显示md命令的发送和响应")
    print("   * 只保存md命令的响应数据到Excel文件")
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
            show_tx_rx=BATCH_1_SHOW_TX_RX
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
            show_tx_rx=BATCH_2_SHOW_TX_RX
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