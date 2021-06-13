# DO NOT modify this file by hand, changes will be overwritten
import sys
from dataclasses import dataclass
from inspect import getmembers, isclass
from typing import (
    AbstractSet,
    Any,
    Generic,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
)

from cloudformation_cli_python_lib.interface import (
    BaseModel,
    BaseResourceHandlerRequest,
)
from cloudformation_cli_python_lib.recast import recast_object
from cloudformation_cli_python_lib.utils import deserialize_list

T = TypeVar("T")


def set_or_none(value: Optional[Sequence[T]]) -> Optional[AbstractSet[T]]:
    if value:
        return set(value)
    return None


@dataclass
class ResourceHandlerRequest(BaseResourceHandlerRequest):
    # pylint: disable=invalid-name
    desiredResourceState: Optional["ResourceModel"]
    previousResourceState: Optional["ResourceModel"]


@dataclass
class ResourceModel(BaseModel):
    Name: Optional[str]
    Id: Optional[str]
    IP: Optional[str]
    URL: Optional[str]
    SubnetId: Optional[str]
    SecurityGroupIds: Optional[Sequence[str]]
    Role: Optional[str]
    PolicyArn: Optional[str]
    InstanceProfile: Optional[str]

    @classmethod
    def _deserialize(
        cls: Type["_ResourceModel"],
        json_data: Optional[Mapping[str, Any]],
    ) -> Optional["_ResourceModel"]:
        if not json_data:
            return None
        dataclasses = {n: o for n, o in getmembers(sys.modules[__name__]) if isclass(o)}
        recast_object(cls, json_data, dataclasses)
        return cls(
            Name=json_data.get("Name"),
            Id=json_data.get("Id"),
            IP=json_data.get("IP"),
            URL=json_data.get("URL"),
            SubnetId=json_data.get("SubnetId"),
            SecurityGroupIds=json_data.get("SecurityGroupIds"),
            Role=json_data.get("Role"),
            PolicyArn=json_data.get("PolicyArn"),
            InstanceProfile=json_data.get("InstanceProfile"),
        )


# work around possible type aliasing issues when variable has same name as a model
_ResourceModel = ResourceModel


