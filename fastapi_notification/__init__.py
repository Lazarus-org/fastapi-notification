"""fastapi-notification.

A FastAPI package developed by Lazarus for efficiently handling
notifications through various APIs.

"""

from fastapi_notification.api.routers.notification import create_router
from fastapi_notification.api.routes.activity import create_activity_router
from fastapi_notification.api.routes.notification import create_notification_router
from fastapi_notification.identity import (
    BuiltInIdentityAdapter,
    IdentityAdapter,
    IdentityReference,
)
from fastapi_notification.models import (
    AuthBase,
    Base,
    ContentType,
    DeletedNotification,
    Group,
    Notification,
    NotificationCategory,
    NotificationDeduplication,
    NotificationPriority,
    NotificationPreference,
    NotificationTemplate,
    NotificationRecipient,
    NotificationSeen,
    NotificationStatus,
    Permission,
    User,
    register_content_model,
)
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.repository.manager.preferences import (
    NotificationPreferenceDataAccessLayer,
)
from fastapi_notification.repository.manager.templates import (
    NotificationTemplateDataAccessLayer,
    RenderedNotificationTemplate,
)
from fastapi_notification.settings.conf import config, configure, reset_config

__version__ = "1.0.0"

__all__ = [
    "AuthBase",
    "Base",
    "BuiltInIdentityAdapter",
    "IdentityAdapter",
    "IdentityReference",
    "ContentType",
    "DeletedNotification",
    "Group",
    "Notification",
    "NotificationCategory",
    "NotificationDeduplication",
    "NotificationPriority",
    "NotificationPreference",
    "NotificationTemplate",
    "NotificationTemplateDataAccessLayer",
    "RenderedNotificationTemplate",
    "NotificationPreferenceDataAccessLayer",
    "NotificationDataAccessLayer",
    "NotificationRecipient",
    "NotificationSeen",
    "NotificationStatus",
    "Permission",
    "User",
    "__version__",
    "config",
    "configure",
    "create_activity_router",
    "create_notification_router",
    "create_router",
    "register_content_model",
    "reset_config",
]
