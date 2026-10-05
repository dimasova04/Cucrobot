"""rename scene buttons and retire his kitchen

Revision ID: d4a91c7e2b58
Revises: c8f21a6e4b37
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a91c7e2b58"
down_revision: Union[str, Sequence[str], None] = "c8f21a6e4b37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WELCOME = (
    "in a welcome studio with a lit mirror and a sofa, "
    "she wears a black swimsuit, he stands close and looks at her"
)
WELCOME_PREVIOUS = (
    "in a backstage dressing room with a lit mirror, "
    "she wears a black swimsuit, he stands close and looks at her"
)
CASTING = (
    "at a casting, a small studio with a camera on a tripod, "
    "she wears a black swimsuit, he stands close and looks at her"
)
CASTING_PREVIOUS = (
    "inside a hotel elevator with mirrored walls, "
    "she wears a black swimsuit, he stands close and holds her waist"
)
EURO = (
    "outdoors in daylight, greenery behind. Из переднего плана протянута рука с купюрами евро. "
    "Она смотрит на деньги. Она в черной кожаной куртке и черном бюстгалтере. Она улыбается. "
    "Рядом с ней только выбранный актёр, других мужчин в кадре нет. "
    "Кисть с купюрами обрезана краем кадра: без лица, плеча и тела. "
    "Её руки и плечи как на её фото, обычные, не накачанные. "
    "The only man is the actor from the actor reference. "
    "Do not add a man from the location photos. Do not give her his arms or muscles."
)
EURO_PREVIOUS = (
    "outdoors in daylight, greenery behind. Из переднего плана протянута рука с купюрами евро. "
    "Она смотрит на деньги. Она в черной кожаной куртке и черном бюстгалтере. Она  улыбается. "
    "The man beside her is the actor from the actor reference, not a different man. "
    "The hand with the notes is only a foreground hand, not a third person."
)


def _rename(old: str, new: str, prompt: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE scenes SET name = :new_name, prompt = :prompt WHERE name = :old_name"),
        {"old_name": old, "new_name": new, "prompt": prompt},
    )


def upgrade() -> None:
    _rename("Гримёрка", "Велкам-студия", WELCOME)
    _rename("Лифт отеля", "На кастинге", CASTING)
    _rename("За 1000 евро", "За 1000 евро", EURO)
    op.get_bind().execute(
        sa.text("UPDATE scenes SET is_active = false WHERE name = :name"),
        {"name": "Его кухня"},
    )


def downgrade() -> None:
    _rename("Велкам-студия", "Гримёрка", WELCOME_PREVIOUS)
    _rename("На кастинге", "Лифт отеля", CASTING_PREVIOUS)
    _rename("За 1000 евро", "За 1000 евро", EURO_PREVIOUS)
    op.get_bind().execute(
        sa.text("UPDATE scenes SET is_active = true WHERE name = :name"),
        {"name": "Его кухня"},
    )
