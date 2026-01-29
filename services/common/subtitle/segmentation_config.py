"""
多语言语义边界配置

定义7种语言的语义边界模式：
- 弱标点（按语言定义）
- 连词（用于语义边界判断）
- 句首词（用于语义边界判断）
- CJK语言检测
- 文本宽度计算

支持语言：中文(zh)、日语(ja)、韩语(ko)、英语(en)、德语(de)、法语(fr)、西班牙语(es)
"""

import copy
from typing import Dict, List, Set


# CJK字符Unicode范围
CJK_RANGES = [
    (0x4E00, 0x9FFF),    # CJK统一表意文字
    (0x3400, 0x4DBF),    # CJK统一表意文字扩展A
    (0x3040, 0x309F),    # 日语平假名
    (0x30A0, 0x30FF),    # 日语片假名
    (0xAC00, 0xD7AF),    # 韩语Hangul音节
    (0xFF01, 0xFF60),    # 全角ASCII和全角标点
    (0x3000, 0x303F),    # CJK符号和标点
]


def is_cjk_char(char: str) -> bool:
    """检查字符是否为CJK字符"""
    if not char or len(char) != 1:
        return False
    code = ord(char)
    for start, end in CJK_RANGES:
        if start <= code <= end:
            return True
    return False


def calculate_text_width(text: str) -> int:
    """
    计算文本显示宽度

    CJK字符宽度为2，拉丁字符宽度为1

    Args:
        text: 输入文本

    Returns:
        文本显示宽度
    """
    width = 0
    for char in text:
        if is_cjk_char(char):
            width += 2
        else:
            width += 1
    return width


