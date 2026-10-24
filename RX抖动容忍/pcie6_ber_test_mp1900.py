"""
PCIe 6.0 误码率测试 - MP1900 联调版本 (优化版 v2 + 元数据 + 保存模式)

优化点:
1. 每次 PRESet 切换后重新执行 RX 均衡 (serdes_rx_eq)
2. 多次读取 BER，取最优值 (每次 PRESet 读 3 次)
3. 无效 BER (0.25) 自动重读，最多 5 次
4. 动态等待时间，检测到无效值时自动延长
5. BER 有效性验证，只有有效值才参与最优选择
6. 更长的链路稳定时间 (10s)
7. 显示 FOM 值用于判断均衡质量
8. 总运行时间统计
9. 提前停止机制 (BER < 1e-7 时自动停止)
10. 自动保存 Excel 结果，包含元数据 (芯片编号、温度电压、FW版本、GUI版本、单板编号、插损)
11. 支持三种保存模式：新文件（带时间戳）、追加到已有文件（同Sheet末尾）、覆盖已有文件（替换Sheet）
"""

import sys
import time
import threading
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

import pandas as pd
import os
from openpyxl import load_workbook

# 不再依赖外部 ExcelSaver，直接使用 pandas
from mp1900_device import MP1900Device
# from excel_saver import ExcelSaver
# from models import BERMeasurement

# ============ 配置 ============
SERIAL_PORT = 'COM4'
BAUD_RATE = 115200
MP1900_HOST = '172.17.17.170'
MP1900_PORT = 5001


# ============ 元数据输入函数 ============
def get_metadata_for_ber():
    """交互式获取测试元数据（含插损）"""
    print("\n" + "=" * 60)
    print("请输入本次测试的全局信息（将添加到每条数据中）：")
    print("=" * 60)
    chip = input("  芯片编号 (如 TT-01): ").strip() or "Unknown"
    temp = input("  温度电压 (如 NTNV): ").strip() or "NTNV"
    fw = input("  FW版本 (如 72fae): ").strip() or "Unknown"
    gui = input("  GUI版本 (如 2.4.9): ").strip() or "Unknown"
    board = input("  单板编号 (如 SIB-02): ").strip() or "Unknown"
    il = input("  插损 (db) (如 12.5): ").strip() or "0.0"
    print("=" * 60)
    return {
        'chip_id': chip,
        'temp_voltage': temp,
        'fw_version': fw,
        'gui_version': gui,
        'board_id': board,
        'insertion_loss_db': float(il) if il.replace('.', '', 1).isdigit() else 0.0
    }


# ============ 数据类 ============
@dataclass
class BERMeasurement:
    preset: int
    ber: float
    success: bool
    raw_response: str
    timestamp: float = 0.0
    is_valid: bool = True
    fom: int = 0


