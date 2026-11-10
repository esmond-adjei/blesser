"""Model registry: every process that touches the DB must import this module.

ForeignKey targets resolve lazily against ``Base.metadata``, so a missing import
only fails at flush time with ``NoReferencedTableError``.
"""

from api.applicant_kit import models as _applicant_kit_models  # noqa: F401
from api.applications import models as _application_models  # noqa: F401
from api.auth import models as _auth_models  # noqa: F401
from api.autofill import models as _autofill_models  # noqa: F401
from api.editorial import models as _editorial_models  # noqa: F401
from api.extension_auth import models as _extension_models  # noqa: F401
from api.notifications import models as _notification_models  # noqa: F401
from api.opportunities import crawl_models as _crawl_models  # noqa: F401
from api.opportunities import models as _opportunity_models  # noqa: F401
from api.scans import models as _scan_models  # noqa: F401
from api.todos import models as _todo_models  # noqa: F401
