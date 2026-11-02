from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class DefaultSerializerSettings:
    notification_serializer_fields: Optional[List[str]] = field(
        default_factory=lambda: [
            "id",
            "description",
            "status",
            "category",
            "priority",
            "link",
            "timestamp",
            "expires_at",
            "template_key",
            "locale",
        ]
    )
    notification_serializer_class: Optional[str] = None
    user_serializer_fields: List[str] = field(default_factory=lambda: ["id"])
    user_serializer_class: Optional[str] = None
    group_serializer_class: Optional[str] = None


@dataclass(frozen=True)
class DefaultThrottleSettings:
    authenticated_user_throttle_rate: str = "30/minute"
    staff_user_throttle_rate: str = "100/minute"
    throttle_class: str = (
        "fastapi_notification.api.throttlings.role_base_throttle"
        ".RoleBasedUserRateThrottle"
    )


@dataclass(frozen=True)
class DefaultPaginationAndFilteringSettings:
    pagination_class: str = (
        "fastapi_notification.api.paginations.limit_offset_pagination"
        ".DefaultLimitOffSetPagination"
    )
    filterset_class: Optional[str] = None
    ordering_fields: List[str] = field(
        default_factory=lambda: [
            "id", "timestamp", "public", "category", "priority"
        ]
    )
    search_fields: List[str] = field(default_factory=lambda: ["verb", "description"])


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class DefaultAPISettings:
    identity_adapter: str = "fastapi_notification.identity.IdentityAdapter"
    include_soft_delete: bool = True
    include_hard_delete: bool = False
    allow_list: bool = True
    allow_retrieve: bool = True
    include_serializer_full_details: bool = False
    exclude_serializer_none_fields: bool = False
    extra_permission_class: Optional[str] = None


default_api_settings: DefaultAPISettings = DefaultAPISettings()
default_serializer_settings: DefaultSerializerSettings = DefaultSerializerSettings()
default_pagination_and_filter_settings: DefaultPaginationAndFilteringSettings = (
    DefaultPaginationAndFilteringSettings()
)
default_throttle_settings: DefaultThrottleSettings = DefaultThrottleSettings()
