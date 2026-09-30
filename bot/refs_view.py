"""Общее для /refs и /partner: username бота и строки статистики."""
from bot import texts
from services.referrals import RefStats

_cached_username: str | None = None


async def bot_username(bot) -> str:
    """Username бота для реф-ссылок. Запрашивается у Telegram один раз."""
    global _cached_username
    if _cached_username is None:
        _cached_username = (await bot.me()).username or ""
    return _cached_username


def stats_line(st: RefStats, template: str, mark: str = "") -> str:
    return template.format(
        mark=mark,
        code=st.code,
        title=st.title,
        users=st.users,
        accepted=st.accepted,
        paying=st.paying_users,
        stars=st.stars,
        rub=st.tribute_rub,
        gens=st.generations_done,
    )


def short_line(st: RefStats) -> str:
    return stats_line(st, texts.PARTNER_STATS_LINE)
