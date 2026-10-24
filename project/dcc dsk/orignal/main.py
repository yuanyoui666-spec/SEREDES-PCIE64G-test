import serial
import time
import sys
import os


class SerialCommandExecutor:
    def __init__(self, port, baudrate=115200, timeout=1):
        """
        初始化串口连接
        :param port: 串口端口，如 'COM3' 或 '/dev/ttyUSB0'
        :param baudrate: 波特率，默认为115200
        :param timeout: 超时时间，默认为1秒
        """
        self.port = port
        self.baudrate = baudrate
        self.ser = None

        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout
            )
            print(f"成功连接到串口 {port}, 波特率 {baudrate}")

        except serial.SerialException as e:
            print(f"连接串口失败: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"初始化错误: {e}")
            sys.exit(1)

    def send_command(self, command, wait_time=0.1):
        """
        发送命令并接收响应
        :param command: 要发送的命令字符串
        :param wait_time: 发送后等待时间，默认为0.1秒
        :return: 接收到的响应字符串
        """
        if not self.ser or not self.ser.is_open:
            print("串口未连接")
            return ""

        # 确保命令以换行符结束
        if not command.endswith('\n'):
            command += '\n'

        try:
            # 发送命令
            self.ser.write(command.encode('utf-8', errors='ignore'))
            print(f"发送命令: {command.strip()}")

            # 等待响应
            time.sleep(wait_time)

            # 读取响应
            response = ""
            while self.ser.in_waiting > 0:
                response += self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                time.sleep(0.01)

            if response:
                print(f"收到响应: {response.strip()}")

            return response

        except Exception as e:
            print(f"发送/接收命令时出错: {e}")
            return ""

    def send_commands_from_txt(self, txt_content):
        """
        发送类似你提供的txt文件中的命令序列
        :param txt_content: 包含命令的文本内容
        """
        lines = txt_content.strip().split('\n')
        current_sequence = []
        sequence_name = ""

        for line in lines:
            line = line.strip()

            # 跳过空行
            if not line:
                continue

            # 检测序列开始（如"①常压NV："）
            if line.startswith('①') or line.startswith('②') or line.startswith('③'):
                if current_sequence:
                    print(f"\n{'=' * 50}")
                    print(f"执行 {sequence_name} 命令序列完成")
                    print(f"{'=' * 50}\n")

                sequence_name = line
                current_sequence = []
                print(f"\n{'=' * 50}")
                print(f"开始执行 {sequence_name} 命令序列")
                print(f"{'=' * 50}")
                continue

            # 跳过注释行（stat命令在文档中用于显示状态）
            if line.startswith('#'):
                continue

            # 处理百分比设置命令（如"1v2 10% 0v75 10% 0.75core 10%"）
            if '%' in line and ('1v2' in line or '0v75' in line):
                print(f"\n[配置命令] {line}")
                continue

            # 处理普通命令
            if line:
                current_sequence.append(line)
                response = self.send_command(line)

        # 执行最后一个序列
        if current_sequence:
            print(f"\n{'=' * 50}")
            print(f"执行 {sequence_name} 命令序列完成")
            print(f"{'=' * 50}")

    def execute_voltage_test_sequence(self):
        """
        执行你文档中的完整电压测试序列
        """
        # 定义测试序列
        test_sequences = [
            {
                "name": "① 常压NV模式",
                "commands": [
                    "stat",
                    "addvolt vdd1v2_vph_dc 1.21 0",
                    "addvolt vdd1v2_vph1 1.21 0",
                    "addvolt vdd1v2_vpod 1.21 0",
                    "addvolt vdd0v75_vp 0.76 0",
                    "addvolt vdd0v75_clk 0.76 0",
                    "addvolt vdd0v75_core 0.76 0",
                    "listgrp 0",
                    "setactgrp 0",
                    "coldreset 3",
                    "stat"
                ]
            },
            {
                "name": "② 高压HV模式 (+10%)",
                "note": "1v2 +10%   0v75 +10%   0.75core +10%",
                "commands": [
                    "stat",
                    "addvolt vdd1v2_vph_dc 1.33 0",
                    "addvolt vdd1v2_vph1 1.33 0",
                    "addvolt vdd1v2_vpod 1.33 0",
                    "addvolt vdd0v75_vp 0.835 0",
                    "addvolt vdd0v75_clk 0.835 0",
                    "addvolt vdd0v75_core 0.835 0",
                    "listgrp 0",
                    "setactgrp 0",
                    "coldreset 3",
                    "stat"
                ]
            },
            {
                "name": "③ 低压LV模式 (-10%)",
                "note": "1v2 -10%   0v75 -10%   0.75core -10%",
                "commands": [
                    "stat",
                    "addvolt vdd1v2_vph_dc 1.09 0",
                    "addvolt vdd1v2_vph1 1.09 0",
                    "addvolt vdd1v2_vpod 1.09 0",
                    "addvolt vdd0v75_vp 0.685 0",
                    "addvolt vdd0v75_clk 0.685 0",
                    "addvolt vdd0v75_core 0.685 0",
                    "listgrp 0",
                    "setactgrp 0",
                    "coldreset 3",
                    "stat"
                ]
            }
        ]

        print("\n" + "=" * 60)
        print("开始执行完整电压测试序列")
        print("=" * 60)

        for sequence in test_sequences:
            print(f"\n{'-' * 60}")
            print(f"执行: {sequence['name']}")
            if 'note' in sequence:
                print(f"配置: {sequence['note']}")
            print(f"{'-' * 60}")

            for cmd in sequence['commands']:
                self.send_command(cmd, wait_time=0.2)

        print(f"\n{'=' * 60}")
        print("所有测试序列执行完成")
        print("=" * 60)

    def interactive_mode(self):
        """交互模式，手动输入命令"""
        print("\n进入交互模式，输入命令与串口通信（输入 'exit' 退出）")
        print("输入 'help' 查看可用命令")

        while True:
            try:
                user_input = input("\n>> ").strip()

                if user_input.lower() == 'exit':
                    print("退出交互模式")
                    break
                elif user_input.lower() == 'help':
                    self.show_help()
                elif user_input.lower() == 'test':
                    self.execute_voltage_test_sequence()
                elif user_input.lower() == 'status':
                    response = self.send_command('stat')
                else:
                    self.send_command(user_input)

            except KeyboardInterrupt:
                print("\n\n检测到中断，退出交互模式")
                break
            except Exception as e:
                print(f"错误: {e}")

    def show_help(self):
        """显示帮助信息"""
        help_text = """
可用命令:
  exit     - 退出交互模式
  help     - 显示此帮助信息
  test     - 执行完整的电压测试序列
  status   - 发送 stat 命令查看状态

特殊功能:
  - 脚本支持你文档中的所有命令格式
  - 支持 addvolt, listgrp, setactgrp, coldreset 等命令
  - 支持常压(NV)、高压(HV)、低压(LV)三种模式
        """
        print(help_text)

    def close(self):
        """关闭串口连接"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("串口连接已关闭")


def main():
    """主函数"""
    print("串口指令收发工具")
    print("-" * 40)

    # 获取串口端口
    default_port = "COM3" if sys.platform.startswith('win') else "/dev/ttyUSB0"
    port = input(f"请输入串口端口 (默认为 {default_port}): ").strip()
    if not port:
        port = default_port

    # 创建串口执行器
    executor = SerialCommandExecutor(port=port, baudrate=115200)

    try:
        # 选择模式
        print("\n请选择操作模式:")
        print("1. 执行完整电压测试序列（基于你提供的文档）")
        print("2. 加载并执行txt文件中的命令")
        print("3. 交互模式（手动输入命令）")

        choice = input("请输入选择 (1/2/3, 默认为1): ").strip()

        if choice == '2':
            # 从txt文件加载
            txt_path = input("请输入txt文件路径: ").strip()
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                executor.send_commands_from_txt(content)
            else:
                print(f"文件不存在: {txt_path}")
        elif choice == '3':
            # 交互模式
            executor.interactive_mode()
        else:
            # 执行完整测试序列
            executor.execute_voltage_test_sequence()

    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"程序执行出错: {e}")
    finally:
        executor.close()


if __name__ == "__main__":
    main()