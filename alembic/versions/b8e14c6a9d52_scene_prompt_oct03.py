"""verbatim staging updates from 3 Oct prompt corrections

Revision ID: b8e14c6a9d52
Revises: f6d29b5e8c41
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8e14c6a9d52"
down_revision: Union[str, Sequence[str], None] = "f6d29b5e8c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMPTS = {
    "Яхта": (
        "on the deck of a luxury yacht at sea, sunny day. Она в темном бикини. Она улыбается",
        "on the deck of a luxury yacht at sea, sunny day. Она в темном бикини",
    ),
    "Ночной клуб": (
        "in a night club with neon lights and a crowd behind. "
        "Она в платье гоу-гоу, он одет в клубном стиле, держит ее за руку и смотрит на неё. "
        "Их видно в полный рост. Она улыбается.",
        "in a night club with neon lights and a crowd behind. "
        "Она в платье гоу-гоу, он одет в клубном стиле, держит ее за руку и смотрит на неё. "
        "Их видно в полный рост.",
    ),
    "Офис": (
        "in a modern office. Он в деловом костюме, сидит у стола. Она секретарша, улыбается. "
        "Она  одета только в черное мини и белую блузку, опирается руками на стол. Смотрят друг на друга",
        "in a modern office. Он в деловом костюме, сидит у стола. "
        "Она секретарша одета только в мини и белую блузку, опирается руками на стол. Смотрят друг на друга",
    ),
    "Съёмочная площадка": (
        "on a film set in a dressed room, studio lights on stands, a camera on a tripod, cables on the floor. "
        "Он одет только в гавайские шорты. Она в черном нижнем белье. Он смотрит на неё, она улыбается. Стоят у кровати",
        "on a film set in a dressed room, studio lights on stands, a camera on a tripod, cables on the floor. "
        "Идёт съёмка, свет и камера в кадре.",
    ),
    "Дверь номера": (
        "standing at a hotel room door in a hotel corridor. Она в черном открытом купальнике. "
        "Он смотрит на нее и держит ее за талию и локоть. Она держит руками ручку двери и улыбается",
        "standing at a hotel room door in a hotel corridor. Она в черном открытом купальнике. "
        "Он смотрит на нее и держит ее за талию и локоть. Она держит руками ручку двери",
    ),
    "За 1000 евро": (
        "outdoors in daylight, greenery behind. Из переднего плана протянута рука с купюрами евро. "
        "Она смотрит на деньги. Она в черной кожаной куртке и черном бюстгалтере. Она  улыбается. "
        "The man beside her is the actor from the actor reference, not a different man. "
        "The hand with the notes is only a foreground hand, not a third person.",
        "outdoors in daylight, greenery behind. Из переднего плана протянута рука с купюрами евро. "
        "Она смотрит на деньги.",
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
