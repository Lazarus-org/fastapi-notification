from typing import Any, Dict, List, Optional, Sequence, Union

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
