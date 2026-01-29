"""
缩写词识别模块
用于避免缩写中的句点被误判为句子结束
"""

COMMON_ABBREVIATIONS = frozenset({
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.",
    "u.s.", "u.k.", "u.n.", "e.u.",
    "e.g.", "i.e.", "etc.", "et al.", "vs.", "cf.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.",
    "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
    "a.m.", "p.m.", "b.c.", "a.d.", "bce", "ce",
    "vol.", "vols.", "inc.", "ltd.", "jr.", "sr.",
    "pp.", "pg.", "no.", "nos.", "fig.", "figs.",
})


def is_abbreviation(word: str) -> bool:
    if not word:
        return False
    return word.lower().strip() in COMMON_ABBREVIATIONS
