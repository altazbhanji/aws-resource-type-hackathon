# imports
import logging
import os
import boto3

from .models import ResourceHandlerRequest, ResourceModel

from cloudformation_cli_python_lib import (
    Action,
    OperationStatus,
    ProgressEvent,
    Resource,
    exceptions,
)

# if not running in AWS, run in debug mode
if os.environ.get("AWS_EXECUTION_ENV") is not None:
    import ptvsd
    ptvsd.enable_attach(address=('0.0.0.0', 5890), redirect_output=True)
    ptvsd.wait_for_attach()

# Use this logger to forward log messages to CloudWatch Logs.
LOG = logging.getLogger(__name__)

# Set resource and test_entrypoint
TYPE_NAME = "EQ::MONITOR::NAGIOS"
resource = Resource(TYPE_NAME, ResourceModel)
test_entrypoint = resource.test_entrypoint

# =====================================
# Helper functions
# =====================================



# =====================================
# Main Resource Handlers
# =====================================
@resource.handler(Action.CREATE)
def create_handler(_, request: ResourceHandlerRequest, __) -> ProgressEvent:
    model = request.desiredResourceState
    model.Id = None
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.SUCCESS, resourceModel=model,
    )
    LOG.info(f"Starting EC2 instance")
    ec2_client = boto3.client('ec2')
    ec2_response = ec2_client.run_instances(ImageId='ami-0d5eff06f840b45e9', InstanceType='t2.small', MinCount=1, MaxCount=1)
    instance_id = ec2_response['Instances'][0]['InstanceId']
    LOG.info(f"New instance {instance_id} created successfully")
    model.Id = instance_id
    return progress

@resource.handler(Action.UPDATE)
def update_handler(_s, request: ResourceHandlerRequest, _c) -> ProgressEvent:
    model = request.desiredResourceState
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.SUCCESS, resourceModel=model,
    )
    return progress

@resource.handler(Action.DELETE)
def delete_handler(_s, request: ResourceHandlerRequest, _c) -> ProgressEvent:
    model = request.desiredResourceState
    instance_id = model.Id
    if instance_id is not None:
        ec2_client = boto3.client('ec2')
        ec2_client.terminate_instances(InstanceIds=[instance_id])
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.SUCCESS, resourceModel=model,
    )
    return progress

@resource.handler(Action.READ)
def read_handler(_s, request: ResourceHandlerRequest, _c) -> ProgressEvent:
    model = request.desiredResourceState
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.SUCCESS, resourceModel=model,
    )
    print(ResourceHandlerRequest)
    print(_)
    return progress

@resource.handler(Action.LIST)
def list_handler(_s, _r, _c):
    raise NotImplementedError("LIST handler not implemented")