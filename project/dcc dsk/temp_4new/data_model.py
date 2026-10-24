"""
数据模型模块
定义了测量数据的结构和收集逻辑
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MeasurementData:
    """单次测量的数据模型"""
    group: int = 0
    macro: int = 0
    lane: int = 0

    # ATB CODE 相关字段
    vbg: float = 0.0
    tx_vreg1_vp_s: float = 0.0
    tx_vreg0_vp: float = 0.0

    # DLL 补偿 DAC 码
    dll_comp_dcc_dac_code_inpcal: int = 0
    dll_comp_dcc_dac_code_inmcal: int = 0
    tx_dll_vreg: int = 0
    inp: int = 0
    inm: int = 0
    dll_comp_dcc_dac_code_dcccal_0: int = 0
    dll_comp_dcc_dac_code_dcccal_90: int = 0
    dll_comp_dcc_dac_code_dcccal_180: int = 0
    dll_comp_dcc_dac_code_dcccal_270: int = 0

    # 电压测量值
    txm_cal_filt_out_dcc0: float = 0.0
    txm_cal_filt_out_dcc90: float = 0.0
    txm_cal_filt_out_dcc180: float = 0.0
    txm_cal_filt_out_dcc270: float = 0.0

    # COM3 指令结果
    dump_ssm_cal_result: str = ""
    dump_rx_dll_Deskew_v2: str = ""

    def to_dict(self) -> Dict:
        return {
            "group": self.group,
            "macro": self.macro,
            "lane": self.lane,
            "vbg": self.vbg,
            "tx_vreg1_vp_s": self.tx_vreg1_vp_s,
            "tx_vreg0_vp": self.tx_vreg0_vp,
            "dll_comp_dcc_dac_code (dccinpcal)": self.dll_comp_dcc_dac_code_inpcal,
            "dll_comp_dcc_dac_code (dccinmcal)": self.dll_comp_dcc_dac_code_inmcal,
            "tx_dll_vreg": self.tx_dll_vreg,
            "inp": self.inp,
            "inm": self.inm,
            "dll_comp_dcc_dac_code（dcccal 0）": self.dll_comp_dcc_dac_code_dcccal_0,
            "dll_comp_dcc_dac_code（dcccal 90）": self.dll_comp_dcc_dac_code_dcccal_90,
            "dll_comp_dcc_dac_code（dcccal 180）": self.dll_comp_dcc_dac_code_dcccal_180,
            "dll_comp_dcc_dac_code（dcccal 270）": self.dll_comp_dcc_dac_code_dcccal_270,
            "txm_cal_filt_out(dcc0)": self.txm_cal_filt_out_dcc0,
            "txm_cal_filt_out(dcc90)": self.txm_cal_filt_out_dcc90,
            "txm_cal_filt_out(dcc180)": self.txm_cal_filt_out_dcc180,
            "txm_cal_filt_out(dcc270)": self.txm_cal_filt_out_dcc270,
            "dump_ssm_cal_result": self.dump_ssm_cal_result,
            "dump_rx_dll_Deskew_v2": self.dump_rx_dll_Deskew_v2,
        }


class DataCollector:
    """数据收集器"""

    def __init__(self):
        self.channel_data: Dict[int, MeasurementData] = {}
        self._pending_md_param: Dict[int, str] = {}

    def get_or_create_channel_data(self, lane: int, macro: int = 0, group: int = 0) -> MeasurementData:
        if lane not in self.channel_data:
            self.channel_data[lane] = MeasurementData(lane=lane, macro=macro, group=group)
        return self.channel_data[lane]

    def register_pending_md(self, lane: int, param_name: str):
        self._pending_md_param[lane] = param_name

    def update_md_value(self, lane: int, raw_value: str) -> bool:
        data = self.channel_data.get(lane)
        if not data:
            return False

        param_name = self._pending_md_param.pop(lane, None)
        if not param_name:
            return False

        try:
            clean_value = raw_value.strip().replace("0x", "").replace("0X", "")
            value = int(clean_value, 16)
        except (ValueError, AttributeError):
            value = 0

        mapping = {
            "dll_comp_dcc_dac_code（inpcal）": "dll_comp_dcc_dac_code_inpcal",
            "dll_comp_dcc_dac_code（inmcal）": "dll_comp_dcc_dac_code_inmcal",
            "dll_comp_dcc_dac_code（dcccal 0）": "dll_comp_dcc_dac_code_dcccal_0",
            "dll_comp_dcc_dac_code（dcccal 90）": "dll_comp_dcc_dac_code_dcccal_90",
            "dll_comp_dcc_dac_code（dcccal 180）": "dll_comp_dcc_dac_code_dcccal_180",
            "dll_comp_dcc_dac_code（dcccal 270）": "dll_comp_dcc_dac_code_dcccal_270",


        }

        field_name = mapping.get(param_name)
        if field_name and hasattr(data, field_name):
            setattr(data, field_name, value)
            return True

        return False

    def update_voltage_value(self, lane: int, measure_point: int, voltage: float):
        data = self.channel_data.get(lane)
        if not data:
            return

        mapping = {
            1: "txm_cal_filt_out_dcc0",
            2: "txm_cal_filt_out_dcc90",
            3: "txm_cal_filt_out_dcc180",
            4: "txm_cal_filt_out_dcc270",
        }

        field_name = mapping.get(measure_point)
        if field_name and hasattr(data, field_name):
            setattr(data, field_name, voltage)

    def update_com3_result(self, lane: int, result_type: str, result: str):
        data = self.channel_data.get(lane)
        if not data:
            return

        if result_type == "dump_ssm_cal_result":
            data.dump_ssm_cal_result = result
        elif result_type == "dump_rx_dll_Deskew_v2":
            data.dump_rx_dll_Deskew_v2 = result

    def get_all_records(self) -> List[Dict]:
        records = []
        for lane in sorted(self.channel_data.keys()):
            records.append(self.channel_data[lane].to_dict())
        return records

    def clear(self):
        self.channel_data.clear()
        self._pending_md_param.clear()


# 全局数据收集器实例
global_data_collector = DataCollector()