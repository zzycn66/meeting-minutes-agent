# -*- coding: utf-8 -*-
"""
说话人识别模块 - 声纹聚类

本模块实现了基于声纹特征的说话人识别（Speaker Diarization）功能，
用于将音频中的不同说话人进行分离和标注。

主要功能：
1. 音频加载与预处理
2. 语音活动检测（VAD）- 识别音频中的语音片段
3. 声纹特征提取 - 使用 resemblyzer 提取说话人嵌入向量
4. 说话人聚类 - 使用层次聚类自动识别说话人数量

依赖库：
- resemblyzer: 声纹特征提取（必需）
- scikit-learn: 聚类分析（必需）
- librosa: 音频加载与处理（必需）
- numpy: 数值计算

使用示例：
    diarizer = SpeakerDiarization()
    segments = diarizer.diarize("audio.wav")
    # 返回: [{"speaker": "Speaker_1", "start": 0.0, "end": 2.5}, ...]
"""
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)

# ==================== 常量配置 ====================
SAMPLE_RATE = 16000  # 采样率：16kHz 是语音处理的标准采样率
MIN_SEGMENT_DURATION = 0.5  # 最小语音片段时长（秒），低于此值的片段会被忽略
ENERGY_THRESHOLD = 0.01  # 能量阈值：用于 VAD 的最低能量门槛
N_MEL_CHANNELS = 40  # MFCC 特征维度：用于降级方案的简单特征提取


