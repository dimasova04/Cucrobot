"""short English scene prompts for SDXL

Revision ID: c7a41e8b2d90
Revises: b4c8e2a71f05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7a41e8b2d90"
down_revision: Union[str, Sequence[str], None] = "b4c8e2a71f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMPTS = {
    "Яхта": (
        "on a luxury yacht deck at sea, sunny day, woman in a dark bikini, smiling, man beside her",
        "on the deck of a luxury yacht at sea, sunny day. Она в темном бикини. Она улыбается",
    ),
    "Ночной клуб": (
        "night club, neon lights, crowd behind, full body, woman in a short go-go dress, smiling, "
        "man in club clothes holding her hand and looking at her",
        "in a night club with neon lights and a crowd behind. Она в платье гоу-гоу, он одет в клубном стиле, "
        "держит ее за руку и смотрит на неё. Их видно в полный рост. Она улыбается.",
    ),
    "Лимузин": (
        "inside a black limousine at night, city lights in the windows, black leather seat, champagne glasses, "
        "woman in a short black dress and black heels, legs stretched across his lap, "
        "man in a dark suit and open white shirt, his hand on her ankle, they look at each other",
        "inside a black limousine at night, city lights through the side windows, black leather seat, "
        "champagne glasses on the side console. Она в коротком черном платье и черных босоножках, сидит, "
        "вытянув ноги вдоль сиденья ему на колени. Он в темном костюме и белой рубашке без галстука, "
        "его рука лежит на ее лодыжке. Смотрят друг на друга.",
    ),
    "Офис": (
        "modern office, man in a business suit sitting at a desk, woman secretary in a black mini skirt "
        "and white blouse leaning on the desk with both hands, smiling, they look at each other",
        "in a modern office. Он в деловом костюме, сидит у стола. Она секретарша, улыбается. "
        "Она  одета только в черное мини и белую блузку, опирается руками на стол. Смотрят друг на друга",
    ),
    "Съёмочная площадка": (
        "film set, dressed bedroom, studio lights on stands, camera on a tripod, cables on the floor, "
        "standing by the bed, man in hawaiian shorts, woman in black lingerie, he looks at her, she smiles",
        "on a film set in a dressed room, studio lights on stands, a camera on a tripod, cables on the floor. "
        "Он одет только в гавайские шорты. Она в черном нижнем белье. Он смотрит на неё, она улыбается. Стоят у кровати",
    ),
    "Дверь номера": (
        "hotel corridor, standing at a room door, woman in a black swimsuit holding the door handle, smiling, "
        "man holding her waist and elbow, looking at her",
        "standing at a hotel room door in a hotel corridor. Она в черном открытом купальнике. "
        "Он смотрит на нее и держит ее за талию и локоть. Она держит руками ручку двери и улыбается",
    ),
    "Кровать в белых халатах": (
        "hotel bedroom, warm evening light, white bed, man and woman sitting on the bed, both in white bathrobes",
        "in a hotel bedroom, both wearing white bathrobes, sitting on a white bed, warm evening light",
    ),
    "Селфи с размазанной тушью": (
        "close phone selfie, woman in black lingerie laughing, dark mascara in wide black streaks down both cheeks, "
        "man pressed close beside her, both looking at the camera",
        "a close phone selfie. Она в черном нижнем белье и смеётся. "
        "Тёмная тушь широкими чёрными потёками по обеим щекам, от ресниц вниз, не две маленькие точки. "
        "Он вплотную рядом с ней. Смотрят в камеру.",
    ),
    "За 1000 евро": (
        "[solo] outdoors, daylight, greenery behind, one woman alone looking at the camera, smiling, "
        "black leather jacket and black bra, a cropped hand at the frame edge holding euro banknotes, "
        "no face on that hand, her own ordinary arms, no extra person",
        "[solo] outdoors in daylight, greenery behind. Она одна в кадре и смотрит в камеру, на фотографа. "
        "Из переднего плана протянута рука с купюрами евро. Кисть обрезана краем кадра: без лица, плеча и тела, "
        "это не человек в кадре. Она в черной кожаной куртке и черном бюстгалтере. Она улыбается. "
        "Её руки и плечи как на её фото, обычные, не накачанные. No other person stands in the frame. "
        "Do not add a man from the location photos. Do not give her his arms or muscles.",
    ),
    "Утро после": (
        "morning-after selfie, one bedroom, white bathrobe over lingerie, phone in her hand, "
        "man pressed close beside her, both looking at the camera, light mascara traces only, sharp skin, "
        "no studio lights and no pool",
        "a morning-after selfie with a white bathrobe, not a tight crying close-up. "
        "Белый халат на плечах, под ним бельё, телефон в руке. Он рядом и прижимается к ней. Смотрят в камеру. "
        "Тушь только лёгкими следами, не широкими чёрными потёками по щекам. "
        "Одна комната, без софитов, камеры на штативе и бассейна. Кожа резкая, как на фото людей, не пластиковая.",
    ),
    "Велкам-студия": (
        "welcome studio, lit mirror and a sofa, woman in a black swimsuit, man standing close looking at her",
        "in a welcome studio with a lit mirror and a sofa, she wears a black swimsuit, he stands close and looks at her",
    ),
    "На кастинге": (
        "casting studio, camera on a tripod, woman in a black swimsuit, man standing close looking at her",
        "at a casting, a small studio with a camera on a tripod, she wears a black swimsuit, he stands close and looks at her",
    ),
}


def _apply(index: int) -> None:
    conn = op.get_bind()
    for name, pair in PROMPTS.items():
        conn.execute(
            sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
            {"name": name, "prompt": pair[index]},
        )


def upgrade() -> None:
    _apply(0)


def downgrade() -> None:
    _apply(1)
