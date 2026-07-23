# -*- coding: utf-8 -*-
"""
音频增强处理模块

本模块负责：
1. 音频降噪（基于频谱门控）
2. 音量标准化（调整到目标音量）
3. 回声消除（LMS 自适应滤波器）

处理流程：
输入音频 → 降噪 → 音量标准化 → 回声消除 → 输出音频
"""
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    音频处理器 - 降噪、音量标准化、回声消除

    依赖库：
    - noisereduce：降噪
    - pydub：音频处理
    - scipy：回声消除
    """

    def __init__(self):
        """初始化时检查依赖库是否可用"""
        self._check_dependencies()

    def _check_dependencies(self):
        """
        检查依赖库是否可用

        优雅降级：缺少某个库时禁用对应功能
        """
        self.has_noisereduce = False
        self.has_pydub = False
        self.has_scipy = False

        # 检查 noisereduce（降噪库）
        try:
            import noisereduce
            self.has_noisereduce = True
        except ImportError:
            logger.warning("noisereduce 未安装，降噪功能不可用。安装命令: pip install noisereduce")

        # 检查 pydub（音频处理库）
        try:
            from pydub import AudioSegment
            self.has_pydub = True
        except ImportError:
            logger.warning("pydub 未安装，音量标准化不可用。安装命令: pip install pydub")

        # 检查 scipy（科学计算库）
        try:
            import scipy.signal
            self.has_scipy = True
        except ImportError:
            logger.warning("scipy 未安装，回声消除不可用。安装命令: pip install scipy")

    def enhance_audio(self, input_path: str, output_path: str = None) -> dict:
        """
        增强音频：降噪 + 音量标准化 + 回声消除

        Args:
            input_path: 输入音频路径
            output_path: 输出音频路径（可选，默认覆盖原文件）

        Returns:
            dict: {"success": bool, "message": str, "output_path": str}
        """
        # 检查输入文件是否存在
        if not os.path.exists(input_path):
            return {"success": False, "message": f"音频文件不存在: {input_path}"}

        # 默认输出路径与输入相同
        if output_path is None:
            output_path = input_path

        try:
            # 1. 加载音频
            audio_segment = self._load_audio(input_path)
            if audio_segment is None:
                return {"success": False, "message": "无法加载音频文件"}

            # 2. 降噪（可选）
            if self.has_noisereduce:
                audio_segment = self._denoise(audio_segment)

            # 3. 音量标准化（可选）
            if self.has_pydub:
                audio_segment = self._normalize_volume(audio_segment)

            # 4. 回声消除（可选）
            if self.has_scipy:
                audio_segment = self._echo_cancellation(audio_segment)

            # 5. 导出处理后的音频
            audio_segment.export(output_path, format="wav")

            logger.info(f"音频增强完成: {output_path}")
            return {"success": True, "message": "音频增强完成", "output_path": output_path}

        except Exception as e:
            logger.error(f"音频增强失败: {e}")
            return {"success": False, "message": f"音频增强失败: {str(e)}"}

    def _load_audio(self, audio_path: str):
        """
        加载音频文件

        使用 pydub 库加载音频，支持多种格式（mp3, wav, m4a 等）
        """
        try:
            from pydub import AudioSegment
            return AudioSegment.from_file(audio_path)
        except Exception as e:
            logger.error(f"加载音频失败: {e}")
            return None

    def _echo_cancellation(self, audio_segment):
        """
        回声消除 - 使用 LMS (Least Mean Squares) 自适应滤波器

        算法原理：
        - LMS 是一种自适应滤波算法
        - 通过迭代更新滤波器系数来逼近回声路径
        - 从原始信号中减去估计的回声

        参数说明：
        - delay_ms: 预估的回声延迟（毫秒）
        - filter_length: 滤波器长度（ taps 数量）
        - mu: 步长参数（学习率）

        算法流程：
        1. 构造参考信号（延迟版本，模拟回声）
        2. 初始化滤波器权重
        3. 迭代更新权重：
           - y = w^T * x     （滤波器输出，回声估计）
           - e = d - y        （误差信号，消除回声后的信号）
           - w = w + mu * e * x （更新权重）
        """
        try:
            import scipy.signal

            # 将 pydub 音频段转为 numpy 数组
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float64)

            # 立体声转单声道
            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)

            sr = audio_segment.frame_rate
            delay_ms = 50                      # 预估回声延迟（毫秒）
            delay_samples = int(sr * delay_ms / 1000)  # 转换为采样点数
            filter_length = 128                 # 滤波器长度
            mu = 0.01                          # 步长参数（学习率）

            # 构造参考信号（延迟版本，模拟回声）
            ref = np.zeros(len(samples), dtype=np.float64)
            if delay_samples < len(samples):
                ref[delay_samples:] = samples[:-delay_samples]

            # LMS 自适应滤波
            weights = np.zeros(filter_length, dtype=np.float64)
            output = np.zeros(len(samples), dtype=np.float64)

            for i in range(filter_length, len(samples)):
                # 获取参考信号片段
                x = ref[i - filter_length:i][::-1].copy()

                # 滤波器输出（回声估计）
                y = scipy.signal.lfilter(weights, 1.0, x)[-1] if len(x) > 0 else 0.0

                # 误差信号（原始信号 - 回声估计 = 消除回声后的信号）
                e = samples[i] - y

                # 更新滤波器权重（LMS 算法）
                if not np.isnan(e) and not np.isinf(e):
                    weights += mu * e * x

                output[i] = e if (not np.isnan(e) and not np.isinf(e)) else samples[i]

            # 归一化并转回 int16
            max_val = np.max(np.abs(output)) if np.max(np.abs(output)) > 0 else 1.0
            output = (output / max_val * 32767).astype(np.int16)

            return audio_segment._spawn(output.tobytes())

        except Exception as e:
            logger.warning(f"回声消除失败，使用原始音频: {e}")
            return audio_segment

    def _denoise(self, audio_segment):
        """
        降噪处理 - 使用 noisereduce 库

        原理：基于频谱门控 (Spectral Gating)
        - 估计噪声的频谱特征
        - 在频域中抑制噪声分量
        - 逆变换回时域
        """
        try:
            import noisereduce as nr

            # 将 pydub 音频段转为 numpy 数组
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)

            # 如果是立体声，转为单声道
            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)

            # 降噪
            reduced_samples = nr.reduce_noise(y=samples, sr=audio_segment.frame_rate)

            # 转回 int16 格式
            reduced_samples = (reduced_samples * 32767).astype(np.int16)
            return audio_segment._spawn(reduced_samples.tobytes())

        except Exception as e:
            logger.warning(f"降噪失败，使用原始音频: {e}")
            return audio_segment

    def _normalize_volume(self, audio_segment, target_dbfs=-20):
        """
        音量标准化 - 使用 pydub 的 apply_gain

        原理：
        - 计算当前音频的平均音量 (dBFS)
        - 计算与目标音量的差值
        - 应用增益调整

        target_dbfs=-20 表示目标平均音量为 -20dBFS
        """
        try:
            # 计算当前音量
            current_dbfs = audio_segment.dBFS

            # 计算需要的增益
            change_in_dbfs = target_dbfs - current_dbfs

            # 应用增益
            return audio_segment.apply_gain(change_in_dbfs)
        except Exception as e:
            logger.warning(f"音量标准化失败: {e}")
            return audio_segment
