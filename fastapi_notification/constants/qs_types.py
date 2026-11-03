from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Sequence, Union

if TYPE_CHECKING:

    class ContentObject(Protocol):
        @property
        def id(self) -> object: ...

else:
    ContentObject = object

# Identity objects belong to the host application. The package only relies on
# the configured IdentityAdapter to extract their identifiers.
Recipient = Optional[Any]
Recipients = Optional[Union[Any, Sequence[Any]]]
Groups = Optional[Union[Any, Sequence[Any]]]
OptConditions = Optional[Sequence[Any]]
Link = Optional[str]
Actor = Any
Target = Optional[Any]
ActionObject = Optional[Any]
Data = Optional[Dict[str, Any]]
Description = Optional[str]
Rows = List[Dict[str, Any]]
