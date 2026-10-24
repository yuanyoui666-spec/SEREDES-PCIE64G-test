import serial
import time
import re
import logging

# ==================== 配置调试日志 ====================
# 设置日志级别，可切换为 logging.DEBUG 查看更详细信息
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== 串口通信封装 ====================
class SerdesComm:
    def __init__(self, port='COM4', baudrate=115200, timeout=2, debug=False):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug
        self.ser = None
        self.connect()

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            logger.info(f"串口 {self.port} 打开成功 (波特率 {self.baudrate})")
        except Exception as e:
            logger.error(f"串口打开失败: {e}")
            raise

    def send_command(self, cmd):
        """发送命令，返回解析出的 value 值（整数），若没有 value 则返回 None"""
        if not self.ser:
            raise Exception("串口未打开")
        self.ser.reset_input_buffer()
        full_cmd = cmd + '\n'
        if self.debug:
            logger.debug(f"发送命令: {full_cmd.strip()}")
        self.ser.write(full_cmd.encode())
        # 读取响应，等待一段时间确保数据完整
        time.sleep(0.05)  # 适当延时，可根据实际调整
        output = b''
        # 这里使用简单循环读取直到超时
        while True:
            chunk = self.ser.read(1024)
            if not chunk:
                break
            output += chunk
            time.sleep(0.01)  # 防止忙等
        text = output.decode('utf-8', errors='ignore')
        if self.debug:
            logger.debug(f"原始响应: {repr(text)}")
        match = re.search(r'value\s*:\s*([0-9a-fA-F]+)', text)
        if match:
            hex_str = match.group(1)
            val = int(hex_str, 16)
            if self.debug:
                logger.debug(f"解析值: {val} (0x{val:X})")
            return val
        else:
            # 写命令通常没有 value 返回
            if self.debug:
                logger.debug("命令未返回 value")
            return None

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("串口已关闭")


# ==================== 寄存器读写封装 ====================
def serdes_read_register_by_field(comm, group, macro, lane, module, offset, start_bit, width, debug=False):
    cmd = f"serdes_read_register_by_field {group} {macro} {lane} {module} 0x{offset:X} {start_bit} {width}"
    return comm.send_command(cmd)


def serdes_write_register_by_field(comm, group, macro, lane, module, offset, start_bit, width, value, debug=False):
    cmd = f"serdes_write_register_by_field {group} {macro} {lane} {module} 0x{offset:X} {start_bit} {width} {value}"
    comm.send_command(cmd)


# ==================== 调试验证接口 ====================
def debug_read(comm, group=0, macro=0, lane=0, module=3, offset=0x06C, start=0, width=9):
    """手动读寄存器，打印值和十六进制"""
    val = serdes_read_register_by_field(comm, group, macro, lane, module, offset, start, width)
    print(f"READ  lane={lane} offset=0x{offset:X} start={start} width={width}  =>  {val} (0x{val:X})")
    return val


def debug_write(comm, group=0, macro=0, lane=0, module=3, offset=0x09C, start=14, width=7, value=0):
    """手动写寄存器"""
    serdes_write_register_by_field(comm, group, macro, lane, module, offset, start, width, value)
    print(f"WRITE lane={lane} offset=0x{offset:X} start={start} width={width} value={value} (0x{value:X})")


