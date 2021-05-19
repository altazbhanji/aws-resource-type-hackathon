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
LOG.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)

# Set resource and test_entrypoint
TYPE_NAME = "EQ::MONITOR::NAGIOS"
resource = Resource(TYPE_NAME, ResourceModel)
test_entrypoint = resource.test_entrypoint

default_server_name = 'Nagios Server'
default_instance_type = 't2.small'
default_ssm_ami_parameter = '/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2'

# =====================================
# Helper functions
# =====================================



# =====================================
# Main Resource Handlers
# =====================================
@resource.handler(Action.CREATE)
def create_handler(_, request: ResourceHandlerRequest, __) -> ProgressEvent:

    # TODO:
    #   check permissions and/or dry run - ec2 create, ssm also check for terminate permission
    #   callback, waiting for instance to spin up
    #   handle case when subnet / security group is provided
    #   process userdata for nagios

    # initialize model
    model = request.desiredResourceState

    # get boto3 clients
    ssm_client = boto3.client('ssm')
    ec2_client = boto3.client('ec2')

    try:
        # initialize parameters
        LOG.info(f"Initializing resource parameters")
        model.Id = None
        instance_name = model.Name if model.Name != '' else default_server_name
        instance_type = default_instance_type
        # image_id comes from AWS SSM paramters that stores latest ami ids
        ssm_response = ssm_client.get_parameter(Name=default_ssm_ami_parameter)
        image_id = ssm_response['Parameter']['Value']

        # start EC2 instance
        LOG.info(f"Starting EC2 instance")
        ec2_response = ec2_client.run_instances(
                                    ImageId=image_id,
                                    InstanceType=instance_type, 
                                    MinCount=1,
                                    MaxCount=1,
                                    TagSpecifications=[{'ResourceType':'instance', 'Tags': [{'Key': 'Name', 'Value': instance_name}]}]
                                    )

        # capture and store instance id so it can be terminated
        instance_id = ec2_response['Instances'][0]['InstanceId']
        model.Id = instance_id
        LOG.info(f"New instance {instance_id} created successfully")

        # get success progress event
        progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=model)

    except Exception as err:
        # get failed progress event
        msg = f"Unexpected error creating nagios server: {type(err).__name__}: {str(err)}"
        progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)

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