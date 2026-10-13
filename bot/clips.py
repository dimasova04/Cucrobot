"""Каталог видео. Сцены видны сразу и списывают кристаллики.

Ролик-образец для сцены кладётся в assets/video_refs/<id>.mp4.
Пока файла нет, сцена собирается по тексту. Когда файл появится, движение ориентируется на него.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Clip:
    id: str
    name: str
    prompt: str
    locked: bool


REFS_DIR = Path(__file__).resolve().parent.parent / "assets" / "video_refs"

# Семь рядов по две кнопки — как на страницах примера, всего девять страниц.
CLIPS_PER_PAGE = 14


# Кадр, лицо и фигура остаются с фото. Кнопка задаёт только взрослое движение.
_FACE = (
    "The woman is the adult from the source photo: same face, same figure, same appearance. "
    "Do not replace her."
)


def _solo(action: str) -> str:
    return (
        f"[solo] {_FACE} She is nude. Explicit adult scene. "
        f"Realistic sexual motion: {action}"
    )


def _pair(action: str) -> str:
    return (
        f"{_FACE} One adult man with her. Explicit adult sex, both nude. "
        f"Realistic sexual motion: {action}"
    )


def _group(action: str) -> str:
    return (
        f"{_FACE} Only other adults with her. Explicit adult sex. "
        f"Realistic sexual motion: {action}"
    )


def _c(clip_id: str, name: str, prompt: str) -> Clip:
    return Clip(clip_id, name, prompt, True)


# Обычные сцены: без подписки, одежда на месте.
SFW_CLIPS: tuple[Clip, ...] = (
    Clip(
        "walk", "Идёт к камере",
        "[solo] indoors, full body, one adult woman in a fitted dress walking toward the camera, smiling",
        False,
    ),
    Clip(
        "dance", "Танцует",
        "[solo] indoors, full body, one adult woman in a mini skirt and top dancing slowly, looking at the camera",
        False,
    ),
    Clip(
        "turn", "Поворот",
        "[solo] indoors, full body, one adult woman in tight shorts and a top turning toward the camera, smiling",
        False,
    ),
    Clip(
        "sit", "Садится",
        "[solo] indoors, a chair, full body, one adult woman in a bikini sitting down, looking at the camera",
        False,
    ),
    Clip(
        "wave", "Машет рукой",
        "[solo] outdoors, daylight, full body, one adult woman in an evening dress waving, smiling",
        False,
    ),
    Clip(
        "hair", "Поправляет волосы",
        "[solo] indoors, full body, one adult woman in a shirt and skirt fixing her hair, looking at the camera",
        False,
    ),
)

# Порядок кнопок как в примере: слева направо, потом следующая страница.
NSFW_CLIPS: tuple[Clip, ...] = (
    _c("cum2", "Камшот 2 ракурса", _pair("two angles, he pulls out and cums across her face and open mouth, she looks at the camera")),
    _c("cum_sweet", "Очень сладкий камшот", _pair("slow finish, he cums on her bare chest and stomach, she watches and smiles")),
    _c("bj_dragon", "Минет Развратный Дракон", _pair("she lies back, head off the bed, wet deep blowjob, tongue on his cock, eyes up")),
    _c("you_top", "Ты сверху!", _pair("she straddles him and rides his cock, hips rolling, eye contact")),
    _c("bj_classic", "Классический минет", _pair("she kneels, lips around his cock, slow wet blowjob, hand on the shaft")),
    _c("cowgirl", "Наездница", _pair("cowgirl, his cock inside her, she bounces and grinds, looking at the camera")),
    _c("cowgirl2", "Наездница 2.0", _pair("deeper faster cowgirl, hands on his chest, she rides his cock hard")),
    _c("cowgirl_low", "Наездница снизу ⚡", _pair("low angle, she rides his cock in cowgirl, hips and thighs moving")),
    _c("sit_on", "Садится на член ⚡", _pair("she lowers herself onto his erect cock and starts riding")),
    _c("anal", "Анал", _pair("anal sex, his cock in her ass, she looks back at the camera and pushes into him")),
    _c("miss", "Миссионерская поза", _pair("missionary, his cock thrusting into her, face to face, she holds him")),
    _c("miss2", "Миссионерская 2.0", _pair("missionary, her legs on his shoulders, deep thrusts of his cock")),
    _c("miss3", "Миссионерская 3.0", _pair("close missionary, his cock moving inside her, she looks at the camera")),
    _c("miss4", "Миссионерская 4.0", _pair("side view of missionary, slow deep thrusts, her legs open")),
    _c("pair", "Парный секс ⚡", _pair("standing sex, he holds her hips and thrusts his cock into her")),
    _c("pair_miss", "Парная миссионерская ⚡", _pair("missionary on the bed, steady thrusts, she moans and pulls him closer")),
    _c("miss5", "Миссионерская 5.0 ⚡", _pair("missionary, her legs locked around him, deep rhythmic thrusts")),
    _c("sitting", "Сидя ⚡", _pair("she sits on his cock face to face and grinds in his lap")),
    _c("mast", "Мастурбирует ⚡", _solo("she rubs her wet pussy and looks at the camera, fingers moving")),
    _c("anal_miss", "Анал в миссионерской ⚡", _pair("anal missionary, his cock in her ass, her legs open, slow deep thrusts")),
    _c("legs_head", "Ноги за голову ⚡", _pair("her legs folded by her head, he thrusts his cock into her from the front")),
    _c("anal_stand", "Анал стоя ⚡", _pair("she leans on the wall, standing anal, his cock thrusting into her ass")),
    _c("cowgirl_anal", "Наездница (анал) ⚡", _pair("anal cowgirl, she rides his cock in her ass, hands on his chest")),
    _c("anal_side", "Анал сбоку", _pair("they lie on their sides, anal sex, his cock moving in her ass")),
    _c("oil", "Попка в масле ⚡", _pair("her oiled ass shines, he thrusts into her from behind")),
    _c("anal_lie", "Анал лежа ⚡", _pair("she lies on her back, legs up, anal sex, his cock in her ass")),
    _c("chair", "На стуле", _pair("she sits facing him on a chair, bouncing on his cock")),
    _c("cowgirl_tights", "Наездница в колготках", _pair("tights pulled aside, she rides his cock in cowgirl")),
    _c("white_stk", "В белых чулках ⚪", _pair("white stockings, sex on the bed, his cock thrusting into her")),
    _c("black_stk", "В черных чулках ⚫", _pair("black stockings, sex on the bed, she wraps her legs around him")),
    _c("miss_stk", "Миссионерская в чулках 🤍", _pair("missionary in white stockings, deep thrusts, she holds his shoulders")),
    _c("bj_lie", "Минет: Лежа", _pair("she lies between his legs and gives a wet blowjob, hand stroking the shaft")),
    _c("bj_side", "Минет: Со стороны", _pair("side view of a wet blowjob, her lips sliding on his cock")),
    _c("bj_eyes", "Минет: Смотрит в глаза", _pair("blowjob, she looks into his eyes, tongue on the head of his cock")),
    _c("balls", "Сосет яйца ⚡", _pair("she licks and sucks his balls, hand stroking his cock")),
    _c("bj_two", "Минет двоим", _group("she gives a wet blowjob to two adult men, switching between their cocks")),
    _c("sixnine", "Поза 69", _pair("69 on the bed, she sucks his cock while he licks her pussy")),
    _c("glans", "Засунуть по гланды", _pair("she takes only the head of his cock in her mouth, tongue circling it")),
    _c("bj_finish", "Минет с окончанием", _pair("wet blowjob, he cums in her mouth, she swallows and looks up")),
    _c("bj_two2", "Минет с двумя", _group("she takes turns with a deep blowjob on two adult men")),
    _c("bj_girls", "Минет от подруг", _group("two adult women lick her pussy and breasts, she lies back and moves her hips")),
    _c("cowgirl_bj", "Наездница и минет", _group("she rides one adult man's cock and gives a blowjob to a second")),
    _c("mouth", "Кончить в рот 💧", _pair("he cums in her open mouth, she holds his cock and looks at the camera")),
    _c("anal_pov", "Анал POV", _pair("first-person anal, his cock thrusting into her ass, she looks back")),
    _c("anal_in", "Кончить в задницу ⚡", _pair("anal sex, he cums inside her ass and keeps moving")),
    _c("cum_ass", "Камшот на попку 💧", _pair("he pulls out and cums on her ass, she stays bent over")),
    _c("cum_sides", "Камшот с двух сторон 💧", _group("two adult men cum on her from both sides, she looks at the camera")),
    _c("cum_side", "Камшот сбоку 💧", _pair("side angle, he cums on her chest and stomach")),
    _c("creampie", "Кремпай ⚡", _pair("he cums inside her pussy, pulls out, and the creampie leaks out")),
    _c("creampie2", "Кремпай 2 💧", _pair("close creampie, cum leaking from her pussy after he pulls out")),
    _c("cum_heavy", "Обильный камшот на лицо 💧", _pair("a heavy cumshot across her face, she keeps her eyes on the camera")),
    _c("cum_face", "Камшот на лицо 💧", _pair("he cums on her face, she opens her mouth and looks up")),
    _c("cum_pov", "Камшот POV 💧", _pair("first-person view, he cums on her face")),
    _c("cum_again", "Еще один камшот 💧", _pair("another cumshot on her chest and face, she is already wet with cum")),
    _c("enter_side", "Войти сбоку", _pair("lying on their sides, he slides his cock into her and thrusts")),
    _c("dp", "Двойное проникновение", _group("two adult men, double penetration, one cock in her pussy and one in her ass")),
    _c("dp_stand", "Двойное проникновение стоя", _group("standing double penetration, two adult men holding her, both cocks inside")),
    _c("grab_hair", "Держать за волосы", _pair("he holds her hair and thrusts into her from behind, she pushes back")),
    _c("doggy_wall", "Раком у стены ⚡", _pair("she bends against the wall, he thrusts his cock into her from behind")),
    _c("doggy", "Раком", _pair("doggy on the bed, his cock thrusting into her, she grips the sheet")),
    _c("doggy_hard", "Жестко раком", _pair("hard fast doggy, he holds her hips, deep thrusts")),
    _c("bed_hard", "Жестко на кровати", _pair("hard sex on the bed, she is under him, fast deep thrusts")),
    _c("stomach", "Лежа на животе", _pair("she lies on her stomach, he thrusts into her from behind")),
    _c("choke_doggy", "Придушить в позе раком", _pair("doggy, his hand rests on her neck, consensual, she likes it and keeps breathing")),
    _c("doggy_stk", "Раком в чулках ⚫", _pair("black stockings, doggy, his cock thrusting into her")),
    _c("doggy_tights", "Раком в колготках 🟤", _pair("tights pulled aside, doggy, he thrusts from behind")),
    _c("leg_up", "Задрала ножку", _pair("she lifts one leg, he enters her from behind and thrusts")),
    _c("twerk_cock", "Тверкает на члене ⚡", _pair("she twerks her ass against his cock, then he slides in")),
    _c("doggy_cam", "Раком лицом в камеру", _pair("doggy, she looks into the camera while he thrusts")),
    _c("doggy_stand", "Раком стоя", _pair("standing doggy, she holds the wall, he thrusts into her")),
    _c("doggy_top", "Раком, вид сверху", _pair("doggy from above, his cock moving in her, her back arched")),
    _c("doggy_stk2", "Раком в чулках 2.0 ⚫", _pair("closer doggy in black stockings, deep thrusts, she looks back")),
    _c("hard", "Жесткий трах", _pair("hard fast sex, he grips her hips and pounds her")),
    _c("choke", "Придушить", _pair("during sex his hand rests on her neck, consensual, she likes it and keeps breathing")),
    _c("miss_tights", "В миссионерке в колготках ⚫", _pair("missionary in black tights pulled aside, his cock thrusting into her")),
    _c("face", "Лицом к лицу", _pair("face to face, slow deep sex, they kiss between thrusts")),
    _c("rub", "Трётся об член", _pair("she rubs her wet pussy along his cock, then he enters")),
    _c("feet", "Мастурбация ножками", _pair("she strokes his cock with both feet, looking at him")),
    _c("thighs", "Между ляшек ⚡", _pair("he thrusts his cock between her thighs, close to her pussy")),
    _c("show_chest", "Показывает грудь ⚡", _solo("she lifts her chest toward the camera, bare breasts, breathing")),
    _c("show_ass", "Показывает попку", _solo("she turns, bends, and shows her bare ass, looking back")),
    _c("entry", "Эффектное вхождение", _pair("close view, he slowly slides his cock into her pussy")),
    _c("tied", "Связана ⚡", _pair("soft rope, consensual, she likes it, he thrusts into her while she is tied")),
    _c("stand", "Секс стоя", _pair("standing sex against the wall, he holds her thigh up and thrusts")),
    _c("stand2", "Секс стоя 2.0", _pair("he holds her up, her legs around him, standing sex, his cock inside her")),
    _c("group", "Групповуха", _group("three adult men have sex with her, oral and thrusting, she stays in the center")),
    _c("hard_back", "Жестко сзади", _pair("she bends over, hard fast sex from behind, deep thrusts")),
    _c("cunni", "Куни", _pair("she lies back, he licks her wet pussy, her hips move against his mouth")),
    _c("solo", "Соло мастурбация", _solo("alone on the bed, she fingers her wet pussy and moans toward the camera")),
    _c("car", "Мастурбация в тачке", _solo("alone on a car seat, legs open, she rubs her wet pussy")),
    _c("tits", "Между сисек", _pair("she strokes his cock between her bare breasts, looking up")),
    _c("twerk", "Тверк попкой", _solo("nude, she twerks her ass toward the camera")),
    _c("trans", "Транс-девочка", _solo("one adult trans woman strokes her cock and looks at the camera")),
    _c("kiss", "Поцелуй", _pair("they kiss, then he slides his cock into her and they start thrusting")),
    _c("slap", "Шлепки по члену", _pair("she lightly slaps his cock with her palm, then strokes it")),
    _c("bj_pov", "Минет POV", _pair("first-person blowjob, her lips sliding down his cock, eyes up")),
    _c("bj_pov2", "Минет POV 2.0 ⚡", _pair("first-person blowjob, she takes his cock deeper, wet and steady")),
    _c("throat", "Горловой минет", _pair("deep throat blowjob, she takes his cock far into her mouth and pulls back")),
    _c("bj_bed", "Минет на кровати", _pair("he lies on the bed, she kneels over him and gives a wet blowjob")),
    _c("milk", "Фетиш-дойка", _solo("an adult woman squeezes her breast and milk drips, she looks at the camera")),
    _c("cum_hands", "Окончание на руки 💧", _pair("she strokes his cock and he cums on her hands")),
    _c("shower", "В душе", _pair("sex under the shower, water on their skin, he thrusts into her")),
    _c("skirt", "Поднимает юбку", _solo("she lifts her skirt, no underwear, and shows her pussy to the camera")),
    _c("lingerie", "В нижнем белье", _pair("lace lingerie pulled aside, sex on the bed, his cock thrusting into her")),
    _c("cum_chest", "Кончить на грудь 💧", _pair("he cums on her bare breasts, she holds them together")),
    _c("cum_doggy", "Кончить в неё раком 💧", _pair("doggy, he cums inside her pussy and stays pressed against her")),
    _c("facesit", "Сидит на лице", _pair("she sits on his face, he licks her pussy, she looks at the camera")),
    _c("chest_close", "Грудь крупным планом", _solo("close view of her bare breasts, she breathes and moves her chest")),
    _c("cum_close", "Камшот крупным планом", _pair("close view, he cums on her skin, thick spurts")),
    _c("squirt", "Сквирт сверху ⚡", _solo("she is above the camera and squirts, her pussy in frame")),
    _c("spread", "Раздвигает булки", _solo("she spreads her ass with both hands and looks back at the camera")),
    _c("wet", "Мокрая киска", _solo("close view, her pussy is wet, she rubs it with two fingers")),
    _c("present", "Пристроилась попкой", _pair("she presents her ass, he slides his cock in and thrusts")),
    _c("morning", "С Добрый Утром ⚡", _pair("morning sex in bed, soft light, slow thrusts, they stay under the sheet then it slips")),
    _c("retry", "Попробуй ещё", _pair("she rides his cock, then rolls onto her side and he keeps thrusting")),
    _c("pov", "От первого лица", _pair("first-person sex, she looks at the camera while his cock thrusts into her")),
    _c("wild", "Бурный секс", _pair("fast energetic sex on the bed, she holds him and moves with every thrust")),
    _c("hard_sex", "Жесткий секс", _pair("hard sex, she grips the sheet, deep fast thrusts")),
    _c("sweet", "Сладкий секс", _pair("slow sex, they kiss, his cock moves gently inside her")),
    _c("passion", "Страстный секс", _pair("passionate sex, she embraces him, rolling hips, deep thrusts")),
    _c("covered", "Вся в 💧", _pair("several cumshots, she is covered in cum and looks at the camera")),
    _c("fast", "Быстрый секс", _pair("they start thrusting immediately, short fast sex, hard rhythm")),
)

CLIPS: tuple[Clip, ...] = SFW_CLIPS + NSFW_CLIPS

_BY_ID = {item.id: item for item in CLIPS}


def clips_for(section: str) -> list[Clip]:
    """sfw — обычные, nsfw — откровенные, all — всё подряд, сначала SFW."""
    if section == "sfw":
        return list(SFW_CLIPS)
    if section == "nsfw":
        return list(NSFW_CLIPS)
    return list(CLIPS)


def get_clip(clip_id: str | None) -> Clip | None:
    if not clip_id:
        return None
    return _BY_ID.get(clip_id)


def light_clips() -> list[Clip]:
    return [item for item in CLIPS if not item.locked]


def hard_clips() -> list[Clip]:
    return [item for item in CLIPS if item.locked]


def ref_file(clip: Clip) -> Path | None:
    """Файл-образец, если его уже положили. Имя файла — id сцены."""
    path = REFS_DIR / f"{clip.id}.mp4"
    return path if path.is_file() else None
