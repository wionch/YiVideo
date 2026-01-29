"""
SegmentationConfig 测试

测试多语言语义边界配置:
1. 弱标点配置
2. 连词配置
3. 句首词配置
4. CJK语言检测
5. 文本宽度计算
"""

import pytest

from services.common.subtitle.segmentation_config import (
    SegmentationConfig,
    is_cjk_char,
    calculate_text_width,
)


class TestSegmentationConfig:
    """测试多语言语义边界配置"""

    @pytest.fixture
    def config(self):
        return SegmentationConfig()

    def test_get_weak_punctuation_english(self, config):
        """测试英语弱标点"""
        puncts = config.get_weak_punctuation("en")
        assert "," in puncts
        assert ";" in puncts
        assert ":" in puncts
        assert "-" in puncts

    def test_get_weak_punctuation_chinese(self, config):
        """测试中文弱标点"""
        puncts = config.get_weak_punctuation("zh")
        assert "，" in puncts
        assert "。" not in puncts  # 句号是强标点
        assert "、" in puncts
        assert "；" in puncts
        assert "：" in puncts

    def test_get_weak_punctuation_japanese(self, config):
        """测试日语弱标点"""
        puncts = config.get_weak_punctuation("ja")
        assert "、" in puncts
        assert "。" not in puncts  # 句号是强标点

    def test_get_weak_punctuation_korean(self, config):
        """测试韩语弱标点"""
        puncts = config.get_weak_punctuation("ko")
        assert "," in puncts or "，" in puncts

    def test_get_weak_punctuation_german(self, config):
        """测试德语弱标点"""
        puncts = config.get_weak_punctuation("de")
        assert "," in puncts

    def test_get_weak_punctuation_french(self, config):
        """测试法语弱标点"""
        puncts = config.get_weak_punctuation("fr")
        assert "," in puncts

    def test_get_weak_punctuation_spanish(self, config):
        """测试西班牙语弱标点"""
        puncts = config.get_weak_punctuation("es")
        assert "," in puncts

    def test_get_weak_punctuation_fallback(self, config):
        """测试未知语言回退到英语"""
        puncts = config.get_weak_punctuation("unknown")
        assert "," in puncts

    def test_get_conjunctions_english(self, config):
        """测试英语连词"""
        conj = config.get_conjunctions("en")
        assert "and" in conj
        assert "but" in conj
        assert "or" in conj
        assert "so" in conj
        assert "because" in conj

    def test_get_conjunctions_chinese(self, config):
        """测试中文连词"""
        conj = config.get_conjunctions("zh")
        assert "和" in conj
        assert "但是" in conj
        assert "因为" in conj
        assert "所以" in conj

    def test_get_conjunctions_japanese(self, config):
        """测试日语连词"""
        conj = config.get_conjunctions("ja")
        assert "そして" in conj or "と" in conj

    def test_get_sentence_starters_english(self, config):
        """测试英语句首词"""
        starters = config.get_sentence_starters("en")
        assert "the" in starters
        assert "a" in starters
        assert "an" in starters
        assert "this" in starters
        assert "that" in starters
        assert "it" in starters
        assert "he" in starters
        assert "she" in starters
        assert "we" in starters
        assert "they" in starters

    def test_get_sentence_starters_chinese(self, config):
        """测试中文句首词"""
        starters = config.get_sentence_starters("zh")
        assert "这" in starters
        assert "那" in starters
        assert "我" in starters
        assert "你" in starters
        assert "他" in starters

    def test_is_cjk_language(self, config):
        """测试CJK语言检测"""
        assert config.is_cjk_language("zh") is True
        assert config.is_cjk_language("ja") is True
        assert config.is_cjk_language("ko") is True
        assert config.is_cjk_language("en") is False
        assert config.is_cjk_language("de") is False
        assert config.is_cjk_language("fr") is False
        assert config.is_cjk_language("es") is False

    def test_supported_languages(self, config):
        """测试支持的语言列表"""
        langs = config.get_supported_languages()
        assert "en" in langs
        assert "zh" in langs
        assert "ja" in langs
        assert "ko" in langs
        assert "de" in langs
        assert "fr" in langs
        assert "es" in langs
        assert len(langs) >= 7

    def test_get_language_config(self, config):
        """测试获取完整语言配置"""
        cfg = config.get_language_config("en")
        assert "weak_punctuation" in cfg
        assert "conjunctions" in cfg
        assert "sentence_starters" in cfg
        assert "is_cjk" in cfg


