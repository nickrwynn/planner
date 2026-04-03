from __future__ import annotations

from app.db.base_class import Base

# Import models for Alembic autogenerate (avoid circular imports by keeping Base separate)
from app.models.user import User  # noqa: E402,F401
from app.models.course import Course  # noqa: E402,F401
from app.models.task import Task  # noqa: E402,F401
from app.models.resource import Resource  # noqa: E402,F401
from app.models.resource_chunk import ResourceChunk  # noqa: E402,F401
from app.models.notebook import Notebook  # noqa: E402,F401
from app.models.note_document import NoteDocument  # noqa: E402,F401
from app.models.note_page import NotePage  # noqa: E402,F401
from app.models.ai_conversation import AIConversation  # noqa: E402,F401
from app.models.ai_message import AIMessage  # noqa: E402,F401
from app.models.study_artifact import StudyArtifact  # noqa: E402,F401
from app.models.background_job import BackgroundJob  # noqa: E402,F401
from app.models.dead_letter_job import DeadLetterJob  # noqa: E402,F401
from app.models.ai_usage_log import AIUsageLog  # noqa: E402,F401
from app.models.resource_lifecycle_event import ResourceLifecycleEvent  # noqa: E402,F401

