"""
抖动容限测试 - 第三阶段 (确认+精细化版) + 元数据 + 完整数据保存

改进:
1. 失败确认: 遇到失败时重读确认
2. 精细化搜索: 步长减半 (1/2, 1/4) 精确定位边界
3. 运行时间统计
4. 频率自适应步长: 根据频率自动调整步长
5. 幅度有效值修正: 自动舍入到 MP1900 支持的有效幅度值
6. 人机交互元数据输入 (芯片编号、温度电压、FW版本、GUI版本、单板编号、插损、协议速率)
7. 保存所有测试点数据 (每个频率的每个UI步进点的BER)
8. 修复: 重读通过时更新该点的 BER 和状态，确保汇总 UI 与 BER 匹配
"""

import sys
import time
import re
import os
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from openpyxl import load_workbook

from mp1900_device import MP1900Device
from models import BERMeasurement
from excel_saver import ExcelSaver


# ============ 配置 ============
SERIAL_PORT = 'COM4'
BAUD_RATE = 115200
MP1900_HOST = '172.17.17.170'
MP1900_PORT = 5001

TARGET_BER = 1e-7
DEFAULT_SETTLE_TIME = 3.0
DEFAULT_BER_WAIT = 5.0


# ============ 人机交互元数据输入 ============
def get_metadata():
    """交互式获取测试元数据（含插损和协议速率）"""
    print("\n" + "=" * 60)
    print("请输入本次测试的全局信息（将添加到每条数据中）：")
    print("=" * 60)
    chip = input("  芯片编号 (如 TT-01): ").strip() or "Unknown"
    temp = input("  温度电压 (如 NTNV): ").strip() or "NTNV"
    fw = input("  FW版本 (如 72fae): ").strip() or "Unknown"
    gui = input("  GUI版本 (如 2.4.9): ").strip() or "Unknown"
    board = input("  单板编号 (如 SIB-02): ").strip() or "Unknown"
    il = input("  插损 (db) (如 12.5): ").strip() or "0.0"
    rate = input("  协议速率 (如 GEN6, GEN5): ").strip() or "GEN6"
    print("=" * 60)
    return {
        'chip_id': chip,
        'temp_voltage': temp,
        'fw_version': fw,
        'gui_version': gui,
        'board_id': board,
        'insertion_loss_db': float(il) if il.replace('.', '', 1).isdigit() else 0.0,
        'protocol_rate': rate
    }


# ============ MP1900 SJ 幅度有效值生成 ============
def get_valid_amplitudes(max_ui=20.0):
    """
    生成所有 MP1900 支持的 SJ 幅度有效值（基于实测规律）
    0.004 ~ 0.096 步进 0.004
    0.100 ~ 1.000 步进 0.020
    1.500 ~ max_ui 步进 0.500
    """
    vals = []
    # 0.004 ~ 0.096 步进 0.004
    v = 0.004
    while v < 0.1:
        vals.append(round(v, 3))
        v += 0.004
    # 0.100 ~ 1.000 步进 0.020
    v = 0.100
    while v <= 1.0:
        vals.append(round(v, 3))
        v += 0.020
    # 1.500 ~ max_ui 步进 0.5
    v = 1.5
    while v <= max_ui:
        vals.append(round(v, 3))
        v += 0.5
    return vals

VALID_AMPLITUDES = get_valid_amplitudes(20.0)

def round_to_valid_amplitude(ui: float) -> float:
    """将输入的 UI 舍入到最近的有效幅度值"""
    if ui <= 0:
        return VALID_AMPLITUDES[0]
    if ui >= VALID_AMPLITUDES[-1]:
        return VALID_AMPLITUDES[-1]
    return min(VALID_AMPLITUDES, key=lambda x: abs(x - ui))


# ============ 频率自适应步长配置 ============
FREQUENCY_STEP_MAP = [
    (500, 2.0),
    (1500, 0.5),
    (3500, 0.2),
    (7500, 0.05),
    (30000, 0.02),
    (80000, 0.01),
    (float('inf'), 0.01),
]

def get_step_for_frequency(freq_khz: int) -> float:
    for limit, step in FREQUENCY_STEP_MAP:
        if freq_khz <= limit:
            return step
    return 0.01


