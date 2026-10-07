"""solo euro scene, separate morning and mascara prompts

Revision ID: b7e2c91a4f08
Revises: d4a91c7e2b58
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c91a4f08"
down_revision: Union[str, Sequence[str], None] = "d4a91c7e2b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EURO = (
    "[solo] outdoors in daylight, greenery behind. Она одна в кадре и смотрит в камеру, на фотографа. "
    "Из переднего плана протянута рука с купюрами евро. Кисть обрезана краем кадра: без лица, плеча и тела, "
    "это не человек в кадре. Она в черной кожаной куртке и черном бюстгалтере. Она улыбается. "
    "Её руки и плечи как на её фото, обычные, не накачанные. "
    "No other person stands in the frame. Do not add a man from the location photos. Do not give her his arms or muscles."
)
EURO_PREVIOUS = (
    "outdoors in daylight, greenery behind. Из переднего плана протянута рука с купюрами евро. "
    "Она смотрит на деньги. Она в черной кожаной куртке и черном бюстгалтере. Она улыбается. "
    "Рядом с ней только выбранный актёр, других мужчин в кадре нет. "
    "Кисть с купюрами обрезана краем кадра: без лица, плеча и тела. "
    "Её руки и плечи как на её фото, обычные, не накачанные. "
    "The only man is the actor from the actor reference. "
    "Do not add a man from the location photos. Do not give her his arms or muscles."
)
MASCARA = (
    "a close phone selfie. Она в черном нижнем белье и смеётся. "
    "Тёмная тушь широкими чёрными потёками по обеим щекам, от ресниц вниз, не две маленькие точки. "
    "Он вплотную рядом с ней. Смотрят в камеру."
)
MASCARA_PREVIOUS = (
    "a close phone selfie. У неё размазана тушь под глазами. Он вплотную рядом с ней. Смотрят в камеру."
)
MORNING = (
    "a morning-after selfie with a white bathrobe, not a tight crying close-up. "
    "Белый халат на плечах, под ним бельё, телефон в руке. Он рядом и прижимается к ней. "
    "Смотрят в камеру. Тушь только лёгкими следами, не широкими чёрными потёками по щекам."
)
MORNING_PREVIOUS = (
    "a close phone selfie in the morning. У неё размазана тушь, телефон в руке. "
    "Он рядом и прижимается к ней. Смотрят в камеру."
)


def _prompt(name: str, prompt: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
        {"name": name, "prompt": prompt},
    )


def upgrade() -> None:
    _prompt("За 1000 евро", EURO)
    _prompt("Селфи с размазанной тушью", MASCARA)
    _prompt("Утро после", MORNING)


def downgrade() -> None:
    _prompt("За 1000 евро", EURO_PREVIOUS)
    _prompt("Селфи с размазанной тушью", MASCARA_PREVIOUS)
    _prompt("Утро после", MORNING_PREVIOUS)