# ============ 串口控制器 ============
class SerialController:
    """串口控制器"""

    def __init__(self, port: str = SERIAL_PORT, baudrate: int = BAUD_RATE, timeout: float = 5.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.received_data = []
        self.lock = threading.Lock()
        self.stop_receiving = False
        self.receive_thread = None
        self.debug = False

    def open(self) -> bool:
        try:
            import serial
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            if self.ser.is_open:
                print(f"[Serial] {self.port} 已打开")
                self.stop_receiving = False
                self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
                self.receive_thread.start()
                return True
            return False
        except Exception as e:
            print(f"[Serial] 打开失败: {e}")
            return False

    def close(self):
        self.stop_receiving = True
        if self.receive_thread:
            self.receive_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"[Serial] {self.port} 已关闭")

    def _receive_loop(self):
        while not self.stop_receiving:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    if data:
                        decoded = data.decode('utf-8', errors='ignore')
                        with self.lock:
                            self.received_data.append(decoded)
                time.sleep(0.01)
            except Exception as e:
                if not self.stop_receiving:
                    print(f"[Serial] 接收错误: {e}")
                break

    def send_command(self, cmd: str, wait: float = 0.5, timeout: float = 5.0) -> str:
        """发送命令并等待响应"""
        if not self.ser or not self.ser.is_open:
            return ""

        try:
            with self.lock:
                self.received_data.clear()

            cmd_with_newline = cmd + '\n' if not cmd.endswith('\n') else cmd
            self.ser.write(cmd_with_newline.encode('utf-8'))
            self.ser.flush()
            print(f"[Tx] {cmd}")

            time.sleep(wait)

            response = ""
            start_time = time.time()
            last_data_time = time.time()

            while time.time() - start_time < timeout:
                with self.lock:
                    if self.received_data:
                        for data in self.received_data:
                            response += data
                            last_data_time = time.time()
                        self.received_data.clear()

                if response:
                    if 'jingyu:/$' in response or 'jingyu:/#' in response:
                        break
                    if 'ber:' in response.lower():
                        time.sleep(0.3)
                        break
                    if time.time() - last_data_time > 1.0:
                        break

                time.sleep(0.05)

            response = response.strip()
            if response:
                lines = response.split('\n')
                filtered = []
                for line in lines:
                    if line.strip() != cmd and not line.strip().startswith(cmd):
                        filtered.append(line)
                response = '\n'.join(filtered).strip()

            return response

        except Exception as e:
            print(f"[Serial] 发送错误: {e}")
            return ""

    def send_ber_commands(self, wait_time: float = 5.0, max_retries: int = 3) -> str:
        """
        发送 BER 读取两条命令，动态等待直到获取有效数据
        """
        if not self.ser or not self.ser.is_open:
            return ""

        try:
            # 清空缓冲区
            with self.lock:
                self.received_data.clear()

            # 第一条命令: serdes_rx_data_en_set
            cmd1 = "serdes_rx_data_en_set 0 0 0x1 1"
            self.ser.write((cmd1 + '\n').encode())
            self.ser.flush()
            print(f"[Tx] {cmd1}")
            time.sleep(0.5)

            # 再次清空缓冲区
            with self.lock:
                self.received_data.clear()

            # 第二条命令: serdes_rx_ber_check
            cmd2 = "serdes_rx_ber_check 0 0 0x1 6"
            self.ser.write((cmd2 + '\n').encode())
            self.ser.flush()
            print(f"[Tx] {cmd2}")

            # 动态等待
            print(f"  ⏳ 等待 BER 数据 (动态检测)...")

            response = ""
            start_time = time.time()
            last_data_time = time.time()
            timeout = 20.0

            while time.time() - start_time < timeout:
                with self.lock:
                    if self.received_data:
                        for data in self.received_data:
                            response += data
                            last_data_time = time.time()
                        self.received_data.clear()

                if response:
                    if 'ber:' in response.lower():
                        elapsed = time.time() - start_time
                        print(f"  ✅ 获取到 BER 数据 (耗时 {elapsed:.1f}s)")
                        break

                    if 'jingyu:/$' in response or 'jingyu:/#' in response:
                        print(f"  ⚠️ 收到 shell 提示符但无 BER 数据")
                        break

                    if time.time() - last_data_time > 4.0:
                        print(f"  ⚠️ 数据接收停止")
                        break

                time.sleep(0.1)

            # 重试逻辑
            retry_count = 0
            while retry_count < max_retries and 'ber:' not in response.lower():
                print(f"  🔄 未获取到 BER 数据，重试 ({retry_count + 1}/{max_retries})...")
                retry_count += 1

                with self.lock:
                    self.received_data.clear()

                self.ser.write((cmd2 + '\n').encode())
                self.ser.flush()
                print(f"[Tx] {cmd2} (重试 {retry_count})")

                retry_start = time.time()
                while time.time() - retry_start < 12.0:
                    with self.lock:
                        if self.received_data:
                            for data in self.received_data:
                                response += data
                                last_data_time = time.time()
                            self.received_data.clear()

                    if response and 'ber:' in response.lower():
                        elapsed = time.time() - retry_start
                        print(f"  ✅ 重试成功获取 BER 数据 (耗时 {elapsed:.1f}s)")
                        break

                    time.sleep(0.1)

            # 清理响应
            response = response.strip()
            if response:
                lines = response.split('\n')
                filtered = []
                for line in lines:
                    if line.strip() not in [cmd1, cmd2]:
                        filtered.append(line)
                response = '\n'.join(filtered).strip()

            return response

        except Exception as e:
            print(f"[Serial] 发送错误: {e}")
            return ""