class SegmentationConfig:
    """多语言语义边界配置类"""

    # 语言配置数据
    _CONFIG: Dict[str, Dict] = {
        "en": {
            "weak_punctuation": {",", ";", ":", "-", "–", "—"},
            "conjunctions": {
                "and", "but", "or", "so", "because", "since", "if", "when",
                "while", "although", "though", "however", "therefore", "thus",
                "moreover", "furthermore", "nevertheless", "otherwise", "yet",
                "unless", "whether", "once", "until", "till", "before", "after"
            },
            "sentence_starters": {
                "the", "a", "an", "this", "that", "these", "those",
                "it", "he", "she", "we", "they", "you", "i",
                "there", "here", "where", "what", "when", "why", "how",
                "who", "which", "whose", "whom",
                "my", "your", "his", "her", "its", "our", "their",
                "some", "any", "no", "every", "each", "all", "both",
                "one", "two", "first", "second", "last", "next",
                "in", "on", "at", "to", "for", "of", "with", "by",
                "from", "as", "up", "about", "into", "through", "during"
            },
            "is_cjk": False,
            "width_factor": 1,
        },
        "zh": {
            "weak_punctuation": {"，", "、", "；", "：", "—"},
            "conjunctions": {
                "和", "与", "及", "或", "但是", "但", "因为", "所以",
                "如果", "即使", "虽然", "尽管", "然而", "因此", "因而",
                "于是", "然后", "接着", "而且", "并且", "或者", "还是",
                "要么", "不仅", "不但", "除非", "无论", "不管", "不论",
                "只要", "只有", "无论", "不论", "不管", "尽管", "虽说"
            },
            "sentence_starters": {
                "这", "那", "此", "该", "某", "上", "下", "前", "后",
                "我", "你", "他", "她", "它", "我们", "你们", "他们",
                "有人", "大家", "人们", "现在", "当时", "今天", "明天",
                "这里", "那里", "哪里", "这边", "那边", "到处",
                "一", "二", "三", "第", "每", "各", "诸", "凡",
                "请", "望", "希", "建议", "认为", "觉得", "相信"
            },
            "is_cjk": True,
            "width_factor": 2,
        },
        "ja": {
            "weak_punctuation": {"、", "，", "；", "：", "-", "–", "—"},
            "conjunctions": {
                "と", "や", "および", "または", "しかし", "だが", "けれども",
                "なぜなら", "だから", "そのため", "したがって", "それで",
                "もし", "たとえ", "でも", "しかしながら", "ところが",
                "また", "そして", "および", "ならびに", "あるいは",
                "または", "それとも", "なぜならば", "というのも"
            },
            "sentence_starters": {
                "これ", "それ", "あれ", "この", "その", "あの",
                "私", "僕", "俺", "あなた", "君", "彼", "彼女",
                "私たち", "僕たち", "あなたたち", "彼ら", "彼女たち",
                "ここ", "そこ", "あそこ", "どこ", "こちら", "そちら",
                "一", "二", "三", "第", "毎", "各", "諸",
                "今日", "明日", "昨日", "今", "先", "来"
            },
            "is_cjk": True,
            "width_factor": 2,
        },
        "ko": {
            "weak_punctuation": {",", "，", ";", ":", "-", "–", "—"},
            "conjunctions": {
                "그리고", "하지만", "또는", "그래서", "왜냐하면", "만약",
                "또한", "그러나", "또는", "혹은", "아니면", "그러므로",
                "따라서", "그래서", "그러면", "그런데", "하지만", "비록",
                "尽管", "虽然", "即使", "就算", "尽管", "不管", "无论"
            },
            "sentence_starters": {
                "이", "그", "저", "이것", "그것", "저것",
                "나", "너", "그", "그녀", "우리", "당신", "그들",
                "여기", "거기", "저기", "어디",
                "한", "두", "세", "첫", "매", "각",
                "오늘", "내일", "어제", "지금", "먼저", "다음"
            },
            "is_cjk": True,
            "width_factor": 2,
        },
        "de": {
            "weak_punctuation": {",", ";", ":", "-", "–", "—"},
            "conjunctions": {
                "und", "aber", "oder", "denn", "weil", "wenn", "als",
                "obwohl", "obgleich", "trotzdem", "deshalb", "daher",
                "somit", "also", "sondern", "nicht", "nur", "sowie",
                "sowohl", "als", "auch", "weder", "noch", "entweder"
            },
            "sentence_starters": {
                "der", "die", "das", "ein", "eine", "einer", "eines",
                "dieser", "diese", "dieses", "jener", "jene", "jenes",
                "er", "sie", "es", "wir", "ihr", "sie", "ich", "du",
                "es", "hier", "dort", "wo", "was", "wann", "warum",
                "wer", "welcher", "welche", "welches", "mein", "dein"
            },
            "is_cjk": False,
            "width_factor": 1,
        },
        "fr": {
            "weak_punctuation": {",", ";", ":", "-", "–", "—", "..."},
            "conjunctions": {
                "et", "mais", "ou", "donc", "car", "parce", "que",
                "si", "quand", "lorsque", "bien", "quoique", "quoiqu",
                "cependant", "toutefois", "néanmoins", "ainsi", "donc",
                "alors", "puis", "ensuite", "après", "avant", "depuis"
            },
            "sentence_starters": {
                "le", "la", "les", "un", "une", "des", "ce", "cet",
                "cette", "ces", "il", "elle", "on", "nous", "vous",
                "ils", "elles", "je", "tu", "il", "elle", "ici", "là",
                "où", "quoi", "quand", "pourquoi", "qui", "quel",
                "quelle", "quels", "quelles", "mon", "ton", "son"
            },
            "is_cjk": False,
            "width_factor": 1,
        },
        "es": {
            "weak_punctuation": {",", ";", ":", "-", "–", "—", "..."},
            "conjunctions": {
                "y", "e", "pero", "o", "u", "porque", "pues", "ya",
                "si", "cuando", "aunque", "aun", "sin", "embargo",
                "por", "lo", "tanto", "así", "entonces", "luego",
                "después", "antes", "mientras", "hasta", "desde"
            },
            "sentence_starters": {
                "el", "la", "los", "las", "un", "una", "unos", "unas",
                "este", "esta", "estos", "estas", "ese", "esa", "esos",
                "esas", "aquel", "aquella", "aquellos", "aquellas",
                "él", "ella", "ello", "nosotros", "vosotros", "ellos",
                "ellas", "yo", "tú", "usted", "aquí", "allí", "donde",
                "qué", "cuándo", "por", "qué", "quién", "cuál", "mi"
            },
            "is_cjk": False,
            "width_factor": 1,
        },
    }

    def __init__(self):
        """初始化配置（深拷贝防止外部修改）"""
        self._config = copy.deepcopy(self._CONFIG)

    def get_weak_punctuation(self, language: str) -> Set[str]:
        """
        获取指定语言的弱标点集合

        Args:
            language: 语言代码 (e.g., 'en', 'zh', 'ja')

        Returns:
            弱标点符号集合
        """
        lang = language.lower() if language else "en"
        if lang not in self._config:
            lang = "en"  # 回退到英语
        return self._config[lang].get("weak_punctuation", set())

    def get_conjunctions(self, language: str) -> Set[str]:
        """
        获取指定语言的连词集合

        Args:
            language: 语言代码

        Returns:
            连词集合
        """
        lang = language.lower() if language else "en"
        if lang not in self._config:
            lang = "en"
        return self._config[lang].get("conjunctions", set())

    def get_sentence_starters(self, language: str) -> Set[str]:
        """
        获取指定语言的句首词集合

        Args:
            language: 语言代码

        Returns:
            句首词集合
        """
        lang = language.lower() if language else "en"
        if lang not in self._config:
            lang = "en"
        return self._config[lang].get("sentence_starters", set())

    def is_cjk_language(self, language: str) -> bool:
        """
        检查是否为CJK语言

        Args:
            language: 语言代码

        Returns:
            是否为CJK语言
        """
        lang = language.lower() if language else "en"
        if lang not in self._config:
            return False
        return self._config[lang].get("is_cjk", False)

    def get_supported_languages(self) -> List[str]:
        """
        获取支持的语言列表

        Returns:
            语言代码列表
        """
        return list(self._config.keys())

    def get_language_config(self, language: str) -> Dict:
        """
        获取指定语言的完整配置

        Args:
            language: 语言代码

        Returns:
            语言配置字典
        """
        lang = language.lower() if language else "en"
        if lang not in self._config:
            lang = "en"
        return self._config[lang].copy()

    def get_cjk_width_factor(self, language: str) -> int:
        """
        获取指定语言的字符宽度因子

        CJK语言返回2，其他返回1

        Args:
            language: 语言代码

        Returns:
            字符宽度因子
        """
        lang = language.lower() if language else "en"
        if lang not in self._config:
            return 1
        return self._config[lang].get("width_factor", 1)

    def calculate_text_width(self, text: str, language: str = None) -> int:
        """
        计算文本显示宽度

        Args:
            text: 输入文本
            language: 语言代码（可选，用于确定宽度因子）

        Returns:
            文本显示宽度
        """
        if language:
            width_factor = self.get_cjk_width_factor(language)
            if width_factor == 1:
                # 非CJK语言，按拉丁字符计算
                return len(text)

        # 使用CJK检测计算
        return calculate_text_width(text)

    def is_weak_punctuation(self, char: str, language: str) -> bool:
        """
        检查字符是否为指定语言的弱标点

        Args:
            char: 字符
            language: 语言代码

        Returns:
            是否为弱标点
        """
        weak_puncts = self.get_weak_punctuation(language)
        return char in weak_puncts

    def is_conjunction(self, word: str, language: str) -> bool:
        """
        检查单词是否为指定语言的连词

        Args:
            word: 单词
            language: 语言代码

        Returns:
            是否为连词
        """
        conjunctions = self.get_conjunctions(language)
        return word.lower() in conjunctions

    def is_sentence_starter(self, word: str, language: str) -> bool:
        """
        检查单词是否为指定语言的句首词

        Args:
            word: 单词
            language: 语言代码

        Returns:
            是否为句首词
        """
        starters = self.get_sentence_starters(language)
        return word.lower() in starters
