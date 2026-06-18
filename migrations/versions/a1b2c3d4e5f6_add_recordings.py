"""add recordings (NVR segments)

Revision ID: a1b2c3d4e5f6
Revises: f24da11bbd70
Create Date: 2026-06-18 17:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f24da11bbd70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recordings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('camera_id', sa.String(length=64), nullable=False),
        sa.Column('path', sa.String(length=512), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('has_motion', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_recordings_camera_id'), 'recordings', ['camera_id'], unique=False)
    op.create_index(op.f('ix_recordings_start_time'), 'recordings', ['start_time'], unique=False)
    op.create_index(op.f('ix_recordings_has_motion'), 'recordings', ['has_motion'], unique=False)
    op.create_index('ix_recordings_camera_time', 'recordings', ['camera_id', 'start_time'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_recordings_camera_time', table_name='recordings')
    op.drop_index(op.f('ix_recordings_has_motion'), table_name='recordings')
    op.drop_index(op.f('ix_recordings_start_time'), table_name='recordings')
    op.drop_index(op.f('ix_recordings_camera_id'), table_name='recordings')
    op.drop_table('recordings')
