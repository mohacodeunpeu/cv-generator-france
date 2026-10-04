"""réglages applicatifs (app_settings) : fournisseur IA actif, modèles, clés d'API chiffrées

Révision : 0002
Précédente : 0001
Créée le : 2026-09-27 19:40:57.602963
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Généré par `alembic revision --autogenerate` sur PostgreSQL 16, relu.
    # Les valeurs ne contiennent jamais de secret en clair (clés chiffrées Fernet, voir pai/providers/store.py).
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade() -> None:
    op.drop_table('app_settings')