# ==================== DSK 校准算法（带时间统计） ====================
def dsk_calibration(comm, lane, recall_num=0, debug=False):
    """
    执行 DSK 校准，并输出各阶段耗时
    """
    print(f"\n========== 开始 Lane {lane} 校准 (recall_num={recall_num}) ==========")
    overall_start = time.time()

    def timestamp(step_name, start_time=None):
        """辅助函数：打印步骤耗时"""
        if start_time is None:
            return time.time()
        elapsed = time.time() - start_time
        print(f"  [{step_name}] 耗时: {elapsed:.3f} 秒")
        return elapsed

    # ---------- (A) 初始化配置 ----------
    print("--- 初始化 ---")
    t0 = time.time()
    # a) tx_ana_dll_dsk_addr = 0xF
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 0, 8, 0xF, debug)
    # b) ovrd_en_tx_ana_dll_dsk_addr = 1
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x054, 8, 1, 1, debug)
    # c) tx_ana_dll_dsk_leg_en 初始值 = 1
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 20, 2, 1, debug)
    # d) ovrd_en_tx_ana_dll_dsk_leg_en = 1
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x054, 12, 1, 1, debug)
    # e) tx_ana_dll_dsk_fine_en 初始值 = 115 (7位)
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, 115, debug)
    # f) ovrd_en_tx_ana_dll_dsk_fine_en = 1
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x054, 11, 1, 1, debug)
    # g~i) 触发 dll_dsk_clk 脉冲
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 0, debug)
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 1, debug)
    serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 0, debug)
    time.sleep(0.01)
    init_time = timestamp("初始化", t0)

    # 循环执行校准
    for iteration in range(recall_num + 1):
        print(f"--- 校准迭代 {iteration + 1}/{recall_num + 1} ---")
        iter_start = time.time()
        cal_results = []

        # ---------- (B) 四个相位校准 ----------
        cal_types = [60, 61, 62, 63]
        phase_times = []
        for phase_idx, cal_type in enumerate(cal_types):
            print(f"  校准 Phase{phase_idx} (cal_type={cal_type})...")
            p_start = time.time()
            # 固定地址写入 lane 号和校准类型
            serdes_write_register_by_field(comm, 0, 0, 0, 1, 0x434, 0, 16, lane, debug)
            serdes_write_register_by_field(comm, 0, 0, 0, 1, 0x438, 24, 8, cal_type, debug)
            # 触发中断 irq16
            serdes_write_register_by_field(comm, 0, 0, 0, 1, 0x41C, 3, 1, 1, debug)
            serdes_read_register_by_field(comm, 0, 0, 0, 1, 0x41C, 3, 1, debug)
            # 等待中断清零
            # while True:
            #     val = serdes_read_register_by_field(comm, 0, 0, 0, 1, 0x41C, 3, 1, debug)
            #     if val == 0:
            #         break
            #     time.sleep(0.001)

            # 启动 SSM
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x028, 7, 1, 1, debug)
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x010, 6, 1, 1, debug)
            # serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x028, 6, 1, debug)
            # 等待 ssm_done
            # while True:
            #     done = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x028, 6, 1, debug)
            #     if done == 1:
            #         break
            #     time.sleep(0.001)
            # 结束 SSM
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x028, 7, 1, 0, debug)
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x010, 6, 1, 1, debug)

            # 读取校准结果
            code = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x06C, 0, 9, debug)
            cal_results.append(code)
            print(f"      校准结果 = {code} (0x{code:X})")
            phase_time = time.time() - p_start
            phase_times.append(phase_time)
            print(f"      此相位耗时: {phase_time:.3f} 秒")

        # ---------- (C) 计算平均值和 PwCalCode ----------
        print("--- 计算与调整 ---")
        calc_start = time.time()
        avg = sum(cal_results) / len(cal_results)
        threshold = avg - 4
        pw_code = 0
        for i, code in enumerate(cal_results):
            if code >= threshold:
                pw_code |= (1 << i)
        print(f"  平均值 = {avg:.2f}, 阈值 = {threshold:.2f}, PwCalCode = 0b{pw_code:04b}")
        calc_time = timestamp("计算 PwCalCode", calc_start)

        # 查表调整 fine_en
        adjust_table = {
            0b1111: [0, 0, 0, 0],
            0b1110: [0, 0, 0, -1],
            0b1101: [0, 0, -1, 0],
            0b1001: [0, -1, -1, 0],
        }
        adjust = adjust_table.get(pw_code, [0, 0, 0, 0])

        # 读取当前 leg_en 和 fine_en
        read_start = time.time()
        cur_leg = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x09C, 20, 2, debug)
        cur_fine = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, debug)
        read_time = timestamp("读取当前状态", read_start)
        print(f"  调整前 leg_en={cur_leg}, fine_en={cur_fine}")

        # 对每个相位应用调整
        adjust_start = time.time()
        for phase_idx, delta in enumerate(adjust):
            if delta != 0:
                serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 0, 8, 1 << phase_idx, debug)
                new_fine = cur_fine + delta
                new_fine = max(0, min(127, new_fine))
                serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, new_fine, debug)
                serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 0, debug)
                serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 1, debug)
                serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 0, debug)
                time.sleep(0.01)
                print(f"      Phase{phase_idx} fine_en 调整为 {new_fine}")
        adjust_time = timestamp("调整 fine_en", adjust_start)

        # 边界调整
        boundary_start = time.time()
        cur_leg = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x09C, 20, 2, debug)
        cur_fine = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, debug)
        print(f"  边界检查前 leg_en={cur_leg}, fine_en={cur_fine}")
        if cur_leg == 0 and cur_fine < 15:
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 20, 2, 1, debug)
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, 127, debug)
            print("  边界调整: leg=0, fine<15 -> leg=1, fine=127")
        elif cur_leg == 1 and cur_fine > 127:
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 20, 2, 0, debug)
            serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, 15, debug)
            print("  边界调整: leg=1, fine>127 -> leg=0, fine=15")
        # 触发更新
        serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 0, debug)
        serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 1, debug)
        serdes_write_register_by_field(comm, 0, 0, lane, 3, 0x1A8, 0, 1, 0, debug)
        time.sleep(0.01)
        boundary_time = timestamp("边界调整", boundary_start)

        # 回显最终状态
        final_leg = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x09C, 20, 2, debug)
        final_fine = serdes_read_register_by_field(comm, 0, 0, lane, 3, 0x09C, 14, 7, debug)
        print(f"  迭代结束: leg_en={final_leg}, fine_en={final_fine}")

        iter_total = time.time() - iter_start
        print(f"--- 本次迭代总耗时: {iter_total:.3f} 秒 ---")
        print(
            f"   其中相位校准耗时: {sum(phase_times):.3f} 秒 (各相位: {', '.join([f'{t:.3f}' for t in phase_times])})")
        print(f"   计算/调整/边界耗时: {calc_time + adjust_time + boundary_time:.3f} 秒")

    overall = time.time() - overall_start
    print(f"========== Lane {lane} 校准完成，总耗时: {overall:.3f} 秒 ==========\n")


# ==================== 主程序 ====================
def main():
    # 初始化串口，开启调试模式（debug=True）
    comm = SerdesComm(port='COM4', baudrate=115200, timeout=2, debug=False)

    try:
        # 示例：对 Lane0 执行一次校准，recall_num=0，开启详细调试输出
        dsk_calibration(comm, lane=0, recall_num=0, debug=True)

        # 如果需要进行手动验证，可以调用调试验证接口
        # 例如，读取 Lane0 的校准结果：
        # debug_read(comm, lane=0, offset=0x06C)
        # 写一个测试值到 fine_en：
        # debug_write(comm, lane=0, offset=0x09C, start=14, width=7, value=100)

    finally:
        comm.close()


if __name__ == "__main__":
    main()