"""appels IA : niveau du routeur (small / large / external) et request_id (page « Utilisation de l'IA »)

Révision : 0003
Précédente : 0002
Créée le : 2026-09-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Colonnes sans contenu personnel : un niveau (« small ») et un identifiant de requête aléatoire.
    op.add_column('llm_calls', sa.Column('tier', sa.String(length=12), server_default='', nullable=False))
    op.add_column('llm_calls', sa.Column('request_id', sa.String(length=64), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('llm_calls', 'request_id')
    op.drop_column('llm_calls', 'tier')
