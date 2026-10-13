"""scene buttons keep the source frame, face, figure and appearance

Revision ID: a3e91c4b7d18
Revises: c7a41e8b2d90
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3e91c4b7d18"
down_revision: Union[str, Sequence[str], None] = "c7a41e8b2d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMPTS = {
    "Яхта": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: luxury yacht deck at sea, "
        "sunny day, dark bikini, a different man beside her",
        "on a luxury yacht deck at sea, sunny day, woman in a dark bikini, smiling, man beside her",
    ),
    "Ночной клуб": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: night club, neon lights, "
        "crowd behind, short go-go dress, a different man in club clothes beside her",
        "night club, neon lights, crowd behind, full body, woman in a short go-go dress, smiling, "
        "man in club clothes holding her hand and looking at her",
    ),
    "Лимузин": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: inside a black limousine at night, "
        "city lights in the windows, black leather seat, champagne glasses, short black dress and black heels, "
        "a different man in a dark suit and an open white shirt beside her",
        "inside a black limousine at night, city lights in the windows, black leather seat, champagne glasses, "
        "woman in a short black dress and black heels, legs stretched across his lap, "
        "man in a dark suit and open white shirt, his hand on her ankle, they look at each other",
    ),
    "Офис": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: modern office, "
        "a different man in a business suit at the desk, black mini skirt and white blouse",
        "modern office, man in a business suit sitting at a desk, woman secretary in a black mini skirt "
        "and white blouse leaning on the desk with both hands, smiling, they look at each other",
    ),
    "Съёмочная площадка": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: film set, dressed bedroom, "
        "studio lights on stands, camera on a tripod, cables on the floor, hawaiian shorts on the man, "
        "black lingerie on her",
        "film set, dressed bedroom, studio lights on stands, camera on a tripod, cables on the floor, "
        "standing by the bed, man in hawaiian shorts, woman in black lingerie, he looks at her, she smiles",
    ),
    "Дверь номера": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: hotel corridor at a room door, "
        "black swimsuit, a different man beside her",
        "hotel corridor, standing at a room door, woman in a black swimsuit holding the door handle, smiling, "
        "man holding her waist and elbow, looking at her",
    ),
    "Кровать в белых халатах": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: hotel bedroom, warm evening light, "
        "white bed, both in white bathrobes",
        "hotel bedroom, warm evening light, white bed, man and woman sitting on the bed, both in white bathrobes",
    ),
    "Селфи с размазанной тушью": (
        "Keep source frame, face, figure and appearance. "
        "Only change makeup and clothes: black lingerie, "
        "dark mascara in wide black streaks down both cheeks, a different man pressed close beside her",
        "close phone selfie, woman in black lingerie laughing, dark mascara in wide black streaks down both cheeks, "
        "man pressed close beside her, both looking at the camera",
    ),
    "За 1000 евро": (
        "[solo] Keep source frame, face, figure and appearance. "
        "Only change place and clothes: outdoors, daylight, greenery behind, "
        "black leather jacket and black bra, a cropped hand at the frame edge holding euro banknotes, "
        "no face on that hand, her own ordinary arms, no extra person",
        "[solo] outdoors, daylight, greenery behind, one woman alone looking at the camera, smiling, "
        "black leather jacket and black bra, a cropped hand at the frame edge holding euro banknotes, "
        "no face on that hand, her own ordinary arms, no extra person",
    ),
    "Утро после": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: morning bedroom, "
        "white bathrobe over lingerie, a phone in her hand, a different man pressed close beside her, "
        "light mascara traces only, no studio lights and no pool",
        "morning-after selfie, one bedroom, white bathrobe over lingerie, phone in her hand, "
        "man pressed close beside her, both looking at the camera, light mascara traces only, sharp skin, "
        "no studio lights and no pool",
    ),
    "Велкам-студия": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: welcome studio, a lit mirror and a sofa, "
        "black swimsuit, a different man close beside her",
        "welcome studio, lit mirror and a sofa, woman in a black swimsuit, man standing close looking at her",
    ),
    "На кастинге": (
        "Keep source frame, face, figure and appearance. "
        "Only change place and clothes: casting studio, a camera on a tripod, "
        "black swimsuit, a different man close beside her",
        "casting studio, camera on a tripod, woman in a black swimsuit, man standing close looking at her",
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