class SpeakerDiarization:
    """
    说话人识别类 - 基于声纹特征的聚类分析

    该类实现了完整的说话人识别流程：
    1. 检查依赖库可用性
    2. 加载并预处理音频
    3. 使用能量阈值进行语音活动检测（VAD）
    4. 提取每个语音片段的声纹嵌入向量
    5. 使用层次聚类自动识别说话人数量并分组

    属性：
        has_resemblyzer (bool): resemblyzer 库是否可用
        has_sklearn (bool): scikit-learn 库是否可用
        has_librosa (bool): librosa 库是否可用
    """

    def __init__(self):
        """
        初始化说话人识别器

        自动检查所需的依赖库是否已安装，
        如果缺少必需库会记录警告日志。
        """
        self._check_dependencies()

    def _check_dependencies(self):
        """
        检查依赖库是否可用

        检查三个必需的依赖库：
        - resemblyzer: 用于提取声纹特征向量
        - scikit-learn: 用于层次聚类分析
        - librosa: 用于音频加载和预处理

        如果缺少库，会设置对应的标志位并在日志中记录安装命令。
        """
        self.has_resemblyzer = False
        self.has_sklearn = False
        self.has_librosa = False

        try:
            from resemblyzer import VoiceEncoder
            self.has_resemblyzer = True
        except ImportError:
            logger.warning(
                "resemblyzer 未安装，说话人识别不可用。"
                "安装命令: pip install resemblyzer"
            )

        try:
            from sklearn.cluster import AgglomerativeClustering
            self.has_sklearn = True
        except ImportError:
            logger.warning(
                "scikit-learn 未安装，聚类分析不可用。"
                "安装命令: pip install scikit-learn"
            )

        try:
            import librosa
            self.has_librosa = True
        except ImportError:
            logger.warning(
                "librosa 未安装，音频加载不可用。"
                "安装命令: pip install librosa"
            )

    def diarize(self, audio_path: str) -> list:
        """
        对音频文件进行说话人识别

        这是主要的对外接口，执行完整的说话人识别流程：
        1. 验证音频文件存在性和依赖库
        2. 加载音频并进行预处理
        3. 使用 VAD 检测语音片段
        4. 提取每个片段的声纹特征
        5. 使用聚类算法识别说话人
        6. 返回带有说话人标签的时间段列表

        Args:
            audio_path (str): 音频文件路径，支持常见音频格式（wav, mp3, flac 等）

        Returns:
            list: 说话人识别结果列表，每个元素包含：
                - speaker (str): 说话人标识，格式为 "Speaker_N"
                - start (float): 开始时间（秒），保留两位小数
                - end (float): 结束时间（秒），保留两位小数
                如果识别失败，返回包含单个"未知发言人"的结果

        Raises:
            无异常抛出，所有错误都被捕获并记录到日志

        Example:
            >>> diarizer = SpeakerDiarization()
            >>> result = diarizer.diarize("meeting.wav")
            >>> print(result)
            [{'speaker': 'Speaker_1', 'start': 0.0, 'end': 2.5},
             {'speaker': 'Speaker_2', 'start': 2.8, 'end': 5.1}]
        """
        if not os.path.exists(audio_path):
            logger.error(f"音频文件不存在: {audio_path}")
            return [{"speaker": "未知发言人", "start": 0.0, "end": 0.0}]

        if not self.has_resemblyzer or not self.has_sklearn:
            logger.error("缺少必要依赖，无法进行说话人识别")
            return [{"speaker": "未知发言人", "start": 0.0, "end": 0.0}]

        try:
            audio, duration = self._load_audio(audio_path)
            if audio is None:
                return [{"speaker": "未知发言人", "start": 0.0, "end": 0.0}]

            segments = self._vad_segment(audio, duration)
            if not segments:
                return [{"speaker": "未知发言人", "start": 0.0, "end": duration}]

            embeddings = self._extract_embeddings(audio, segments)
            if len(embeddings) == 0:
                return [{"speaker": "未知发言人", "start": 0.0, "end": duration}]

            labels = self._cluster_speakers(embeddings)

            result = []
            for i, (start, end) in enumerate(segments):
                if i < len(labels):
                    speaker = f"Speaker_{labels[i] + 1}"
                else:
                    speaker = "Speaker_1"
                result.append({
                    "speaker": speaker,
                    "start": round(start, 2),
                    "end": round(end, 2),
                })

            return result

        except Exception as e:
            logger.error(f"说话人识别失败: {e}")
            return [{"speaker": "未知发言人", "start": 0.0, "end": 0.0}]

    def _load_audio(self, audio_path: str):
        """
        加载并预处理音频文件

        使用 librosa 加载音频，并进行以下预处理：
        - 重采样到 16kHz（SAMPLE_RATE）
        - 转换为单声道（mono）

        Args:
            audio_path (str): 音频文件路径

        Returns:
            tuple: (audio, duration)
                - audio (np.ndarray): 音频数据数组，采样率为 16kHz
                - duration (float): 音频时长（秒）
                如果加载失败，返回 (None, 0.0)

        Note:
            16kHz 是语音处理的标准采样率，平衡了音频质量和计算效率。
        """
        import librosa

        try:
            audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
            duration = len(audio) / SAMPLE_RATE
            return audio, duration
        except Exception as e:
            logger.error(f"加载音频失败: {e}")
            return None, 0.0

    def _vad_segment(self, audio: np.ndarray, duration: float) -> list:
        """
        基于能量的语音活动检测（VAD）分段

        使用短时能量分析来检测音频中的语音活动区域：
        1. 将音频分成重叠的帧（25ms 帧长，10ms 步长）
        2. 计算每帧的 RMS 能量
        3. 使用自适应阈值（均值的 30% 或最低阈值）判断语音/静音
        4. 合并相邻的语音片段（间隙 < 300ms）
        5. 如果语音片段太少，强制均匀分段

        Args:
            audio (np.ndarray): 音频数据数组
            duration (float): 音频总时长（秒）

        Returns:
            list: 语音片段列表，每个元素为 (start, end) 元组
                start (float): 片段开始时间（秒）
                end (float): 片段结束时间（秒）

        Note:
            帧参数说明：
            - 帧长 25ms: 捕捉语音的短期特性
            - 步长 10ms: 提供足够的时间分辨率
            - 最小片段时长 0.5s: 过滤掉太短的语音片段

        算法流程：
            原始音频 → 分帧 → 计算能量 → 阈值判断 → 合并 → 均匀分段（可选）
        """
        frame_length = int(SAMPLE_RATE * 0.025)
        hop_length = int(SAMPLE_RATE * 0.010)

        frames = []
        for i in range(0, len(audio) - frame_length + 1, hop_length):
            frame = audio[i:i + frame_length]
            energy = np.sqrt(np.mean(frame ** 2))
            frames.append(energy)

        if not frames:
            return []

        energies = np.array(frames)
        threshold = max(np.mean(energies) * 0.3, ENERGY_THRESHOLD)

        is_speech = energies > threshold

        segments = []
        start = None
        for i, speech in enumerate(is_speech):
            time = i * hop_length / SAMPLE_RATE
            if speech and start is None:
                start = time
            elif not speech and start is not None:
                if time - start >= MIN_SEGMENT_DURATION:
                    segments.append((start, time))
                start = None

        if start is not None:
            end_time = duration
            if end_time - start >= MIN_SEGMENT_DURATION:
                segments.append((start, end_time))

        if not segments:
            segments = [(0.0, duration)]

        merged = [segments[0]]
        for seg in segments[1:]:
            prev_start, prev_end = merged[-1]
            cur_start, cur_end = seg
            if cur_start - prev_end < 0.3:
                merged[-1] = (prev_start, cur_end)
            else:
                merged.append(seg)

        if len(merged) < 4 and duration > 5.0:
            merged = []
            chunk_size = duration / max(4, int(duration / 3.0))
            t = 0.0
            while t < duration:
                end = min(t + chunk_size, duration)
                merged.append((round(t, 2), round(end, 2)))
                t = end

        return merged

    def _extract_embeddings(self, audio: np.ndarray, segments: list) -> list:
        """
        使用 resemblyzer 提取声纹嵌入向量

        resemblyzer 是一个基于深度学习的声纹特征提取器，
        可以将语音片段转换为 256 维的嵌入向量，
        该向量能够有效区分不同的说话人。

        处理流程：
        1. 初始化 VoiceEncoder 模型
        2. 对每个语音片段提取嵌入向量
        3. 处理过短的片段（填充到最小长度）
        4. 如果初始化失败，降级到简单特征提取

        Args:
            audio (np.ndarray): 完整音频数据
            segments (list): 语音片段列表 [(start, end), ...]

        Returns:
            list: 嵌入向量列表，每个元素为 256 维 numpy 数组
                如果某个片段提取失败，返回全零向量

        Raises:
            无异常抛出，异常被内部捕获

        Note:
            - 每个嵌入向量为 256 维，代表说话人的声纹特征
            - 向量之间的余弦相似度可用于衡量说话人的相似性
            - 如果 resemblyzer 初始化失败，会自动降级到 MFCC 特征
        """
        from resemblyzer import VoiceEncoder

        try:
            encoder = VoiceEncoder()
        except Exception:
            logger.warning("VoiceEncoder初始化失败，使用降级方案")
            return self._extract_simple_features(audio, segments)

        embeddings = []
        for start, end in segments:
            start_sample = int(start * SAMPLE_RATE)
            end_sample = int(end * SAMPLE_RATE)
            segment_audio = audio[start_sample:end_sample]

            min_samples = int(MIN_SEGMENT_DURATION * SAMPLE_RATE)
            if len(segment_audio) < min_samples:
                pad_length = min_samples - len(segment_audio)
                segment_audio = np.pad(segment_audio, (0, pad_length))

            try:
                embedding = encoder.embed_utterance(segment_audio)
                embeddings.append(embedding)
            except Exception as e:
                logger.warning(f"提取声纹特征失败: {e}")
                embeddings.append(np.zeros(256))

        return embeddings

    def _extract_simple_features(self, audio: np.ndarray, segments: list) -> list:
        """
        降级方案：使用简单的 MFCC 频谱特征

        当 resemblyzer 无法使用时，使用 MFCC（梅尔频率倒谱系数）
        作为声纹特征的替代方案。虽然效果不如深度学习模型，
        但仍能提供基本的说话人区分能力。

        MFCC 是语音识别中常用的特征，它模拟了人耳的听觉特性：
        1. 将音频转换为梅尔频谱
        2. 取对数
        3. 进行离散余弦变换（DCT）
        4. 保留前 N_MEL_CHANNELS（40）个系数

        Args:
            audio (np.ndarray): 完整音频数据
            segments (list): 语音片段列表 [(start, end), ...]

        Returns:
            list: 特征向量列表，每个元素为 40 维 numpy 数组
                如果某个片段提取失败，返回全零向量

        Note:
            - MFCC 特征维度为 40（由 N_MEL_CHANNELS 常量控制）
            - 使用均值池化将时间序列压缩为固定长度向量
            - 该方法仅在 resemblyzer 不可用时作为备选方案
        """
        import librosa

        embeddings = []
        for start, end in segments:
            start_sample = int(start * SAMPLE_RATE)
            end_sample = int(end * SAMPLE_RATE)
            segment_audio = audio[start_sample:end_sample]

            min_samples = int(MIN_SEGMENT_DURATION * SAMPLE_RATE)
            if len(segment_audio) < min_samples:
                pad_length = min_samples - len(segment_audio)
                segment_audio = np.pad(segment_audio, (0, pad_length))

            try:
                mfcc = librosa.feature.mfcc(
                    y=segment_audio,
                    sr=SAMPLE_RATE,
                    n_mfcc=N_MEL_CHANNELS,
                )
                embedding = np.mean(mfcc, axis=1)
                embeddings.append(embedding)
            except Exception:
                embeddings.append(np.zeros(N_MEL_CHANNELS))

        return embeddings

    def _cluster_speakers(self, embeddings: list) -> list:
        """
        使用层次聚类对说话人进行分组，自动确定说话人数量

        使用凝聚层次聚类（Agglomerative Clustering）算法，
        通过轮廓系数（Silhouette Score）自动选择最佳的说话人数量。

        算法流程：
        1. 如果只有 1 个片段，返回单个说话人
        2. 如果有 2 个片段，使用余弦相似度判断是否同一人
        3. 对 2 到 min(N, 8) 个聚类数进行尝试
        4. 使用轮廓系数评估每个聚类结果
        5. 选择得分最高的聚类数（要求得分 > 0.1）
        6. 如果没有好的结果，回退到 2 个聚类

        Args:
            embeddings (list): 嵌入向量列表

        Returns:
            list: 说话人标签列表，每个元素为整数（从 0 开始）
                例如：[0, 0, 1, 1, 0] 表示前两个片段是同一人，
                中间两个是另一人，最后一个是第一个人

        Note:
            - 轮廓系数范围 [-1, 1]，越大表示聚类效果越好
            - 使用余弦度量是因为嵌入向量的方向比大小更重要
            - 最大尝试 8 个聚类，避免过度分割
            - 阈值 0.1 是经验值，过低会导致错误的说话人分割
        """
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score

        if len(embeddings) <= 1:
            return [0] * len(embeddings)

        X = np.array(embeddings)

        if len(embeddings) == 2:
            similarity = np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            )
            if similarity > 0.85:
                return [0, 0]
            else:
                return [0, 1]

        best_labels = None
        best_score = -1
        best_n = 2

        for n in range(2, min(len(embeddings), 8)):
            try:
                clustering = AgglomerativeClustering(
                    n_clusters=n,
                    metric="cosine",
                    linkage="average",
                )
                labels = clustering.fit_predict(X)
                if len(set(labels)) < 2:
                    continue
                score = silhouette_score(X, labels, metric="cosine")
                if score > best_score:
                    best_score = score
                    best_labels = labels
                    best_n = n
            except Exception:
                continue

        if best_labels is not None and best_score > 0.1:
            return best_labels.tolist()

        clustering = AgglomerativeClustering(
            n_clusters=2,
            metric="cosine",
            linkage="average",
        )
        labels = clustering.fit_predict(X)
        return labels.tolist()
