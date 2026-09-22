import re

# Стемы: совпадение по началу слова (\b + стем), чтобы "страх" не ловился на "трах".
RU_STEMS = [
    "голы", "голая", "голой", "голого", "обнаж", "раздет", "нагая", "нагой", "нагиш",
    "секс", "эрот", "порно", "интим", "оргазм", "трах", "ебл", "ебат", "хуй", "пизд", "минет", "куни",
    "сосет", "сиськ", "грудь", "груди", "соск", "попк", "попа", "задниц", "ягодиц", "бикини",
    "лифчик", "трусик", "стринг", "чулк", "бдсм", "изнасил", "насил", "кровь", "труп", "убий",
]
RU_PHRASES = ["без одежды", "нижнее бель"]
EN_STEMS = [
    "nude", "naked", "topless", "undress", "lingerie", "underwear", "bikini", "panties", "sex",
    "erotic", "porn", "nsfw", "intimate", "orgasm", "fuck", "dick", "cock", "pussy", "boob",
    "breast", "nipple", "blowjob", "bdsm", "rape", "blood", "gore", "kill",
]
EN_WORDS = ["bra", "ass", "butt", "tits"]
EN_PHRASES = ["no clothes"]

_RE = re.compile(
    r"\b(?:" + "|".join(map(re.escape, RU_STEMS + EN_STEMS)) + r")"
    r"|\b(?:" + "|".join(map(re.escape, EN_WORDS)) + r")\b"
    r"|(?:" + "|".join(map(re.escape, RU_PHRASES + EN_PHRASES)) + r")",
    re.IGNORECASE,
)


def is_allowed(text: str) -> bool:
    return _RE.search(text.lower().replace("ё", "е")) is None
