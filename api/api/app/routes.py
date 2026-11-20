from fastapi import APIRouter

from api.applications.routes import router as applications
from api.assistant.routes import router as assistant
from api.auth.routes import router as auth
from api.matching.routes import router as matching
from api.notifications.routes import router as notifications
from api.opportunities.routes import router as opportunities
from api.scans.routes import router as scans
from api.todos.routes import router as todos

router = APIRouter()
for member_router in (auth, opportunities, matching, applications, todos, scans, notifications, assistant):
    router.include_router(member_router)
