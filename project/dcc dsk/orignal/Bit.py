"""
register_extractor.py
用于从32位寄存器值中提取地址和数据位的模块
"""


class RegisterExtractor:
    """
    寄存器位域提取器

    参数说明：
    - addr_start: 地址起始位（默认4）
    - addr_len: 地址长度（默认7）
    - data_start: 数据起始位（默认11）
    - data_len: 数据长度（默认9）
    - use_safe_method: 是否使用安全提取（处理字节跨越问题，默认True）
    """

    def __init__(self, addr_start=4, addr_len=7, data_start=11, data_len=9,
                 use_safe_method=True):
        self.addr_start = addr_start
        self.addr_len = addr_len
        self.data_start = data_start
        self.data_len = data_len
        self.use_safe_method = use_safe_method

        # 预计算掩码
        self.addr_mask = (1 << addr_len) - 1
        self.data_mask = (1 << data_len) - 1

    def extract_bitfield(self, reg_value, start, length):
        """通用位域提取"""
        if length == 0 or length > 32:
            return 0
        mask = (1 << length) - 1
        return (reg_value >> start) & mask

    def extract_data_safe(self, reg_value):
        """
        安全提取数据位（处理字节跨越问题）
        特别针对 data_start=11, data_len=9 的情况优化
        """
        # 数据位跨越 byte1 和 byte2
        # byte1: bit8-15, byte2: bit16-23

        # 提取相关字节
        byte1 = (reg_value >> 8) & 0xFF  # 第2字节
        byte2 = (reg_value >> 16) & 0xFF  # 第3字节

        # bit11-15 在 byte1 的高5位 (bit3-7)
        # bit16-19 在 byte2 的低4位 (bit0-3)
        data_low = (byte1 >> 3) & 0x1F  # 5 bits
        data_high = (byte2 & 0x0F) << 5  # 左移5位

        return data_high | data_low

    def process(self, reg_value):
        """
        处理单个寄存器值，返回提取结果

        返回字典：
        {
            'raw': 原始值,
            'addr': 地址,
            'data': 数据,
            'data_safe': 安全提取的数据
        }
        """
        if isinstance(reg_value, str):
            # 如果是十六进制字符串
            if reg_value.startswith('0x'):
                reg_value = int(reg_value, 16)
            else:
                reg_value = int(reg_value, 16)

        # 提取地址
        addr = self.extract_bitfield(reg_value, self.addr_start, self.addr_len)

        # 提取数据
        data = self.extract_bitfield(reg_value, self.data_start, self.data_len)
        data_safe = self.extract_data_safe(reg_value)

        return {
            'raw': reg_value,
            'raw_hex': f'0x{reg_value:08x}',
            'addr': addr,
            'data': data,
            'data_safe': data_safe if self.use_safe_method else data
        }

    def process_batch(self, reg_values, verbose=False):
        """
        批量处理多个寄存器值

        参数：
        - reg_values: 寄存器值列表（可以是整数或十六进制字符串）
        - verbose: 是否打印详细结果

        返回列表，每个元素是 process() 的结果
        """
        results = []
        for i, val in enumerate(reg_values):
            result = self.process(val)
            results.append(result)

            if verbose:
                diff = result['data_safe'] - result['data']
                diff_str = f" (差值: {diff:+d})" if diff != 0 else ""
                print(f"[{i:2d}] {result['raw_hex']}: "
                      f"addr={result['addr']:3d}, "
                      f"data={result['data']:3d}, "
                      f"safe={result['data_safe']:3d}{diff_str}")

        return results

    def validate_with_expected(self, reg_values, expected_data, tolerance=5):
        """
        验证提取结果与期望值的匹配度

        参数：
        - reg_values: 寄存器值列表
        - expected_data: 期望的数据值列表
        - tolerance: 允许的误差范围
        """
        results = self.process_batch(reg_values)

        print("验证结果 (允许误差 ±{}):".format(tolerance))
        print("-" * 70)
        print("原始值       地址  提取数据  安全数据  期望值  误差  状态")
        print("-" * 70)

        all_passed = True
        for i, (result, expected) in enumerate(zip(results, expected_data)):
            data_used = result['data_safe'] if self.use_safe_method else result['data']
            error = data_used - expected
            passed = abs(error) <= tolerance

            status = "✓" if passed else "✗"
            if not passed:
                all_passed = False

            print(f"{result['raw_hex']}  "
                  f"{result['addr']:3d}  "
                  f"{result['data']:6d}  "
                  f"{result['data_safe']:7d}  "
                  f"{expected:7d}  "
                  f"{error:4d}  "
                  f"{status}")

        print("-" * 70)
        print(f"总体验证: {'通过' if all_passed else '失败'}")

        return all_passed


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 创建提取器
    extractor = RegisterExtractor(addr_start=4, addr_len=7,
                                  data_start=11, data_len=9,
                                  use_safe_method=True)

    # 你的测试数据
    test_values = [
        0x3e35f90e, 0x3e38040e, 0x3e36d82e,
        0x3e35f84e, 0x3e37388e, 0x3e36010e
    ]

    expected_values = [195, 256, 219, 191, 231, 192]

    print("单个值测试:")
    result = extractor.process(test_values[0])
    print(f"原始: {result['raw_hex']}")
    print(f"地址: {result['addr']}")
    print(f"数据: {result['data']}")
    print(f"安全提取: {result['data_safe']}")
    print()

    print("批量处理:")
    extractor.process_batch(test_values, verbose=True)
    print()

    print("验证测试:")
    extractor.validate_with_expected(test_values, expected_values, tolerance=5)