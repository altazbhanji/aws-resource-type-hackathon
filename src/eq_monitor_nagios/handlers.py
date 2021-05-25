# imports
import logging
import os
import boto3

import logging
from typing import Any, MutableMapping, Optional

from cloudformation_cli_python_lib import (
    Action,
    HandlerErrorCode,
    OperationStatus,
    ProgressEvent,
    Resource,
    SessionProxy,
    exceptions,
    identifier_utils,
)

from .models import ResourceHandlerRequest, ResourceModel

# Use this logger to forward log messages to CloudWatch Logs.
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)


#     LOG.info("Waiting for debug process to attach")
#     import ptvsd
#     ptvsd.enable_attach(address=('0.0.0.0', 5890), redirect_output=True)
#     ptvsd.wait_for_attach()


# Set resource and test_entrypoint
TYPE_NAME = "EQ::MONITOR::NAGIOS"
resource = Resource(TYPE_NAME, ResourceModel)
test_entrypoint = resource.test_entrypoint

default_server_name = 'Nagios Server'
default_instance_type = 't2.small'
default_ssm_ami_parameter = '/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2'
default_callback_period = 60
default_ssm_path = '/Eq/Nagios/Monitor/Stack'


# =====================================
# Helper functions
# =====================================
def build_instance(model:ResourceModel, session):

    ssm_client = session.client('ssm')
    ec2_client = session.client('ec2')

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
        progress = ProgressEvent(status=OperationStatus.IN_PROGRESS, callbackDelaySeconds=default_callback_period, resourceModel=model)
        LOG.info(f"Returning IN_PROGRESS")

    except Exception as err:
        # get failed progress event
        msg = f"Unexpected error creating nagios server: {type(err).__name__}: {str(err)}"
        progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)
        LOG.exception(msg)

    return progress



def check_instance_state(model:ResourceModel, session):


    try:
        # use ec2 resource to get the current state
        instance_id = model.Id
        LOG.info(f"Checking state for instance {instance_id}")
        ec2_client = session.resource('ec2')
        instance = ec2_client.Instance(instance_id)
        state = instance.state
        state_code = state['Code']
        state_name = state['Name']

        # return progress event based on state
        if state_code == 16:
            # we're done
            LOG.info(f"Instance is {state_name}")
            progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=model)
            LOG.info(f"Returning SUCCESS")
        elif state_code == 0:
            # still in pending state
            LOG.info(f"Instance is {state_name}")
            msg = "Waiting for EC2 instance to stabilize"
            progress = ProgressEvent(status=OperationStatus.IN_PROGRESS, resourceModel=model, message=msg)
            LOG.info(f"Returning IN_PROGRESS")
        else:
            # something went wrong - EC2 is stopping, stopped or terminated
            LOG.info(f"Instance is {state_name}")
            msg = f"Unexpected error, instance is {state_name}"
            progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)
            LOG.info(f"Returning IN_FAILED")

    except Exception as err:
        # get failed progress event
        msg = f"Unexpected error checking state: {type(err).__name__}: {str(err)}"
        progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)
        LOG.exception(msg)

    return progress


# =====================================
# Main Resource Handlers
# =====================================
@resource.handler(Action.CREATE)
def create_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:


    # TODO:
    #   check permissions and/or dry run - ec2 create, ssm also check for terminate permission
    #   callback, waiting for instance to spin up
    #   handle case when subnet / security group is provided
    #   process userdata for nagios
    #   check if default subnet / sg exists if not provided
    #   add tags

    print("Starting create_handler")

    # initialize model
    model = request.desiredResourceState

    print(f"Model is {model}")

    # check whether this is the first call or a callback
    # first call, create instance, subsequently check instance state until ready
    if model.Id is None:
        LOG.info(f"model.Id is {model.Id}, creating instance")
        progress = build_instance(model, session)
    else:
        LOG.info(f"model.Id is {model.Id}, checking instance state")
        progress = check_instance_state(model, session)
        if progress.status == OperationStatus.SUCCESS:
            # Store server id information in SSM
            ssm_client = session.client('ssm')
            ssm_name = f"{default_ssm_path}/{request.stackId}"
            ssm_value = model.Id
            ssm_client.put_parameter(Name=ssm_name, Value=ssm_value, Type='String')

    return progress


@resource.handler(Action.UPDATE)
def update_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:

    LOG.info("Starting update_handler")

    # TODO:
    #   re-launch in a new subnet if required
    #   check tags
    desired_state = request.desiredResourceState
    current_state = request.previousResourceState

    desired_name = desired_state.Name
    current_name = current_state.Name

    if desired_name != current_name:
        instance_id = desired_state.Id
        ec2_client = session.client('ec2')
        instance = ec2_client.Instance(instance_id)
        instance.create_tags(Tags=[{'Key': 'Name', 'Value': current_name}])


    progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=desired_state)

    return progress


@resource.handler(Action.DELETE)
def delete_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:

    # TODO:
    #   wait for server to terminate

    LOG.info("Starting delete_handler")

    ssm_client = session.client('ssm')
    ssm_name = f"{default_ssm_path}/{request.stackId}"
    try:
        ssm_client.delete_parameter(Name=ssm_name)
        model = request.desiredResourceState
        instance_id = model.Id
        ec2_client = session.client('ec2')
        ec2_client.terminate_instances(InstanceIds=[instance_id])
        progress = ProgressEvent(status=OperationStatus.SUCCESS)
        LOG.info(f"Returning SUCCESS")
    except:
        progress = ProgressEvent(status=OperationStatus.FAILED, errorCode=HandlerErrorCode.NotFound)
        LOG.info(f"Returning FAILED")


    return progress


@resource.handler(Action.READ)
def read_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:
    
    LOG.info("Starting read_handler")

    ssm_client = session.client('ssm')
    ssm_name = f"{default_ssm_path}/{request.stackId}"
    try:
        ssm_client.get_parameter(Name=ssm_name)
        model = request.desiredResourceState
        progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=model)
        LOG.info(f"Returning SUCCESS")
    except:
        progress = ProgressEvent(status=OperationStatus.FAILED, errorCode=HandlerErrorCode.NotFound)
        LOG.info(f"Returning FAILED")
    
    return progress


@resource.handler(Action.LIST)
def list_handler(_s, _r, _c):
    raise NotImplementedError("LIST handler not implemented")