# # ============ MP1900 设备模拟（占位） ============
# # 实际项目中应导入真实的 mp1900_device 模块
# class MP1900Device:
#     def __init__(self, host, debug=False):
#         self.host = host
#         self.debug = debug
#
#     def connect(self):
#         print(f"[MP1900] 连接到 {self.host}")
#         return True
#
#     def close(self):
#         print("[MP1900] 断开")
#
#     def send_command(self, cmd):
#         print(f"[MP1900] 发送: {cmd}")
#         return True
#
#     def query(self, cmd):
#         print(f"[MP1900] 查询: {cmd}")
#         return "0"
#
#     def wait_complete(self):
#         time.sleep(0.1)
#

# ============ PCIe 6.0 测试类 (优化版 v2 + 元数据) ============
class PCIe6BERTestMP1900:
    """
    PCIe 6.0 误码率测试 - MP1900 联调版 (优化 v2 + 元数据)
    """

    def __init__(self, port: str = SERIAL_PORT, mp1900_host: str = MP1900_HOST):
        self.serial = SerialController(port)
        self.mp1900 = MP1900Device(host=mp1900_host, debug=True)
        self.current_preset = -1
        self.results: List[BERMeasurement] = []
        self.start_time = 0.0
        self._rate = "GEN6"
        self._lane = "lane0"
        self.metadata = {}          # 存储元数据

    def set_metadata(self, metadata_dict):
        """设置本次测试的元数据"""
        self.metadata = metadata_dict

    # ============================================================
    # 连接管理
    # ============================================================

    def connect(self) -> bool:
        if not self.serial.open():
            return False
        if not self.mp1900.connect():
            print("[警告] MP1900 连接失败")
            return False
        return True

    def disconnect(self):
        self.serial.close()
        self.mp1900.close()

    def _send_and_wait(self, cmd: str, wait: float = 0.5, timeout: float = 5.0) -> str:
        return self.serial.send_command(cmd, wait, timeout)

    # ============================================================
    # MP1900 初始化
    # ============================================================

    def init_mp1900(self) -> bool:
        print("\n" + "=" * 60)
        print("步骤1: MP1900 初始化 (PCIe 6.0 PAM4)")
        print("=" * 60)

        commands = [
            ':UENTry:ID 1; :MODule:ID 7; :SOURce:MOD:TYPE PAM4',
            ':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :OUTPut:PAM4:TOTal:AMPLitude 0.590',
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:FREQuency 400000',
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:AMPLitude 15.000',
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ2:AMPLitude 0.016',
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:RJ:AMPLitude 0.120',
            ':UENTry:ID 1; :MODule:ID 8; :SOURce:CMNoise:AMPLitude 96',
            ':UENTry:ID 1; :MODule:ID 8; :SOURce:DMNoise:AMPLitude 22',
            ':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:EMPHasis:STANdard PCI6',
            ':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:PATTern:PAM4:PRBS:LENG 31',
            ':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:PATTern:PAM4:PRBS:MSB:INV OFF',
            ':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:PATTern:PAM4:PRBS:LSB:INV OFF',
            ':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:PATTern:PAM4:GRAYcode OFF',
        ]

        for cmd in commands:
            if not self.mp1900.send_command(cmd):
                print(f"  ❌ MP1900 初始化失败: {cmd}")
                return False
            print(f"  ✅ {cmd}")

        if not self.mp1900.send_command(':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:EMPHasis:PRESet 0'):
            print("  ❌ 初始 PRESet 设置失败")
            return False
        print("  ✅ PRESet = 0 (初始)")

        if not self.mp1900.send_command(':SOURce:OUTPut:ASET ON'):
            print("  ❌ 输出使能失败")
            return False
        print("  ✅ :SOURce:OUTPut:ASET ON")

        self.mp1900.wait_complete()
        print("\n✅ MP1900 初始化完成")
        return True

    # ============================================================
    # SerDes 初始化 + GEN6 切换
    # ============================================================

    def init_serdes(self) -> bool:
        print("\n" + "=" * 60)
        print("步骤2: SerDes 初始化")
        print("=" * 60)

        commands = [
            ("phy_init_only", 2.0, 5.0),
            ("m3_run", 1.0, 5.0),
            ("phy_macro_reset", 2.0, 5.0),
            ("serdes_set_cca_skip 0 0 0 0xffffffff", 0.5, 3.0),
            ("serdes_set_cca_skip 0 0 1 0xffffffff", 0.5, 3.0),
            ("serdes_start_cm 0 0 3", 2.0, 10.0),
            ("serdes_pstate_chg 0 0 0xf 0", 0.5, 3.0),
            ("serdes_set_tx_ffe 0 0 2 6", 0.5, 3.0),
            ("serdes_tx_pattern_gen 0 0 0x1 0 0 0 4 1", 0.5, 3.0),
            ("serdes_rate_chg 0 0 0x1 4", 0.5, 3.0),
            ("serdes_rx_data_en_set 0 0 0x1 1", 0.5, 3.0),
            ("serdes_rx_ber_check 0 0 0x1 6", 2.0, 5.0),
            ("serdes_rx_data_en_set 0 0 0xf 0", 0.5, 3.0),
        ]

        for cmd, wait, timeout in commands:
            resp = self._send_and_wait(cmd, wait, timeout)
            print(f"  ✅ {cmd}")

        print("\n✅ SerDes 初始化完成")
        return True

    def init_gen6(self) -> bool:
        print("\n" + "=" * 60)
        print("步骤3: 切换到 GEN6 模式")
        print("=" * 60)

        commands = [
            ("serdes_tx_pattern_gen 0 0 0x1 0 0 0 4 0", 0.5, 3.0),
            ("serdes_rate_chg 0 0 0x1 5", 0.5, 3.0),
            ("serdes_set_tx_ffe 0 0 2 15", 0.5, 3.0),
            ("serdes_tx_pattern_gen 0 0 0x1 0 0 0 4 1", 0.5, 3.0),
        ]

        for cmd, wait, timeout in commands:
            resp = self._send_and_wait(cmd, wait, timeout)
            print(f"  ✅ {cmd}")

        print("\n✅ GEN6 模式切换完成")
        return True

    # ============================================================
    # MP1900 设置 PRESet
    # ============================================================

    def set_preset_mp1900(self, preset: int) -> bool:
        cmd = f':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:EMPHasis:PRESet {preset}'
        if self.mp1900.send_command(cmd):
            self.current_preset = preset
            print(f"  [MP1900] PRESet = {preset}")
            actual = self.mp1900.query(':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:EMPHasis:PRESet?')
            print(f"  [MP1900] 查询实际 PRESet = {actual}")
            return True
        else:
            print(f"  [MP1900] PRESet {preset} 设置失败")
            return False

    # ============================================================
    # RX 均衡 (关键优化!)
    # ============================================================

    def redo_rx_eq(self) -> bool:
        """
        重新执行 RX 均衡
        这是每次 PRESet 切换后获得最佳 BER 的关键步骤
        """
        print(f"  🔄 重新执行 RX 均衡...")

        resp1 = self._send_and_wait("serdes_rate_chg 0 0 0x1 5", 0.5, 3.0)
        print(f"    serdes_rate_chg 0 0 0x1 5")

        resp2 = self._send_and_wait("serdes_rx_eq 0 0 1 20", 2.0, 5.0)
        print(f"    serdes_rx_eq 0 0 1 20")

        time.sleep(1.0)

        if 'fom' in resp2.lower():
            fom_match = re.search(r'fom\s*=\s*0x([0-9a-fA-F]+)', resp2, re.IGNORECASE)
            if fom_match:
                fom_value = fom_match.group(1)
                print(f"    FOM = 0x{fom_value}")

        return True

    # ============================================================
    # BER 读取 (多次采样 + 有效性判断)
    # ============================================================

    def is_invalid_ber(self, ber: float) -> bool:
        """判断 BER 是否无效 (2.5e-1 是典型的无效值)"""
        if ber < 0:
            return True
        if 0.24 < ber < 0.26:
            return True
        return False

    def read_ber_once(self, wait_time: float = 5.0, redo_eq: bool = True) -> BERMeasurement:
        """单次 BER 读取，可选重新执行 RX 均衡"""
        print(f"\n[PRESet {self.current_preset}] 读取 BER...")

        if redo_eq:
            self.redo_rx_eq()

        ber_response = self.serial.send_ber_commands(wait_time=wait_time, max_retries=3)
        ber_value = self._parse_ber(ber_response)

        fom_value = self._parse_fom(ber_response)

        is_valid = not self.is_invalid_ber(ber_value) if ber_value >= 0 else False

        return BERMeasurement(
            preset=self.current_preset,
            ber=ber_value,
            success=ber_value >= 0 and is_valid,
            raw_response=ber_response,
            timestamp=time.time(),
            is_valid=is_valid,
            fom=fom_value
        )

    def read_ber_multi(self, wait_time: float = 5.0, samples: int = 3, redo_eq: bool = True) -> BERMeasurement:
        """
        多次读取 BER，取最优值 (最小 BER)
        如果某次读到无效值 (0.25)，自动重读
        """
        print(f"\n[PRESet {self.current_preset}] 读取 BER (采样 {samples} 次)...")

        valid_readings = []
        invalid_count = 0
        max_invalid_retry = 5

        for i in range(samples):
            print(f"  --- 采样 {i+1}/{samples} ---")
            result = self.read_ber_once(wait_time=wait_time, redo_eq=redo_eq)

            if result.success and result.is_valid:
                valid_readings.append(result.ber)
                fom_str = f", FOM=0x{result.fom:x}" if result.fom > 0 else ""
                print(f"  📊 采样 {i+1}: BER = {result.ber:.6e} ✅{fom_str}")
            else:
                invalid_count += 1
                if result.ber >= 0:
                    print(f"  📊 采样 {i+1}: BER = {result.ber:.6e} ❌ (无效)")
                else:
                    print(f"  📊 采样 {i+1}: 读取失败 ❌")

                if invalid_count <= max_invalid_retry:
                    print(f"  ⏳ 等待额外 3s 后继续...")
                    time.sleep(3.0)

        if valid_readings:
            best_ber = min(valid_readings)
            print(f"\n  🏆 最优 BER = {best_ber:.6e} (来自 {len(valid_readings)} 个有效采样)")
            return BERMeasurement(
                preset=self.current_preset,
                ber=best_ber,
                success=True,
                raw_response=f"best_of_{len(valid_readings)}_samples",
                timestamp=time.time(),
                is_valid=True,
                fom=0
            )
        else:
            print(f"\n  ❌ 所有采样均无效或失败")
            return BERMeasurement(
                preset=self.current_preset,
                ber=-1.0,
                success=False,
                raw_response="all_samples_invalid",
                timestamp=time.time(),
                is_valid=False,
                fom=0
            )

    def _parse_ber(self, response: str) -> float:
        if not response:
            return -1.0

        pattern = r'ber\s*[:=]\s*([0-9.]+[eE][+-]?[0-9]+)'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except:
                pass

        pattern2 = r'([0-9.]+[eE][+-]?[0-9]+)'
        matches = re.findall(pattern2, response)
        if matches:
            try:
                return float(matches[0])
            except:
                pass

        return -1.0

    def _parse_fom(self, response: str) -> int:
        """从响应中提取 FOM 值"""
        if not response:
            return 0

        pattern = r'fom\s*=\s*0x([0-9a-fA-F]+)'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1), 16)
            except:
                pass

        pattern2 = r'fom\s*=\s*0x([0-9a-fA-F]{1,2})'
        match = re.search(pattern2, response, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1), 16)
            except:
                pass

        return 0

    # ============================================================
    # PRESet 扫描
    # ============================================================

    def scan_preset(
        self,
        preset_range: List[int] = None,
        settle_time: float = 10.0,
        ber_wait_time: float = 5.0,
        samples: int = 3,
        redo_eq: bool = True,
        on_preset_applied: callable = None
    ) -> List[BERMeasurement]:
        if preset_range is None:
            preset_range = list(range(0, 11))

        self.results = []

        print("\n" + "=" * 60)
        print("步骤4: PRESet 扫描 (Q0 -> Q10)")
        print("=" * 60)
        print(f"PRESet 范围: {preset_range}")
        print(f"链路稳定等待: {settle_time}s")
        print(f"BER 采样次数: {samples} 次/PRESet")
        print(f"RX 均衡重新执行: {'✅' if redo_eq else '❌'}")
        print("=" * 60)

        for preset in preset_range:
            print(f"\n{'=' * 40}")
            print(f"Q{preset} (PRESet = {preset})")
            print(f"{'=' * 40}")

            if not self.set_preset_mp1900(preset):
                print(f"  ❌ PRESet {preset} 设置失败，跳过")
                continue

            print(f"  ⏳ 等待 {settle_time}s 链路稳定...")
            time.sleep(settle_time)

            result = self.read_ber_multi(
                wait_time=ber_wait_time,
                samples=samples,
                redo_eq=redo_eq
            )
            self.results.append(result)

            if on_preset_applied:
                try:
                    should_continue = on_preset_applied(preset, result)
                    # if not should_continue:
                    #     print(f"\n⏹️ 扫描停止 (PRESet={preset})")
                    #     break
                except Exception as e:
                    print(f"  ❌ 回调执行失败: {e}")
                    break

            time.sleep(1.0)

        self._print_summary()
        return self.results

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("扫描汇总")
        print("=" * 60)

        print(f"{'PRESet':>8} | {'BER':>18} | {'Status':>10} | {'Valid':>8} | {'FOM':>8}")
        print("-" * 65)

        valid_results = []
        for r in self.results:
            status = "✅" if r.success else "❌"
            valid_str = "✅" if r.is_valid else "❌"
            ber_str = f"{r.ber:.6e}" if r.ber >= 0 else "N/A"
            fom_str = f"0x{r.fom:x}" if r.fom > 0 else "N/A"
            print(f"{r.preset:>8} | {ber_str:>18} | {status:>10} | {valid_str:>8} | {fom_str:>8}")
            if r.success and r.is_valid:
                valid_results.append(r)

        if valid_results:
            best = min(valid_results, key=lambda x: x.ber)
            print("\n" + "-" * 65)
            print(f"🏆 最优 PRESet: {best.preset} (BER = {best.ber:.6e})")
            self._best_preset = best.preset
            self._best_ber = best.ber
        else:
            print("\n" + "-" * 65)
            print("⚠️ 没有有效的 BER 数据")
            self._best_preset = -1
            self._best_ber = -1.0

    def get_best_preset(self) -> Tuple[int, float]:
        if hasattr(self, '_best_preset') and self._best_preset >= 0:
            return self._best_preset, self._best_ber
        return -1, -1.0

    def apply_best_preset(self) -> bool:
        best_p, best_b = self.get_best_preset()
        if best_p < 0:
            print("❌ 没有有效的最优 PRESet")
            return False

        print(f"\n[应用最优值] PRESet = {best_p}, BER = {best_b:.6e}")
        return self.set_preset_mp1900(best_p)

    # ============================================================
    # 保存 Excel (支持三种模式)
    # ============================================================

    def save_excel(self, rate: str = "GEN6", lane: str = "lane0", mode: str = 'new') -> Optional[str]:
        """
        保存测试结果到 Excel 文件，包含元数据，并标注最优 PRESet
        mode: 'new' (新文件带时间戳), 'append' (追加到同一Sheet末尾), 'overwrite' (覆盖Sheet)
        """
        if not self.results:
            print("⚠️ 没有数据可保存")
            return None

        best_p, best_b = self.get_best_preset()
        elapsed = time.time() - self.start_time

        # 构建 DataFrame
        rows = []
        for r in self.results:
            row = {
                **self.metadata,
                'preset': r.preset,
                'ber': r.ber if r.ber >= 0 else None,
                'success': r.success,
                'is_valid': r.is_valid,
                'fom': r.fom,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r.timestamp)) if r.timestamp else ''
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # 列重命名（中文）
        meta_rename = {
            'chip_id': '芯片编号',
            'temp_voltage': '温度电压',
            'fw_version': 'FW版本',
            'gui_version': 'gui版本',
            'board_id': '单板编号',
            'insertion_loss_db': '插损(db)'
        }
        data_rename = {
            'preset': 'PRESet',
            'ber': 'BER',
            'success': 'Success',
            'is_valid': 'Valid',
            'fom': 'FOM',
            'timestamp': '时间戳'
        }
        all_rename = {**meta_rename, **data_rename}
        df = df.rename(columns=all_rename)

        # ★ 新增：添加“备注”列，并在最优行标注
        df['备注'] = ''
        if best_p >= 0:
            df.loc[df['PRESet'] == best_p, '备注'] = '★ Best'

        # 指定列顺序（将“备注”放在最后）
        meta_keys = ['芯片编号', '温度电压', 'FW版本', 'gui版本', '单板编号', '插损(db)']
        data_keys = ['PRESet', 'BER', 'Success', 'Valid', 'FOM', '时间戳']
        columns_order = [c for c in meta_keys + data_keys if c in df.columns] + ['备注']
        df = df[columns_order]

        # 确定输出目录和文件名
        output_dir = "./xlsx"
        os.makedirs(output_dir, exist_ok=True)

        if mode == 'new':
            filename = os.path.join(output_dir, f"ber_scan_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="BER_scan", index=False)
            print(f"📊 数据已保存 (新文件): {os.path.abspath(filename)}")
            return filename

        # 追加或覆盖使用固定文件名
        filename = os.path.join(output_dir, "ber_scan.xlsx")
        sheet_name = "BER_scan"

        if mode == 'append':
            if os.path.exists(filename):
                try:
                    existing = pd.read_excel(filename, sheet_name=sheet_name, engine='openpyxl')
                    combined = pd.concat([existing, df], ignore_index=True)
                    with pd.ExcelWriter(filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                        combined.to_excel(writer, sheet_name=sheet_name, index=False)
                    print(f"📊 数据已追加 (原有{len(existing)}行，新增{len(df)}行): {os.path.abspath(filename)}")
                except Exception as e:
                    print(f"⚠️ 追加失败，创建新文件: {e}")
                    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                    print(f"📊 数据已保存: {os.path.abspath(filename)}")
            else:
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"📊 文件不存在，已创建: {os.path.abspath(filename)}")
            return filename

        elif mode == 'overwrite':
            if os.path.exists(filename):
                with pd.ExcelWriter(filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"📊 数据已覆盖: {os.path.abspath(filename)}")
            else:
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"📊 文件不存在，已创建: {os.path.abspath(filename)}")
            return filename

        else:
            # 默认新建（带时间戳）作为后备
            filename = os.path.join(output_dir, f"ber_scan_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="BER_scan", index=False)
            print(f"📊 数据已保存 (默认新文件): {os.path.abspath(filename)}")
            return filename

    # ============================================================
    # 完整流程
    # ============================================================

    def run_full_test(
        self,
        preset_range: List[int] = None,
        settle_time: float = 10.0,
        ber_wait_time: float = 5.0,
        samples: int = 3,
        redo_eq: bool = True,
        on_preset_applied: callable = None,
        save_excel: bool = True,
        rate: str = "GEN6",
        lane: str = "lane0",
        save_mode: str = 'new'      # 新增：保存模式
    ) -> List[BERMeasurement]:
        """运行完整测试流程"""
        self.start_time = time.time()
        self._rate = rate
        self._lane = lane

        print("\n" + "=" * 60)
        print("PCIe 6.0 误码率测试 - MP1900 联调 (优化版 v2 + 元数据)")
        print("=" * 60)
        print(f"SerDes 串口: {SERIAL_PORT}")
        print(f"MP1900 IP: {MP1900_HOST}")
        print(f"RX 均衡重新执行: {'✅' if redo_eq else '❌'}")
        print(f"保存模式: {save_mode}")
        print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        if not self.init_mp1900():
            print("❌ MP1900 初始化失败")
            return []

        if not self.init_serdes():
            print("❌ SerDes 初始化失败")
            return []

        if not self.init_gen6():
            print("❌ GEN6 切换失败")
            return []

        results = self.scan_preset(
            preset_range=preset_range,
            settle_time=settle_time,
            ber_wait_time=ber_wait_time,
            samples=samples,
            redo_eq=redo_eq,
            on_preset_applied=on_preset_applied
        )

        if results:
            self.apply_best_preset()

        # 计算总运行时间
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = elapsed % 60

        print("\n" + "=" * 60)
        print(f"测试完成!")
        print(f"总运行时间: {hours}h {minutes}m {seconds:.1f}s")
        print(f"结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 保存 Excel
        if save_excel and results:
            filepath = self.save_excel(rate=rate, lane=lane, mode=save_mode)
            if filepath:
                print(f"📊 Excel 已保存: {filepath}")

        return results


# ============================================================
# 外部回调
# ============================================================

def my_callback(preset: int, result: BERMeasurement) -> bool:
    """
    回调函数: 每次 BER 读取完成后调用
    返回 True 继续，False 停止
    """
    ber_str = f"{result.ber:.6e}" if result.ber >= 0 else "N/A"
    valid_str = "✅" if result.is_valid else "❌"
    fom_str = f"0x{result.fom:x}" if result.fom > 0 else "N/A"
    print(f"\n>>> [回调] Q{preset} 完成, BER={ber_str}, Valid={valid_str}, FOM={fom_str}")

    # 如果找到有效的低 BER，提前停止
    if result.is_valid and result.ber >= 0 and result.ber < 1e-7:
        print(f"    BER < 1e-7，找到优秀值!")
        return False

    return True


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='PCIe 6.0 BER 测试 - MP1900 联调 (优化版 v2 + 元数据)')
    parser.add_argument('--scan', action='store_true', help='执行完整扫描')
    parser.add_argument('--settle', type=float, default=10.0, help='链路稳定等待时间 (秒)')
    parser.add_argument('--ber-wait', type=float, default=5.0, help='BER 读取等待时间 (秒)')
    parser.add_argument('--samples', type=int, default=3, help='每个 PRESet 采样次数')
    parser.add_argument('--no-redo-eq', action='store_true', help='不重新执行 RX 均衡')
    parser.add_argument('--preset-start', type=int, default=0, help='起始 PRESet')
    parser.add_argument('--preset-end', type=int, default=10, help='结束 PRESet')
    parser.add_argument('--no-save', action='store_true', help='不保存 Excel')
    parser.add_argument('--rate', type=str, default='GEN6', help='速率 (如 GEN6, GEN5)')
    parser.add_argument('--lane', type=str, default='lane0', help='通道 (如 lane0, lane1)')
    args = parser.parse_args()

    print("=" * 60)
    print("PCIe 6.0 误码率测试启动")
    print("=" * 60)
    print(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 先获取元数据
    metadata = get_metadata_for_ber()

    # 询问保存模式
    print("\n请选择保存模式:")
    print("  1. 生成新文件（带时间戳，默认）")
    print("  2. 追加到已有文件（同一文件同一Sheet，末尾追加数据）")
    print("  3. 覆盖已有文件（替换文件中的 BER_scan Sheet）")
    save_choice = input("请选择 (1-3): ").strip() or "1"
    mode_map = {"1": "new", "2": "append", "3": "overwrite"}
    save_mode = mode_map.get(save_choice, "new")
    print(f"已选择: {save_mode}")

    tester = PCIe6BERTestMP1900(mp1900_host=MP1900_HOST)
    tester.set_metadata(metadata)

    if not tester.connect():
        print("设备连接失败")
        return

    try:
        if args.scan:
            results = tester.run_full_test(
                preset_range=list(range(args.preset_start, args.preset_end + 1)),
                settle_time=args.settle,
                ber_wait_time=args.ber_wait,
                samples=args.samples,
                redo_eq=not args.no_redo_eq,
                on_preset_applied=my_callback,
                save_excel=not args.no_save,
                rate=args.rate,
                lane=args.lane,
                save_mode=save_mode
            )
            best_p, best_b = tester.get_best_preset()
            if best_p >= 0:
                print(f"\n🏆 最终结果: PRESet={best_p}, BER={best_b:.6e}")
        else:
            print("\n单次测试模式 (PRESet=8)")
            tester.init_mp1900()
            tester.init_serdes()
            tester.init_gen6()
            tester.set_preset_mp1900(8)
            time.sleep(args.settle)
            result = tester.read_ber_multi(
                wait_time=args.ber_wait,
                samples=args.samples,
                redo_eq=not args.no_redo_eq
            )
            print(f"\n结果: PRESet={result.preset}, BER={result.ber:.6e}")

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        tester.disconnect()
        print("\n程序结束")


if __name__ == '__main__':
    main()