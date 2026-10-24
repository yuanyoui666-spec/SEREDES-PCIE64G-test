import socket
import sys
import pyvisa


def diagnose_connection():
    """诊断网络连接"""
    addresses = [
        ("172.17.17.187", 5025),  # 默认VISA TCP/IP端口
        ("172.17.17.187", 3490),  # 备选VXI-11端口
        ("172.17.17.108", 5025),
        ("172.17.17.108", 3490)
    ]

    print("网络连接诊断:")
    print("=" * 50)

    for ip, port in addresses:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, port))
            if result == 0:
                print(f"✓ {ip}:{port} 端口开放")
            else:
                print(f"✗ {ip}:{port} 端口关闭")
            sock.close()
        except Exception as e:
            print(f"✗ {ip}:{port} 连接错误: {e}")


def test_ping():
    """测试Ping连接"""
    import subprocess

    ips = ["172.17.17.187", "172.17.17.108"]
    for ip in ips:
        try:
            result = subprocess.run(["ping", "-n", "2", ip],
                                    capture_output=True, text=True, timeout=3)
            if "TTL=" in result.stdout or "time=" in result.stdout:
                print(f"✓ {ip} 可Ping通")
            else:
                print(f"✗ {ip} 不可Ping通")
        except:
            print(f"✗ {ip} Ping测试失败")


def list_visa_resources():
    """列出所有可用的VISA资源"""
    print("\n扫描VISA资源:")
    print("=" * 50)

    try:
        # 使用@py后端
        rm = pyvisa.ResourceManager('@py')
        resources = rm.list_resources()

        if not resources:
            print("未找到任何VISA资源")
        else:
            print(f"找到 {len(resources)} 个VISA资源:")
            for i, resource in enumerate(resources, 1):
                print(f"{i}. {resource}")

        rm.close()
        return resources
    except Exception as e:
        print(f"VISA资源扫描失败: {e}")
        return []






# 运行诊断
# if __name__ == "__main__":
#     # 运行扫描
#     list_visa_resources()
#     #diagnose_connection()
#     #test_ping()

# -*- coding: utf-8 -*-
import pyvisa
import socket
import time
import sys
from typing import Optional, List


class MultimeterReader:
    """万用表读取器 - 健壮版本"""

    def __init__(self, use_py_backend=True):
        self.resource_manager = None
        self.use_py_backend = use_py_backend

    def initialize(self) -> bool:
        """初始化VISA资源管理器"""
        try:
            if self.use_py_backend:
                self.resource_manager = pyvisa.ResourceManager('@py')
            else:
                self.resource_manager = pyvisa.ResourceManager()
            print(f"✓ VISA资源管理器初始化成功")
            return True
        except Exception as e:
            print(f"✗ VISA资源管理器初始化失败: {e}")
            return False

    def discover_devices(self) -> List[str]:
        """发现网络上的万用表设备"""
        print("\n扫描网络设备...")
        print("=" * 50)

        # 常见Keysight设备的IP段
        ip_base = "172.17.17."
        devices = []

        for i in range(1, 255):
            ip = f"{ip_base}{i}"
            if i in [187, 108]:  # 已知设备
                continue

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                result = sock.connect_ex((ip, 5025))
                if result == 0:
                    print(f"发现设备: {ip}:5025")
                    devices.append(ip)
                sock.close()
            except:
                pass

        return devices

    def test_connection_methods(self, ip: str) -> Optional[str]:
        """测试多种连接方法"""
        test_methods = [
            # (visa_address, description)
            (f"TCPIP0::{ip}::inst0::INSTR", "标准VISA格式"),
            (f"TCPIP0::{ip}::5025::SOCKET", "Socket格式"),
            (f"TCPIP::{ip}::inst0::INSTR", "无编号格式"),
            (f"TCPIP0::{ip}", "简化格式"),
        ]

        for visa_addr, desc in test_methods:
            try:
                print(f"尝试: {desc} ({visa_addr})")
                inst = self.resource_manager.open_resource(visa_addr)
                inst.timeout = 3000

                # 测试连接
                idn = inst.query("*IDN?").strip()
                print(f"  ✓ 成功! 设备: {idn}")

                inst.close()
                return visa_addr
            except Exception as e:
                print(f"  ✗ 失败: {str(e)[:80]}")

        return None

    def read_voltage(self, visa_address: str) -> Optional[float]:
        """读取直流电压"""
        try:
            inst = self.resource_manager.open_resource(visa_address)
            inst.timeout = 5000

            # 配置为直流电压测量
            inst.write("CONF:VOLT:DC")
            time.sleep(0.5)  # 等待稳定

            # 读取测量值
            voltage_str = inst.query("READ?").strip()
            voltage = float(voltage_str)

            inst.close()
            return voltage

        except Exception as e:
            print(f"读取电压失败 {visa_address}: {e}")
            return None

    def cleanup(self):
        """清理资源"""
        if self.resource_manager:
            self.resource_manager.close()


# ==================== 主程序 ====================
if __name__ == "__main__":
    print("Keysight 34470A 万用表读取程序")
    print("=" * 50)

    # 创建读取器实例
    reader = MultimeterReader(use_py_backend=True)

    # 初始化VISA
    if not reader.initialize():
        print("尝试使用默认后端...")
        reader = MultimeterReader(use_py_backend=False)
        if not reader.initialize():
            print("无法初始化VISA，程序退出")
            sys.exit(1)

    try:
        # 已知设备IP
        known_ips = ["172.17.17.187", "172.17.17.108"]

        for ip in known_ips:
            print(f"\n处理设备: {ip}")
            print("-" * 30)

            # 1. 测试网络连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, 5025))
            sock.close()

            if result != 0:
                print(f"✗ 网络连接失败 (端口5025关闭)")
                continue

            # 2. 测试VISA连接
            visa_address = reader.test_connection_methods(ip)

            if visa_address:
                # 3. 读取电压
                voltage = reader.read_voltage(visa_address)
                if voltage is not None:
                    print(f"✓ 电压读数: {voltage:.6f} V")
                else:
                    print(f"✗ 读取电压失败")
            else:
                print(f"✗ 所有VISA连接方法都失败")

        # 4. 可选：扫描网络寻找其他设备
        print("\n" + "=" * 50)
        response = input("是否扫描网络寻找其他设备? (y/n): ")
        if response.lower() == 'y':
            devices = reader.discover_devices()
            if devices:
                print(f"\n发现 {len(devices)} 个设备:")
                for device in devices:
                    print(f"  {device}")
            else:
                print("未发现其他设备")

    finally:
        # 清理资源
        reader.cleanup()

    print("\n程序结束")