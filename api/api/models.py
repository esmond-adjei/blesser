"""Model registry: every process that touches the DB must import this module.

ForeignKey targets resolve lazily against ``Base.metadata``, so a missing
import only fails at flush time with ``NoReferencedTableError``. Add new
``*/models.py`` modules here, not to each entry point.
"""

from api.account import models as _account_models  # noqa: F401
from api.agents import models as _agents_models  # noqa: F401
from api.applications import models as _application_models  # noqa: F401
from api.assistant import models as _assistant_models  # noqa: F401
from api.auth import models as _auth_models  # noqa: F401
from api.candidates import models as _candidate_models  # noqa: F401
from api.cv import models as _cv_models  # noqa: F401
from api.flows import models as _flow_models  # noqa: F401
from api.index import models as _index_models  # noqa: F401
from api.metering import models as _metering_models  # noqa: F401
from api.notifications import models as _notification_models  # noqa: F401
from api.opportunities import models as _opportunity_models  # noqa: F401
from api.outreach import models as _outreach_models  # noqa: F401
from api.prospects import models as _prospect_models  # noqa: F401
from api.providers import models as _providers_models  # noqa: F401
from api.runs import models as _run_models  # noqa: F401
from api.todos import models as _todo_models  # noqa: F401
from api.workspace import models as _workspace_models  # noqa: F401
