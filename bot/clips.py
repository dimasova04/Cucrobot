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


def _solo(action: str) -> str:
    return f"[solo] indoors, full body, one adult woman. {action}"


def _pair(action: str) -> str:
    return f"indoors, full body, one adult woman and one adult man. {action}"


def _group(action: str) -> str:
    return f"indoors, full body, one adult woman and other adults only. {action}"


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
    _c("cum2", "Камшот 2 ракурса", _pair("two camera angles, the man finishes on her")),
    _c("cum_sweet", "Очень сладкий камшот", _pair("slow finish, the man comes on her body")),
    _c("bj_dragon", "Минет Развратный Дракон", _pair("she gives a blowjob in a dragon pose and looks up")),
    _c("you_top", "Ты сверху!", _pair("she is on top, moving, looking at the camera")),
    _c("bj_classic", "Классический минет", _pair("she kneels and gives a classic blowjob")),
    _c("cowgirl", "Наездница", _pair("she rides him in cowgirl")),
    _c("cowgirl2", "Наездница 2.0", _pair("she rides deeper and faster, hands on his chest")),
    _c("cowgirl_low", "Наездница снизу ⚡", _pair("low camera, she rides him in cowgirl")),
    _c("sit_on", "Садится на член ⚡", _pair("she slowly sits onto him and starts moving")),
    _c("anal", "Анал", _pair("anal sex, she looks at the camera")),
    _c("miss", "Миссионерская поза", _pair("missionary, face to face, she holds him")),
    _c("miss2", "Миссионерская 2.0", _pair("missionary, her legs on his shoulders")),
    _c("miss3", "Миссионерская 3.0", _pair("closer missionary, she looks at the camera")),
    _c("miss4", "Миссионерская 4.0", _pair("missionary from the side, slow deep movement")),
    _c("pair", "Парный секс ⚡", _pair("they have sex standing close together")),
    _c("pair_miss", "Парная миссионерская ⚡", _pair("missionary on the bed")),
    _c("miss5", "Миссионерская 5.0 ⚡", _pair("missionary, her legs wrapped around him")),
    _c("sitting", "Сидя ⚡", _pair("she sits on him face to face and moves")),
    _c("mast", "Мастурбирует ⚡", _solo("she touches herself and looks at the camera")),
    _c("anal_miss", "Анал в миссионерской ⚡", _pair("anal sex in missionary")),
    _c("legs_head", "Ноги за голову ⚡", _pair("her legs folded back by her head, he enters from the front")),
    _c("anal_stand", "Анал стоя ⚡", _pair("standing anal sex, she leans on the wall")),
    _c("cowgirl_anal", "Наездница (анал) ⚡", _pair("she rides him, anal cowgirl")),
    _c("anal_side", "Анал сбоку", _pair("anal sex, they lie on their sides")),
    _c("oil", "Попка в масле ⚡", _pair("her buttocks shine with oil, he enters from behind")),
    _c("anal_lie", "Анал лежа ⚡", _pair("she lies on her back, anal sex")),
    _c("chair", "На стуле", _pair("she sits on a chair facing him, sex on the chair")),
    _c("cowgirl_tights", "Наездница в колготках", _pair("she wears tights and rides him")),
    _c("white_stk", "В белых чулках ⚪", _pair("she wears white stockings, sex on the bed")),
    _c("black_stk", "В черных чулках ⚫", _pair("she wears black stockings, sex on the bed")),
    _c("miss_stk", "Миссионерская в чулках 🤍", _pair("missionary, she wears white stockings")),
    _c("bj_lie", "Минет: Лежа", _pair("she lies down and gives a blowjob")),
    _c("bj_side", "Минет: Со стороны", _pair("blowjob, camera from the side")),
    _c("bj_eyes", "Минет: Смотрит в глаза", _pair("she gives a blowjob and looks into his eyes")),
    _c("balls", "Сосет яйца ⚡", _pair("she licks his balls")),
    _c("bj_two", "Минет двоим", _group("one adult woman gives a blowjob to two adult men")),
    _c("sixnine", "Поза 69", _pair("69 position on the bed")),
    _c("glans", "Засунуть по гланды", _pair("she takes only the head of his penis in her mouth")),
    _c("bj_finish", "Минет с окончанием", _pair("blowjob, the man finishes in her mouth")),
    _c("bj_two2", "Минет с двумя", _group("one adult woman takes turns giving a blowjob to two adult men")),
    _c("bj_girls", "Минет от подруг", _group("two adult women pleasure her with their mouths")),
    _c("cowgirl_bj", "Наездница и минет", _group("one adult woman rides one adult man and gives a blowjob to a second")),
    _c("mouth", "Кончить в рот 💧", _pair("the man finishes in her mouth")),
    _c("anal_pov", "Анал POV", _pair("anal sex from a first-person view")),
    _c("anal_in", "Кончить в задницу ⚡", _pair("he finishes inside her during anal sex")),
    _c("cum_ass", "Камшот на попку 💧", _pair("the man finishes on her buttocks")),
    _c("cum_sides", "Камшот с двух сторон 💧", _group("two adult men finish on her from both sides")),
    _c("cum_side", "Камшот сбоку 💧", _pair("side angle, he finishes on her body")),
    _c("creampie", "Кремпай ⚡", _pair("creampie, he finishes inside and it leaks out")),
    _c("creampie2", "Кремпай 2 💧", _pair("close creampie, it leaks out of her")),
    _c("cum_heavy", "Обильный камшот на лицо 💧", _pair("a heavy finish on her face")),
    _c("cum_face", "Камшот на лицо 💧", _pair("the man finishes on her face")),
    _c("cum_pov", "Камшот POV 💧", _pair("finish on her face, first-person view")),
    _c("cum_again", "Еще один камшот 💧", _pair("another finish on her chest and face")),
    _c("enter_side", "Войти сбоку", _pair("he enters her from the side, they are lying down")),
    _c("dp", "Двойное проникновение", _group("two adult men, double penetration")),
    _c("dp_stand", "Двойное проникновение стоя", _group("two adult men, standing double penetration")),
    _c("grab_hair", "Держать за волосы", _pair("he holds her hair during sex from behind")),
    _c("doggy_wall", "Раком у стены ⚡", _pair("she bends over against the wall, he is behind her")),
    _c("doggy", "Раком", _pair("doggy style on the bed, he is behind her")),
    _c("doggy_hard", "Жестко раком", _pair("hard doggy style, she holds the bed")),
    _c("bed_hard", "Жестко на кровати", _pair("hard sex on the bed, she is underneath")),
    _c("stomach", "Лежа на животе", _pair("she lies on her stomach, he enters from behind")),
    _c("choke_doggy", "Придушить в позе раком", _pair("doggy style, his hand on her neck, she likes it and keeps breathing")),
    _c("doggy_stk", "Раком в чулках ⚫", _pair("she wears black stockings, doggy style")),
    _c("doggy_tights", "Раком в колготках 🟤", _pair("she wears tights, doggy style")),
    _c("leg_up", "Задрала ножку", _pair("she lifts one leg, he enters from behind")),
    _c("twerk_cock", "Тверкает на члене ⚡", _pair("she twerks against his penis")),
    _c("doggy_cam", "Раком лицом в камеру", _pair("doggy style, she looks at the camera")),
    _c("doggy_stand", "Раком стоя", _pair("standing doggy style")),
    _c("doggy_top", "Раком, вид сверху", _pair("doggy style, camera from above")),
    _c("doggy_stk2", "Раком в чулках 2.0 ⚫", _pair("closer, she wears black stockings, doggy style")),
    _c("hard", "Жесткий трах", _pair("hard fast sex")),
    _c("choke", "Придушить", _pair("during sex his hand rests on her neck, she likes it and keeps breathing")),
    _c("miss_tights", "В миссионерке в колготках ⚫", _pair("missionary, she wears black tights")),
    _c("face", "Лицом к лицу", _pair("face to face, slow sex")),
    _c("rub", "Трётся об член", _pair("she rubs herself against his penis")),
    _c("feet", "Мастурбация ножками", _pair("she strokes him with her feet")),
    _c("thighs", "Между ляшек ⚡", _pair("he moves between her thighs")),
    _c("show_chest", "Показывает грудь ⚡", _solo("she shows her bare chest and looks at the camera")),
    _c("show_ass", "Показывает попку", _solo("she turns and shows her buttocks")),
    _c("entry", "Эффектное вхождение", _pair("close view, he slowly enters her")),
    _c("tied", "Связана ⚡", _pair("she is tied with soft rope, consensual sex, she likes it")),
    _c("stand", "Секс стоя", _pair("standing sex against the wall")),
    _c("stand2", "Секс стоя 2.0", _pair("standing sex, he holds her up")),
    _c("group", "Групповуха", _group("one adult woman and three adult men having sex")),
    _c("hard_back", "Жестко сзади", _pair("hard sex from behind, she bends over")),
    _c("cunni", "Куни", _pair("the man gives her oral sex, she is lying down")),
    _c("solo", "Соло мастурбация", _solo("she is alone on the bed, touching herself")),
    _c("car", "Мастурбация в тачке", _solo("she is alone on a car seat, touching herself")),
    _c("tits", "Между сисек", _pair("she strokes him between her breasts")),
    _c("twerk", "Тверк попкой", _solo("she twerks toward the camera")),
    _c("trans", "Транс-девочка", _solo("one adult trans woman touching herself, looking at the camera")),
    _c("kiss", "Поцелуй", _pair("they kiss and move into sex")),
    _c("slap", "Шлепки по члену", _pair("she lightly slaps his penis with her palm")),
    _c("bj_pov", "Минет POV", _pair("blowjob, first-person view")),
    _c("bj_pov2", "Минет POV 2.0 ⚡", _pair("blowjob, first-person view, she takes him deeper")),
    _c("throat", "Горловой минет", _pair("she gives a deep throat blowjob")),
    _c("bj_bed", "Минет на кровати", _pair("blowjob on the bed, he is lying down")),
    _c("milk", "Фетиш-дойка", _solo("one adult woman expressing milk from her breast")),
    _c("cum_hands", "Окончание на руки 💧", _pair("he finishes on her hands")),
    _c("shower", "В душе", _pair("sex in the shower under the water")),
    _c("skirt", "Поднимает юбку", _solo("she lifts her skirt and shows what is underneath")),
    _c("lingerie", "В нижнем белье", _pair("she wears lace lingerie, sex on the bed")),
    _c("cum_chest", "Кончить на грудь 💧", _pair("he finishes on her chest")),
    _c("cum_doggy", "Кончить в неё раком 💧", _pair("doggy style, he finishes inside")),
    _c("facesit", "Сидит на лице", _pair("she sits on his face, looking at the camera")),
    _c("chest_close", "Грудь крупным планом", _solo("close view of her chest, she is breathing")),
    _c("cum_close", "Камшот крупным планом", _pair("close view of him finishing on her body")),
    _c("squirt", "Сквирт сверху ⚡", _solo("she is on top in the frame, squirting")),
    _c("spread", "Раздвигает булки", _solo("she spreads her buttocks with her hands and looks back")),
    _c("wet", "Мокрая киска", _solo("close view, she is wet and touching herself")),
    _c("present", "Пристроилась попкой", _pair("she presents her hips and he enters")),
    _c("morning", "С Добрый Утром ⚡", _pair("morning sex in bed, soft light")),
    _c("retry", "Попробуй ещё", _pair("another angle of the same sex, she is on top, then on her side")),
    _c("pov", "От первого лица", _pair("sex from a first-person view, she looks at the camera")),
    _c("wild", "Бурный секс", _pair("fast energetic sex on the bed")),
    _c("hard_sex", "Жесткий секс", _pair("hard sex, she grips the sheet")),
    _c("sweet", "Сладкий секс", _pair("slow gentle sex, they kiss")),
    _c("passion", "Страстный секс", _pair("passionate sex, she embraces him")),
    _c("covered", "Вся в 💧", _pair("several finishes, she is covered and looks at the camera")),
    _c("fast", "Быстрый секс", _pair("short fast sex, straight into a rhythm")),
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
