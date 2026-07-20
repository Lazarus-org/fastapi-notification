from typing import Any, Dict, List, Optional, Sequence, Union

from fastapi_notification.models.auth import Group, User

# Type aliases used across the data access layer.
Recipient = Optional[User]
Recipients = Optional[Union[User, Sequence[User]]]
Groups = Optional[Union[Group, Sequence[Group]]]
OptConditions = Optional[Sequence[Any]]
Link = Optional[str]
Actor = Any
Target = Optional[Any]
ActionObject = Optional[Any]
Data = Optional[Dict[str, Any]]
Description = Optional[str]
Rows = List[Dict[str, Any]]