class TestCJKDetection:
    """测试CJK字符检测"""

    def test_is_cjk_char_chinese(self):
        """测试中文字符检测"""
        assert is_cjk_char("中") is True
        assert is_cjk_char("文") is True
        assert is_cjk_char("字") is True

    def test_is_cjk_char_japanese(self):
        """测试日语字符检测"""
        assert is_cjk_char("あ") is True  # 平假名
        assert is_cjk_char("ア") is True  # 片假名
        assert is_cjk_char("日") is True  # 汉字

    def test_is_cjk_char_korean(self):
        """测试韩语字符检测"""
        assert is_cjk_char("한") is True
        assert is_cjk_char("글") is True

    def test_is_cjk_char_latin(self):
        """测试拉丁字符不是CJK"""
        assert is_cjk_char("a") is False
        assert is_cjk_char("A") is False
        assert is_cjk_char("1") is False
        assert is_cjk_char(",") is False
        assert is_cjk_char(" ") is False

    def test_is_cjk_char_fullwidth(self):
        """测试全角标点"""
        assert is_cjk_char("。") is True
        assert is_cjk_char("，") is True
        assert is_cjk_char("！") is True


class TestTextWidthCalculation:
    """测试文本宽度计算"""

    def test_calculate_text_width_latin(self):
        """测试拉丁文本宽度"""
        # 拉丁字符宽度为1
        assert calculate_text_width("Hello") == 5
        assert calculate_text_width("Hello World") == 11

    def test_calculate_text_width_cjk(self):
        """测试CJK文本宽度"""
        # CJK字符宽度为2
        assert calculate_text_width("中文") == 4
        assert calculate_text_width("你好") == 4

    def test_calculate_text_width_mixed(self):
        """测试混合文本宽度"""
        # "Hello" (5) + " " (1) + "中文" (4) = 10
        assert calculate_text_width("Hello 中文") == 10

    def test_calculate_text_width_empty(self):
        """测试空文本"""
        assert calculate_text_width("") == 0

    def test_calculate_text_width_punctuation(self):
        """测试标点符号宽度"""
        assert calculate_text_width("Hello!") == 6  # 拉丁标点宽度1
        assert calculate_text_width("你好！") == 6  # 2+2+2=6，全角标点宽度2

    def test_calculate_text_width_with_config(self):
        """测试使用配置对象计算宽度"""
        config = SegmentationConfig()
        width = config.calculate_text_width("Hello 中文", "zh")
        assert width == 10


class TestLanguageSpecificFeatures:
    """测试语言特定功能"""

    def test_english_conjunctions_case_insensitive(self):
        """测试英语连词大小写不敏感"""
        config = SegmentationConfig()
        conj = config.get_conjunctions("en")
        # 连词应该都是小写
        assert all(c.islower() for c in conj)

    def test_chinese_punctuation_fullwidth(self):
        """测试中文标点全角"""
        config = SegmentationConfig()
        puncts = config.get_weak_punctuation("zh")
        # 中文标点应该是全角（除了可能存在的特殊字符）
        # 主要标点符号应该是全角
        fullwidth_puncts = {"，", "、", "；", "：", "—"}
        for p in fullwidth_puncts:
            assert p in puncts, f"标点 '{p}' 应该在中文弱标点集合中"
            assert ord(p) > 127, f"标点 '{p}' 应该是全角字符"

    def test_cjk_width_factor(self):
        """测试CJK宽度因子"""
        config = SegmentationConfig()
        # CJK语言字符宽度为2
        assert config.get_cjk_width_factor("zh") == 2
        assert config.get_cjk_width_factor("ja") == 2
        assert config.get_cjk_width_factor("ko") == 2
        # 非CJK语言字符宽度为1
        assert config.get_cjk_width_factor("en") == 1
        assert config.get_cjk_width_factor("de") == 1
