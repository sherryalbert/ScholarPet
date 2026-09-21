"""Terminology support for academic communications translation.

The glossary is intentionally small and editable.  It contains terms that are
easy to mistranslate in anti-interference and wireless-communications papers;
users can add or override entries in the settings dialog.  The translation
engine receives a copy, so a UI edit never mutates the process-wide defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Dict


# Keep keys in their common English spelling.  Matching in translation.py is
# case-insensitive and longest-first, so abbreviations and multi-word entries
# are safe to use together.  These are handed to the LLM engine as preferred
# renderings and also normalise acronyms left in the output by any engine.
DEFAULT_ACADEMIC_GLOSSARY: Dict[str, str] = {
    "anti-jamming": "抗干扰",
    "anti-interference": "抗干扰",
    "anti jamming": "抗干扰",
    "interference suppression": "干扰抑制",
    "interference mitigation": "干扰缓解",
    "jamming signal": "干扰信号",
    "jamming": "压制干扰",
    "interference": "干扰",
    "spread spectrum": "扩频",
    "frequency hopping": "跳频",
    "frequency-hopping": "跳频",
    "frequency-hopping spread spectrum": "跳频扩频",
    "FHSS": "跳频扩频",
    "direct-sequence spread spectrum": "直接序列扩频",
    "direct sequence spread spectrum": "直接序列扩频",
    "DSSS": "直接序列扩频",
    "carrier frequency": "载波频率",
    "center frequency": "中心频率",
    "bandwidth": "带宽",
    "signal-to-noise ratio": "信噪比",
    "signal to noise ratio": "信噪比",
    "SNR": "信噪比",
    "signal-to-interference-plus-noise ratio": "信干噪比",
    "signal to interference plus noise ratio": "信干噪比",
    "SINR": "信干噪比",
    "signal-to-interference ratio": "信干比",
    "SIR": "信干比",
    "signal-to-jamming ratio": "信干比",
    "additive white Gaussian noise": "加性高斯白噪声",
    "AWGN": "加性高斯白噪声",
    "bit error rate": "误比特率",
    "BER": "误比特率",
    "symbol error rate": "误符号率",
    "SER": "误符号率",
    "packet error rate": "分组误码率",
    "PER": "分组误码率",
    "link budget": "链路预算",
    "waveform": "波形",
    "beamforming": "波束成形",
    "beam forming": "波束成形",
    "beamformer": "波束成形器",
    "adaptive beamforming": "自适应波束成形",
    "antenna array": "天线阵列",
    "phased array": "相控阵",
    "MIMO": "多输入多输出",
    "OFDM": "正交频分复用",
    "co-channel interference": "同频干扰",
    "adjacent-channel interference": "邻道干扰",
    "electromagnetic compatibility": "电磁兼容",
    "electromagnetic interference": "电磁干扰",
    "adaptive modulation and coding": "自适应调制编码",
    "automatic gain control": "自动增益控制",
    "error-correcting code": "纠错码",
    "error correction code": "纠错码",
    "modulation": "调制",
    "demodulation": "解调",
    "receiver": "接收机",
    "transmitter": "发射机",
    "false alarm probability": "虚警概率",
    "probability of detection": "检测概率",
    "processing gain": "处理增益",
    "channel estimation": "信道估计",
    "equalization": "均衡",
    "equalizer": "均衡器",
    "matched filter": "匹配滤波器",
    "RAKE receiver": "RAKE 接收机",
    "multipath": "多径",
    "fading": "衰落",
    "Rayleigh fading": "瑞利衰落",
    "Rician fading": "莱斯衰落",
    "diversity": "分集",
    "outage probability": "中断概率",
    "spectral efficiency": "频谱效率",
    "sum rate": "和速率",
    "power allocation": "功率分配",
    "relay": "中继",
    "cognitive radio": "认知无线电",
    "spectrum sensing": "频谱感知",
    "cyclic prefix": "循环前缀",
    "guard interval": "保护间隔",
    "pilot symbol": "导频符号",
    "convergence": "收敛",
    "closed-form solution": "闭式解",
    "convex optimization": "凸优化",
    "covariance matrix": "协方差矩阵",
    "singular value decomposition": "奇异值分解",
    "signal subspace": "信号子空间",
    "direction of arrival": "波达方向",
    "DOA": "波达方向",
    "low probability of intercept": "低截获概率",
    "LPI": "低截获概率",
}


# Corrections applied only to the bundled offline model's output.
#
# The offline engine is a small general-domain NMT model, so it produces a
# handful of very predictable renderings that are wrong for this field
# ("beamforming" -> 光束造型, "bit error rate" -> 位误率).  Substituting those
# Chinese strings in the translated text is deterministic and testable, which
# is not true of trying to inject Chinese terms into the English source: the
# model answers mixed-language input with subtitle styling tags.
#
# Keys are the model's own wording, values are the accepted terminology.  The
# user glossary is applied afterwards, so a personal rule always wins.
OFFLINE_MODEL_CORRECTIONS: Dict[str, str] = {
    "光束造型": "波束成形",
    "适应性束造型": "自适应波束成形",
    "自适应性束造型": "自适应波束成形",
    "束造型": "波束成形",
    "波束形成": "波束成形",
    "信号-干扰-加-噪声比": "信干噪比",
    "信号与干扰加噪比": "信干噪比",
    "信号干扰加噪声比": "信干噪比",
    "信号与干扰噪声比": "信干噪比",
    "信号-噪声比": "信噪比",
    "信号与噪声比": "信噪比",
    "信噪比": "信噪比",
    "频率跳跃散射频谱": "跳频扩频",
    "频率跳变扩展频谱": "跳频扩频",
    "频率跳动散射频谱": "跳频扩频",
    "位误率": "误比特率",
    "比特误差率": "误比特率",
    "误码率": "误比特率",
    "反干扰": "抗干扰",
    "反干扰能力": "抗干扰能力",
    "压制干扰": "压制干扰",
    "趋同": "收敛",
    "收敛性": "收敛性",
    "模拟结果": "仿真结果",
    "模拟显示": "仿真表明",
    "拟议的方案": "所提方案",
    "拟议方法": "所提方法",
    "部分波段": "部分频段",
    "多路访问": "多址接入",
    "到达方向": "波达方向",
    "统一的线性天线阵列": "均匀线阵",
    "均匀的线性天线阵列": "均匀线阵",
    "线性天线阵列": "天线阵列",
    "信道容量": "信道容量",
}


def default_glossary() -> dict[str, str]:
    """Return an independent copy of the built-in terminology map."""

    return dict(DEFAULT_ACADEMIC_GLOSSARY)


def offline_corrections() -> dict[str, str]:
    """Return the offline engine's output-correction table."""

    return dict(OFFLINE_MODEL_CORRECTIONS)



def normalize_glossary(value: Mapping[object, object] | None) -> dict[str, str]:
    """Validate and normalize a user glossary.

    Invalid values are rejected early with a Chinese error suitable for the
    settings dialog.  Limits prevent an accidental giant glossary from making
    an LLM request unusable.  The returned mapping is detached from *value*.
    """

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("术语表必须是键值对象")
    if len(value) > 128:
        raise ValueError("术语表最多支持 128 个词条")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise ValueError("术语表的键和值必须是文本")
        key = raw_key.strip()
        translated = raw_value.strip()
        if not key or not translated:
            raise ValueError("术语表不允许空键或空值")
        if len(key) > 160 or len(translated) > 160:
            raise ValueError("术语表单条词条不能超过 160 个字符")
        normalized[key] = translated
    return normalized


def merged_glossary(custom: Mapping[object, object] | None = None) -> dict[str, str]:
    """Merge user terms over the defaults and return a fresh dictionary."""

    result = default_glossary()
    result.update(normalize_glossary(custom))
    return result


__all__ = [
    "DEFAULT_ACADEMIC_GLOSSARY",
    "OFFLINE_MODEL_CORRECTIONS",
    "default_glossary",
    "offline_corrections",
    "normalize_glossary",
    "merged_glossary",
]
