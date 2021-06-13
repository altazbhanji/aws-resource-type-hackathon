# EQ::MONITOR::NAGIOS

Nagios monitoring server in AWS

## Syntax

To declare this entity in your AWS CloudFormation template, use the following syntax:

### JSON

<pre>
{
    "Type" : "EQ::MONITOR::NAGIOS",
    "Properties" : {
        "<a href="#name" title="Name">Name</a>" : <i>String</i>,
        "<a href="#subnetid" title="SubnetId">SubnetId</a>" : <i>String</i>,
        "<a href="#securitygroupids" title="SecurityGroupIds">SecurityGroupIds</a>" : <i>[ String, ... ]</i>,
    }
}
</pre>

### YAML

<pre>
Type: EQ::MONITOR::NAGIOS
Properties:
    <a href="#name" title="Name">Name</a>: <i>String</i>
    <a href="#subnetid" title="SubnetId">SubnetId</a>: <i>String</i>
    <a href="#securitygroupids" title="SecurityGroupIds">SecurityGroupIds</a>: <i>
      - String</i>
</pre>

## Properties

#### Name

Name of the Nagios server.

_Required_: No

_Type_: String

_Update requires_: [No interruption](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html#update-no-interrupt)

#### SubnetId

Subnet Id where server is deployed. If not specified uses default VPC and default subnet, which must exist.

_Required_: Yes

_Type_: String

_Update requires_: [Replacement](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html#update-replacement)

#### SecurityGroupIds

_Required_: No

_Type_: List of String

_Update requires_: [No interruption](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html#update-no-interrupt)

## Return Values

### Ref

When you pass the logical ID of this resource to the intrinsic `Ref` function, Ref returns the Id.

### Fn::GetAtt

The `Fn::GetAtt` intrinsic function returns a value for a specified attribute of this type. The following are the available attributes and sample return values.

For more information about using the `Fn::GetAtt` intrinsic function, see [Fn::GetAtt](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html).

#### Id

Instance Id of the nagios server.

#### IP

IP of the nagios server.

#### URL

IP of the nagios server.

#### Role

Name of the server Role

#### PolicyArn

ARN of the server Policy

#### InstanceProfile

Name of the instance profile