# ============ 导入串口控制器 ============
import threading
from pcie6_ber_test_mp1900 import SerialController


@dataclass
class JitterTestResult:
    frequency: int
    ui_amplitude: float
    ber: float
    success: bool
    is_lock_lost: bool = False
    phase: str = "coarse"  # coarse, fine, final
    timestamp: float = field(default_factory=time.time)


@dataclass
class FrequencyScanResult:
    frequency: int
    max_ui: float
    ui_step: float
    test_results: List[JitterTestResult] = None
    reference_ui: float = 0.0


class JitterToleranceTest:

    def __init__(
        self,
        mp1900_host: str = MP1900_HOST,
        port: str = SERIAL_PORT,
        baudrate: int = BAUD_RATE,
        target_ber: float = TARGET_BER,
        settle_time: float = DEFAULT_SETTLE_TIME,
        ber_wait: float = DEFAULT_BER_WAIT
    ):
        self.mp1900 = MP1900Device(host=mp1900_host, debug=True)
        self.serial = SerialController(port, baudrate)
        self.target_ber = target_ber
        self.settle_time = settle_time
        self.ber_wait = ber_wait
        self.best_preset = -1
        self.current_frequency = 0
        self.current_ui = 0.0
        self.results: List[FrequencyScanResult] = []
        self.start_time = 0.0
        self.metadata = {}          # 存储元数据

    def set_metadata(self, metadata: dict):
        self.metadata = metadata

    # ============================================================
    # 连接管理
    # ============================================================

    def connect(self) -> bool:
        if not self.mp1900.connect():
            print("[ERROR] MP1900 连接失败")
            return False
        if not self.serial.open():
            print("[ERROR] 串口连接失败")
            return False
        return True

    def disconnect(self):
        if self.mp1900:
            self.mp1900.close()
        if self.serial:
            self.serial.close()

    def _send_serdes(self, cmd: str, wait: float = 0.5, timeout: float = 5.0) -> str:
        return self.serial.send_command(cmd, wait, timeout)

    # ============================================================
    # SerDes 初始化
    # ============================================================

    def init_serdes(self) -> bool:
        print("\n" + "=" * 60)
        print("步骤1: SerDes 初始化")
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
            resp = self._send_serdes(cmd, wait, timeout)
            print(f"  ✅ {cmd}")

        print("\n✅ SerDes 初始化完成")
        return True

    def init_gen6(self) -> bool:
        print("\n" + "=" * 60)
        print("步骤2: 切换到 GEN6 模式")
        print("=" * 60)

        commands = [
            ("serdes_tx_pattern_gen 0 0 0x1 0 0 0 4 0", 0.5, 3.0),
            ("serdes_rate_chg 0 0 0x1 5", 0.5, 3.0),
            ("serdes_set_tx_ffe 0 0 2 15", 0.5, 3.0),
            ("serdes_tx_pattern_gen 0 0 0x1 0 0 0 4 1", 0.5, 3.0),
        ]

        for cmd, wait, timeout in commands:
            resp = self._send_serdes(cmd, wait, timeout)
            print(f"  ✅ {cmd}")

        print("\n✅ GEN6 模式切换完成")
        return True

    # ============================================================
    # 加载 PRESet
    # ============================================================

    def load_best_preset(self, preset: int) -> bool:
        print(f"\n[加载最优 PRESet] PRESet = {preset}")
        cmd = f':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:EMPHasis:PRESet {preset}'
        if not self.mp1900.send_command(cmd):
            print(f"  ❌ PRESet {preset} 设置失败")
            return False
        actual = self.mp1900.query(':UENTry:ID 1; :MODule:ID 7; :INTerface:ID 1; :SOURce:EMPHasis:PRESet?')
        print(f"  ✅ PRESet 已设置: {actual}")
        self.best_preset = preset
        return True

    # ============================================================
    # RX 均衡
    # ============================================================

    def redo_rx_eq(self) -> bool:
        print(f"  🔄 重新执行 RX 均衡...")
        self._send_serdes("serdes_rate_chg 0 0 0x1 5", 0.5, 3.0)
        self._send_serdes("serdes_rx_eq 0 0 1 20", 2.0, 5.0)
        time.sleep(1.0)
        return True

    # ============================================================
    # 抖动配置 (只打开 SJ1)
    # ============================================================

    def configure_jitter(self, sj_freq: int = 400000, sj_amp: float = 0.004) -> bool:
        commands = [
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:ENABle ON',
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ2:ENABle OFF',
            ':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:RJ:ENABle OFF',
            ':UENTry:ID 1; :MODule:ID 8; :SOURce:CMNoise:ENABle OFF',
            ':UENTry:ID 1; :MODule:ID 8; :SOURce:DMNoise:ENABle OFF',
            f':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:FREQuency {sj_freq}',
            f':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:AMPLitude {sj_amp:.3f}',
        ]
        for cmd in commands:
            if not self.mp1900.send_command(cmd):
                print(f"  ❌ 抖动配置失败: {cmd}")
                return False
        return True

    def set_sj_frequency(self, freq: int) -> bool:
        cmd = f':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:FREQuency {freq}'
        self.current_frequency = freq
        return self.mp1900.send_command(cmd)

    def set_sj_amplitude(self, ui: float) -> bool:
        valid_ui = round_to_valid_amplitude(ui)
        if abs(valid_ui - ui) > 0.001:
            print(f"  ⚠️ UI {ui:.3f} -> {valid_ui:.3f} (有效值)")
        cmd = f':UENTry:ID 1; :MODule:ID 4; :SOURce:JITTer:SJ:AMPLitude {valid_ui:.3f}'
        self.current_ui = valid_ui
        return self.mp1900.send_command(cmd)

    # ============================================================
    # BER 测量
    # ============================================================

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
        return -1.0

    def is_invalid_ber(self, ber: float) -> bool:
        if ber < 0:
            return False
        return 0.24 < ber < 0.26

    def measure_ber(self, redo_eq: bool = True) -> float:
        if redo_eq:
            self.redo_rx_eq()

        self._send_serdes("serdes_rx_data_en_set 0 0 0x1 1", 0.5, 3.0)
        ber_response = self.serial.send_ber_commands(wait_time=self.ber_wait, max_retries=3)
        ber_value = self._parse_ber(ber_response)

        if ber_value >= 0:
            print(f"  📊 BER = {ber_value:.6e}")
        else:
            print(f"  📊 BER 解析失败")

        return ber_value

    # ============================================================
    # 核心: 单个频率扫描 (自适应步长 + 确认 + 精细化)
    # ============================================================

    def scan_ui_for_frequency(
        self,
        frequency: int,
        ui_start: float,
        ui_end: float,
        ui_step: float,
        max_ui_limit: float = None,
        confirm_retries: int = 2
    ) -> FrequencyScanResult:
        """
        从低到高扫描 UI，返回所有测试点数据
        """
        print(f"\n{'=' * 60}")
        print(f"频率: {frequency/1000:.1f} kHz")
        print(f"UI 搜索: {ui_start:.3f} -> {ui_end:.3f}, 步进: {ui_step:.3f}")
        print(f"有效幅度步进: 0-0.1:0.004, 0.1-1.0:0.020, >1.0:0.500")
        if max_ui_limit:
            print(f"参考最大 UI 限制: {max_ui_limit:.3f}")
        print(f"{'=' * 60}")

        if not self.set_sj_frequency(frequency):
            print(f"  ❌ 设置频率失败")
            return FrequencyScanResult(frequency=frequency, max_ui=0.0, ui_step=ui_step)

        all_results = []
        max_valid_ui = ui_start
        first_fail_ui = None
        fail_found = False

        # 阶段1: 粗扫
        print(f"\n[阶段1] 粗扫 (步进 {ui_step:.3f})")
        current_ui = ui_start

        while current_ui <= ui_end:
            if max_ui_limit and current_ui > max_ui_limit:
                print(f"\n  ⏹️ UI={current_ui:.3f} 超过限制 {max_ui_limit:.3f}，停止")
                break

            actual_ui = round_to_valid_amplitude(current_ui)
            if actual_ui < current_ui:
                idx = VALID_AMPLITUDES.index(actual_ui)
                if idx + 1 < len(VALID_AMPLITUDES):
                    current_ui = VALID_AMPLITUDES[idx + 1]
                    continue
                else:
                    break

            print(f"\n  [测试] UI = {current_ui:.3f} (有效值: {actual_ui:.3f})")

            if not self.set_sj_amplitude(current_ui):
                print(f"    ❌ 设置 UI 失败")
                current_ui += ui_step
                continue

            time.sleep(self.settle_time)
            ber = self.measure_ber()

            if self.is_invalid_ber(ber):
                print(f"    ⚠️ 链路失锁，重新均衡...")
                ber = self.measure_ber(redo_eq=True)

            result = JitterTestResult(
                frequency=frequency,
                ui_amplitude=current_ui,
                ber=ber,
                success=ber >= 0,
                is_lock_lost=self.is_invalid_ber(ber),
                phase="coarse"
            )
            all_results.append(result)

            if ber >= 0 and ber < self.target_ber:
                max_valid_ui = current_ui
                print(f"    ✅ 通过 (BER={ber:.6e} < {self.target_ber:.6e})")
                current_ui += ui_step
            else:
                print(f"    ⚠️ 失败 (BER={ber:.6e})，确认中...")
                confirmed = True

                for retry in range(confirm_retries):
                    time.sleep(1.0)
                    print(f"    🔄 重读 {retry+1}/{confirm_retries}...")
                    ber_retry = self.measure_ber(redo_eq=True)

                    if ber_retry >= 0 and ber_retry < self.target_ber:
                        max_valid_ui = current_ui
                        confirmed = False
                        # ★★★ 修复：更新该点的 BER 和状态 ★★★
                        result.ber = ber_retry
                        result.success = True
                        result.is_lock_lost = False
                        print(f"    ✅ 重读通过 (BER={ber_retry:.6e})，更新记录")
                        break
                    else:
                        print(f"    ❌ 重读失败 (BER={ber_retry:.6e})")

                if confirmed:
                    first_fail_ui = current_ui
                    fail_found = True
                    print(f"    ❌ 确认失败，粗扫结束")
                    break
                else:
                    current_ui += ui_step

        # 阶段2: 精细搜索 (1/2 步进)
        if fail_found and first_fail_ui is not None:
            print(f"\n[阶段2] 精细搜索 (步进 {ui_step/2:.3f})")

            search_start = max_valid_ui
            search_end = first_fail_ui
            fine_step = ui_step / 2

            print(f"  回退范围: [{search_start:.3f}, {search_end:.3f}]")

            current_ui = search_start + fine_step
            fail_in_fine = False

            while current_ui < search_end:
                actual_ui = round_to_valid_amplitude(current_ui)
                if actual_ui < current_ui:
                    idx = VALID_AMPLITUDES.index(actual_ui)
                    if idx + 1 < len(VALID_AMPLITUDES):
                        current_ui = VALID_AMPLITUDES[idx + 1]
                        continue
                    else:
                        break

                print(f"\n  [精细] UI = {current_ui:.3f} (有效值: {actual_ui:.3f})")

                if not self.set_sj_amplitude(current_ui):
                    current_ui += fine_step
                    continue

                time.sleep(self.settle_time)
                ber = self.measure_ber()

                if self.is_invalid_ber(ber):
                    ber = self.measure_ber(redo_eq=True)

                result = JitterTestResult(
                    frequency=frequency,
                    ui_amplitude=current_ui,
                    ber=ber,
                    success=ber >= 0,
                    is_lock_lost=self.is_invalid_ber(ber),
                    phase="fine"
                )
                all_results.append(result)

                if ber >= 0 and ber < self.target_ber:
                    max_valid_ui = current_ui
                    print(f"    ✅ 通过 (BER={ber:.6e})")
                    current_ui += fine_step
                else:
                    print(f"    ⚠️ 失败，确认中...")
                    confirmed = True
                    for retry in range(confirm_retries):
                        time.sleep(1.0)
                        ber_retry = self.measure_ber(redo_eq=True)
                        if ber_retry >= 0 and ber_retry < self.target_ber:
                            max_valid_ui = current_ui
                            confirmed = False
                            # ★★★ 修复：更新该点的 BER 和状态 ★★★
                            result.ber = ber_retry
                            result.success = True
                            result.is_lock_lost = False
                            print(f"    ✅ 重读通过，更新记录")
                            break
                        else:
                            print(f"    ❌ 重读失败")

                    if confirmed:
                        print(f"    ❌ 确认失败，精细搜索结束")
                        fail_in_fine = True
                        break
                    else:
                        current_ui += fine_step

            # 阶段3: 进一步精细 (1/4 步进)
            if fail_in_fine:
                print(f"\n[阶段3] 进一步精细 (步进 {fine_step/2:.3f})")
                final_step = fine_step / 2
                current_ui = max_valid_ui + final_step

                while current_ui < search_end:
                    actual_ui = round_to_valid_amplitude(current_ui)
                    if actual_ui < current_ui:
                        idx = VALID_AMPLITUDES.index(actual_ui)
                        if idx + 1 < len(VALID_AMPLITUDES):
                            current_ui = VALID_AMPLITUDES[idx + 1]
                            continue
                        else:
                            break

                    print(f"\n  [最终] UI = {current_ui:.3f} (有效值: {actual_ui:.3f})")

                    if not self.set_sj_amplitude(current_ui):
                        current_ui += final_step
                        continue

                    time.sleep(self.settle_time)
                    ber = self.measure_ber()

                    if self.is_invalid_ber(ber):
                        ber = self.measure_ber(redo_eq=True)

                    result = JitterTestResult(
                        frequency=frequency,
                        ui_amplitude=current_ui,
                        ber=ber,
                        success=ber >= 0,
                        is_lock_lost=self.is_invalid_ber(ber),
                        phase="final"
                    )
                    all_results.append(result)

                    if ber >= 0 and ber < self.target_ber:
                        max_valid_ui = current_ui
                        print(f"    ✅ 通过 (BER={ber:.6e})")
                        current_ui += final_step
                    else:
                        print(f"    ❌ 失败，边界确定")
                        break

        print(f"\n{'=' * 50}")
        print(f"📊 频率 {frequency/1000:.1f}kHz 最大 UI: {max_valid_ui:.3f}")
        print(f"   总测试点数: {len(all_results)}")
        print(f"{'=' * 50}")

        return FrequencyScanResult(
            frequency=frequency,
            max_ui=max_valid_ui,
            ui_step=ui_step,
            test_results=all_results
        )

    # ============================================================
    # 完整测试流程 (自适应步长)
    # ============================================================

    def run_jitter_tolerance_test(
            self,
            frequencies: List[int],
            ui_start: float = 0.004,
            ui_end: float = 15.0,
            ui_step: float = None,
            use_adaptive_step: bool = True,
            save_mode: str = 'new'
    ) -> List[FrequencyScanResult]:
        """
        运行完整的抖动容限测试 (自适应步长)
        save_mode: 'new', 'append', 'overwrite' 用于控制Excel保存行为
        """
        self.start_time = time.time()

        print("\n" + "=" * 60)
        print("抖动容限测试 - 第三阶段 (自适应步长版) + 完整数据保存")
        print("=" * 60)
        print(f"目标 BER: {self.target_ber:.6e}")
        print(f"频率列表: {[f / 1000 for f in frequencies]} kHz")
        print(f"UI 搜索: {ui_start:.3f} -> {ui_end:.3f}")
        print(f"步长策略: {'自适应' if use_adaptive_step else f'固定 {ui_step:.3f}'}")
        print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        if use_adaptive_step:
            print("\n频率自适应步长:")
            for freq in frequencies:
                freq_khz = freq / 1000
                step = get_step_for_frequency(freq_khz)
                print(f"  {freq_khz:.1f} kHz -> 步长 {step:.3f}")
            print()

        if not self.connect():
            print("❌ 设备连接失败")
            return []

        try:
            if not self.init_serdes():
                print("❌ SerDes 初始化失败")
                return []

            if not self.init_gen6():
                print("❌ GEN6 切换失败")
                return []

            if self.best_preset < 0:
                print("⚠️ 未设置最优 PRESet，使用 PRESet=0")
                self.best_preset = 0
            if not self.load_best_preset(self.best_preset):
                print("❌ PRESet 加载失败")
                return []

            print("\n配置抖动参数 (SJ1 ON, 其他 OFF)...")
            self.configure_jitter(sj_freq=frequencies[0], sj_amp=ui_start)

            self.results = []

            for i, freq in enumerate(frequencies):
                print(f"\n{'#' * 60}")
                print(f"频率 {i + 1}/{len(frequencies)}: {freq / 1000:.1f} kHz")
                print(f"{'#' * 60}")

                if use_adaptive_step:
                    current_step = get_step_for_frequency(freq / 1000)
                else:
                    current_step = ui_step or 0.5

                result = self.scan_ui_for_frequency(
                    frequency=freq,
                    ui_start=ui_start,
                    ui_end=ui_end,
                    ui_step=current_step,
                    max_ui_limit=None
                )

                self.results.append(result)

            self._print_summary()

            # 保存Excel (传入模式)
            self._save_excel(mode=save_mode)

            elapsed = time.time() - self.start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = elapsed % 60

            print("\n" + "=" * 60)
            print(f"测试完成!")
            print(f"总运行时间: {hours}h {minutes}m {seconds:.1f}s")
            print(f"结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)

            return self.results

        except KeyboardInterrupt:
            print("\n用户中断")
            return self.results
        except Exception as e:
            print(f"执行出错: {e}")
            import traceback
            traceback.print_exc()
            return self.results
        finally:
            self.disconnect()

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("抖动容限测试汇总")
        print("=" * 60)
        print(f"{'频率 (kHz)':>12} | {'最大 UI':>10} | {'步长':>8} | {'测试点数':>8}")
        print("-" * 50)

        for r in self.results:
            count = len(r.test_results) if r.test_results else 0
            print(f"{r.frequency / 1000:>12.1f} | {r.max_ui:>10.3f} | {r.ui_step:>8.3f} | {count:>8}")

    def _save_excel(self, mode='new'):
        """保存所有测试点数据到Excel（含元数据，每个频率末尾附加汇总行）"""
        if not self.results:
            return

        rows = []
        for freq_result in self.results:
            # --- 详细数据点 ---
            for tr in freq_result.test_results:
                row = {k: v for k, v in self.metadata.items()}
                row.update({
                    '频率_kHz': tr.frequency / 1000,
                    'UI': tr.ui_amplitude,
                    'BER': tr.ber if tr.ber >= 0 else None,
                    '成功': tr.success,
                    '失锁': tr.is_lock_lost,
                    '阶段': tr.phase,
                })
                rows.append(row)

            # --- 查找最大通过UI及其对应的BER（优先取 final 阶段，否则取最大UI） ---
            max_ui = freq_result.max_ui
            max_ber = None
            # 优先在 final 阶段查找
            for tr in freq_result.test_results:
                if tr.phase == 'final' and abs(tr.ui_amplitude - max_ui) < 1e-6:
                    max_ber = tr.ber if tr.ber >= 0 else None
                    break
            # 若没找到，则从所有点中匹配UI
            if max_ber is None:
                for tr in freq_result.test_results:
                    if abs(tr.ui_amplitude - max_ui) < 1e-6:
                        max_ber = tr.ber if tr.ber >= 0 else None
                        break

            # --- 汇总行 ---
            summary_row = {k: v for k, v in self.metadata.items()}
            summary_row.update({
                '频率_kHz': freq_result.frequency / 1000,
                'UI': max_ui,
                'BER': max_ber,
                '成功': None,
                '失锁': None,
                '阶段': f'最大通过UI(步长{freq_result.ui_step:.3f}, {len(freq_result.test_results)}点)',
            })
            rows.append(summary_row)

            # --- 空行分隔 ---
            empty_row = {k: None for k in rows[0].keys()}
            rows.append(empty_row)

        df = pd.DataFrame(rows)

        # 重命名元数据列为中文
        rename_map = {
            'chip_id': '芯片编号',
            'temp_voltage': '温度电压',
            'fw_version': 'FW版本',
            'gui_version': 'gui版本',
            'board_id': '单板编号',
            'insertion_loss_db': '插损(db)',
            'protocol_rate': '协议速率'
        }
        for old, new in rename_map.items():
            if old in df.columns:
                df.rename(columns={old: new}, inplace=True)

        # 列顺序
        meta_cols = ['芯片编号', '温度电压', 'FW版本', 'gui版本', '单板编号', '插损(db)', '协议速率']
        meta_present = [c for c in meta_cols if c in df.columns]
        data_cols = ['频率_kHz', 'UI', 'BER', '成功', '失锁', '阶段']
        all_cols = meta_present + [c for c in data_cols if c in df.columns]
        df = df[all_cols]

        # 决定文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if mode == 'new':
            filename = f"./xlsx/Jitter_Data_{timestamp}.xlsx"
        else:
            filename = "./xlsx/Jitter_Data.xlsx"

        os.makedirs("./xlsx", exist_ok=True)
        sheet_name = "Jitter_Data"

        # 保存逻辑
        if mode == 'new':
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"📊 数据已保存 (新文件): {os.path.abspath(filename)}")

        elif mode == 'append':
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

        elif mode == 'overwrite':
            if os.path.exists(filename):
                with pd.ExcelWriter(filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"📊 数据已覆盖: {os.path.abspath(filename)}")
            else:
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"📊 文件不存在，已创建: {os.path.abspath(filename)}")
        else:
            filename = f"./xlsx/Jitter_Data_{timestamp}.xlsx"
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"📊 数据已保存: {os.path.abspath(filename)}")


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='抖动容限测试 - 第三阶段 (自适应步长)')
    parser.add_argument('--preset', type=int, default=6, help='最优 PRESet')
    parser.add_argument('--target-ber', type=float, default=1e-6, help='目标 BER 阈值')
    parser.add_argument('--ui-start', type=float, default=0.004, help='起始 UI (低)')
    parser.add_argument('--ui-end', type=float, default=15.0, help='结束 UI (高)')
    parser.add_argument('--ui-step', type=float, default=None, help='UI 步进 (默认自适应)')
    parser.add_argument('--frequencies', type=str, default='400,800,1200,1600,2000',
                        help='频率列表 (kHz), 逗号分隔')
    parser.add_argument('--confirm-retries', type=int, default=2, help='失败确认重试次数')
    parser.add_argument('--no-adaptive', action='store_true', help='禁用自适应步长')
    args = parser.parse_args()

    frequencies = [int(f.strip()) * 1000 for f in args.frequencies.split(',')]

    print("=" * 60)
    print("抖动容限测试启动 (第三阶段 - 自适应步长)")
    print("=" * 60)
    print(f"最优 PRESet: {args.preset}")
    print(f"目标 BER: {args.target_ber:.6e}")
    print(f"频率列表: {[f/1000 for f in frequencies]} kHz")
    print(f"UI 范围: {args.ui_start:.3f} -> {args.ui_end:.3f}")
    print(f"步长策略: {'自适应' if not args.no_adaptive else f'固定 {args.ui_step}'}")
    print(f"失败确认重试: {args.confirm_retries} 次")
    print("=" * 60)

    # ---- 1. 获取元数据 ----
    metadata = get_metadata()

    # ---- 2. 选择保存模式 ----
    print("\n请选择保存模式:")
    print("  1. 生成新文件（带时间戳，默认）")
    print("  2. 追加到已有文件（同一文件同一Sheet，末尾追加数据）")
    print("  3. 覆盖已有文件（替换文件中的 Jitter_Data Sheet）")
    save_choice = input("请选择 (1-3): ").strip() or "1"
    mode_map = {"1": "new", "2": "append", "3": "overwrite"}
    save_mode = mode_map.get(save_choice, "new")

    # ---- 3. 创建测试实例 ----
    tester = JitterToleranceTest(
        target_ber=args.target_ber,
        settle_time=3.0,
        ber_wait=5.0
    )
    tester.best_preset = args.preset
    tester.set_metadata(metadata)

    # ---- 4. 运行测试 ----
    results = tester.run_jitter_tolerance_test(
        frequencies=frequencies,
        ui_start=args.ui_start,
        ui_end=args.ui_end,
        ui_step=args.ui_step,
        use_adaptive_step=not args.no_adaptive,
        save_mode=save_mode
    )


if __name__ == '__main__':
    main()