# imports
import logging
import os
import boto3
import uuid
import time

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

# LOG.info("Waiting for debug process to attach")
# import ptvsd
# ptvsd.enable_attach(address=('0.0.0.0', 5890), redirect_output=True)
# ptvsd.wait_for_attach()

# Set resource and test_entrypoint
TYPE_NAME = "EQ::MONITOR::NAGIOS"
resource = Resource(TYPE_NAME, ResourceModel)
test_entrypoint = resource.test_entrypoint

default_server_name = 'Nagios Server'
default_instance_type = 't2.small'
default_ssm_ami_parameter = '/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2'
default_callback_period = 60
default_ssm_path = '/Eq/Nagios/Monitor/Stack'

const_key_instance_id = 'instance_id'
const_key_name = 'server_name'
const_key_policy_arn = 'policy_arn'
const_key_role = 'role'
const_key_instance_profile = 'instance_profile'
const_key_IP = 'IP'
const_key_URL = 'URL'
const_key_status = 'status'
const_key_subnet = 'subnet_id'
const_key_sg = 'security_groups'
model_key_list = [const_key_instance_id, const_key_name, 
                    const_key_policy_arn, const_key_role, const_key_instance_profile, 
                    const_key_IP, const_key_URL, 
                    const_key_status, 
                    const_key_subnet, const_key_sg]

ssm_action_put = 0
ssm_action_get = 1
ssm_action_delete = 2

ec2_user_data = """#!/bin/bash -xe
region=$(curl -k http://169.254.169.254/latest/meta-data/placement/region)
instance_id=$(curl -k http://169.254.169.254/latest/meta-data/instance-id)

aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value Starting --overwrite
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value StartingYumUpdates --overwrite
yum install -y gcc glibc glibc-common wget unzip httpd php gd gd-devel perl postfix
cd /tmp
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value DownloadingNagios --overwrite
wget -O nagioscore.tar.gz https://github.com/NagiosEnterprises/nagioscore/archive/nagios-4.4.5.tar.gz
tar xzf nagioscore.tar.gz
cd /tmp/nagioscore-nagios-4.4.5/
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value DeployingNagios --overwrite
./configure
make all
make install-groups-users
usermod -a -G nagios apache
make install
make install-daemoninit
chkconfig --level 2345 httpd on
systemctl enable httpd.service
make install-commandmode
make install-config
make install-webconf
htpasswd -c -b /usr/local/nagios/etc/htpasswd.users nagiosadmin nagiosadmin
cd /tmp
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value DownloadingPlugins --overwrite
wget https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
rpm -ihv epel-release-latest-7.noarch.rpm
yum install -y gcc glibc glibc-common make gettext automake autoconf wget openssl-devel net-snmp net-snmp-utils
yum install -y perl-Net-SNMP
cd /tmp
wget --no-check-certificate -O nagios-plugins.tar.gz https://github.com/nagios-plugins/nagios-plugins/archive/release-2.2.1.tar.gz
tar zxf nagios-plugins.tar.gz
cd /tmp/nagios-plugins-release-2.2.1/
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value DeployingPlugins --overwrite
./tools/setup
./configure
make
make install
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value StartingServices --overwrite
systemctl restart httpd.service
systemctl restart nagios.service
aws ssm put-parameter --name $default_ssm_path/$key/$instance_id --region $region --type String --value Done --overwrite
"""

ec2_assume_role_document = """{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}"""

ec2_policy_document = """{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AccessParameterManager",
            "Effect": "Allow",
            "Action": [
                "ssm:PutParameter",
                "ssm:DeleteParameter",
                "ssm:DescribeParameters",
                "ssm:GetParametersByPath",
                "ssm:GetParameters",
                "ssm:GetParameter",
                "ssm:DeleteParameters"
            ],
            "Resource": "*"
        }
    ]
}"""


# =====================================
# Helper functions
# =====================================
def build_instance(model:ResourceModel, session, callback_context:MutableMapping[str, any]):

    ssm_client = session.client('ssm')
    ec2_client = session.client('ec2')
    iam_client = session.client('iam')

    try:
        # initialize parameters
        LOG.info(f"...Initializing resource parameters (instance name, type)")
        model.Id = None
        instance_name = model.Name if model.Name != '' else default_server_name
        instance_type = default_instance_type
        sg_id = model.SecurityGroupId
        subnet_id = model.SubnetId

        # image_id comes from AWS SSM paramters that stores latest ami ids
        ssm_response = ssm_client.get_parameter(Name=default_ssm_ami_parameter)
        image_id = ssm_response['Parameter']['Value']

        # create instance profile
        rnd = str(uuid.uuid4()).replace('-','_')
        role_name = f"nagios_role_{rnd}"
        instance_profile_name = f"nagios_instance_profile_{rnd}"
        LOG.info(f"...Creating role {role_name}")
        iam_response = iam_client.create_role(RoleName=role_name, AssumeRolePolicyDocument=ec2_assume_role_document, Description='Role for nagios server')
        LOG.info(f"...Creating custom policy")
        iam_response = iam_client.create_policy(PolicyName=f"nagios_policy_{rnd}", PolicyDocument=ec2_policy_document, Description='Custom Policy for Nagios Server')
        policy_arn = iam_response['Policy']['Arn']
        LOG.info(f"...Attaching policies to role")
        iam_client.attach_role_policy(RoleName=role_name, PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
        LOG.info(f"...Creating instance profile {instance_profile_name}")
        iam_response = iam_client.create_instance_profile(InstanceProfileName=instance_profile_name)
        iam_client.add_role_to_instance_profile(InstanceProfileName=instance_profile_name, RoleName=role_name)
        time.sleep(30)      # need to do this, iam waiter not working properly

        # start EC2 instance
        LOG.info(f"...Starting EC2 instance {instance_name} with {image_id} on {instance_type} instance, subnet {subnet_id} and security groups {sg_id}")
        user_data = ec2_user_data.replace('$default_ssm_path', default_ssm_path).replace('$key', const_key_status)
        
        ec2_response = ec2_client.run_instances(
                                    ImageId=image_id,
                                    InstanceType=instance_type,
                                    SecurityGroupIds=[sg_id],
                                    SubnetId=subnet_id,
                                    MinCount=1,
                                    MaxCount=1,
                                    UserData=user_data,
                                    IamInstanceProfile={'Name': instance_profile_name},
                                    TagSpecifications=[{'ResourceType':'instance', 'Tags': [{'Key': 'Name', 'Value': instance_name}]}]
                                    )

        # capture and store instance id so it can be terminated
        instance_id = ec2_response['Instances'][0]['InstanceId']
        model.Id = instance_id
        callback_context[const_key_role] = role_name
        callback_context[const_key_policy_arn] = policy_arn
        callback_context[const_key_instance_profile] = instance_profile_name
        callback_context[const_key_subnet] = subnet_id
        callback_context[const_key_sg] = sg_id
        callback_context[const_key_name] = instance_name

        LOG.info(f"...New instance {instance_id} created successfully")

        # get success progress event
        progress = ProgressEvent(status=OperationStatus.IN_PROGRESS, callbackDelaySeconds=default_callback_period, resourceModel=model, callbackContext=callback_context)

    except Exception as err:
        # get failed progress event
        msg = f"Unexpected error creating nagios server: {type(err).__name__}: {str(err)}"
        progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)
        LOG.exception(msg)

    return progress



def check_instance_state(model:ResourceModel, session, callback_context:MutableMapping[str, any]):

    try:
        # use ec2 resource to get the current state
        instance_id = model.Id
        LOG.info(f"...Checking state for instance {instance_id}")
        ec2_client = session.resource('ec2')
        instance = ec2_client.Instance(instance_id)
        state = instance.state
        state_code = state['Code']
        state_name = state['Name']

        # return progress event based on state
        if state_code == 16:
            LOG.info(f"...Instance is {state_name}, checking status of user_data")
            status = 'Not started'
            try:
                # when first initializing, the ssm parameter may not be available
                status = ssm_parameter_action(ssm_action_get, session, model.Id, const_key_status)
            except:
                pass
            if status == 'Done':
                # we're done
                LOG.info("...User data script complete")
                # get and update IP and URL
                model.IP = instance.public_ip_address
                LOG.info(f"...IP is {model.IP}")
                model.URL = f"http://{model.IP}/nagios"
                LOG.info(f"...URL is {model.URL}")
                progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=model)
            else:
                msg = f"Waiting for user data script to complete, status is {status}"
                LOG.info(f"...{msg}")
                progress = ProgressEvent(status=OperationStatus.IN_PROGRESS, callbackDelaySeconds=default_callback_period, callbackContext=callback_context, resourceModel=model, message=msg)
        elif state_code == 0:
            # still in pending state
            LOG.info(f"...Instance is {state_name}")
            msg = "Waiting for EC2 instance to stabilize"
            progress = ProgressEvent(status=OperationStatus.IN_PROGRESS, callbackDelaySeconds=default_callback_period, resourceModel=model, message=msg, callbackContext=callback_context)
        else:
            # something went wrong - EC2 is stopping, stopped or terminated
            LOG.info(f"...Instance is {state_name}")
            msg = f"Unexpected error, instance is {state_name}"
            progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)

    except Exception as err:
        # get failed progress event
        msg = f"Unexpected error checking state: {type(err).__name__}: {str(err)}"
        progress = ProgressEvent(status=OperationStatus.FAILED, resourceModel=model, message=msg)
        LOG.exception(msg)

    return progress


def ssm_parameter_action(action, session, id, key, value=None):

    ssm_client = session.client('ssm')
    # ssm_name = f"{default_ssm_path}/{id}/{key}"
    ssm_name = f"{default_ssm_path}/{key}/{id}"
    
    if action == ssm_action_put:
        ssm_value = value
        ssm_type = 'String'
        if isinstance(ssm_value, list):
            ssm_value = ','.join(ssm_value)
            ssm_type = 'StringList'
        ssm_client.put_parameter(Name=ssm_name, Value=ssm_value, Type=ssm_type, Overwrite=True)
    elif action == ssm_action_get:
        ssm_response = ssm_client.get_parameter(Name=ssm_name)
        if ssm_response['Parameter']['Type'] == 'String':
            ssm_value = ssm_response['Parameter']['Value']
        else:
            ssm_value = (ssm_response['Parameter']['Value']).split(',')
    else:
        ssm_client.delete_parameter(Name=ssm_name)
        ssm_value = ''

    return ssm_value


# =====================================
# Main Resource Handlers
# =====================================
@resource.handler(Action.CREATE)
def create_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:


    LOG.info("Starting create_handler")

    # initialize model
    model = request.desiredResourceState

    # check whether this is the first call or a callback
    # first call, create instance, subsequently check instance state until ready
    if model.Id is None:
        LOG.info(f"...no model Id, creating instance")
        progress = build_instance(model, session, callback_context)
    else:
        LOG.info(f"...model.Id is {model.Id}, checking instance state")
        progress = check_instance_state(model, session, callback_context)
        if progress.status == OperationStatus.SUCCESS:
            id = model.Id
            # Store server id information in SSM - needed for read after delete
            LOG.info(f"...instance is running, storing information in SSM")
            callback_context[const_key_instance_id] = model.Id
            callback_context[const_key_IP] = model.IP
            callback_context[const_key_URL] = model.URL
            for key, value in callback_context.items():
                ssm_parameter_action(ssm_action_put, session, id, key, value)

    LOG.info(f"Exiting create_handler with code {progress.status}")
    return progress


@resource.handler(Action.UPDATE)
def update_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:

    LOG.info("Starting update_handler")

    desired_state = request.desiredResourceState
    current_state = request.previousResourceState

    desired_name = desired_state.Name
    current_name = current_state.Name

    try:
        # if instance_id is not in SSM, the resource doesn't exist and it will raise an exception
        ssm_parameter_action(ssm_action_get, session, desired_state.Id, const_key_instance_id)

        if desired_name != current_name:
            LOG.info(f"...Updating instance name from {current_name} to {desired_name}")
            # use ec2 resource to get the current state
            instance_id = desired_state.Id
            ec2_client = session.resource('ec2')
            instance = ec2_client.Instance(instance_id)
            instance.create_tags(Tags=[{'Key': 'Name', 'Value': desired_name}])
        else:
            LOG.info(f"...Nothing to update")

        progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=desired_state)

    except:
        msg = "Server does not exist"
        progress = ProgressEvent(status=OperationStatus.FAILED, errorCode=HandlerErrorCode.NotFound, message=msg)


    LOG.info(f"Exiting create_handler with code {progress.status}")
    return progress


@resource.handler(Action.DELETE)
def delete_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:

    # TODO:
    #   wait for server to terminate
    #   delete roles and policies

    LOG.info("Starting delete_handler")

    try:
        LOG.info("...Terminating ec2 instance")
        model = request.desiredResourceState
        instance_id = ssm_parameter_action(ssm_action_get, session, model.Id, const_key_instance_id)

        ec2_client = session.client('ec2')
        try:
            ec2_client.terminate_instances(InstanceIds=[instance_id])
        except:
            pass

        LOG.info("...Removing role, policy and instance profile")
        try:
            instance_profile = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_instance_profile)
        except:
            pass

        try:
            role = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_role)
        except:
            pass

        try:
            policy_arn = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_policy_arn)
        except:
            pass


        iam_client = session.client('iam')
        try:
            iam_client.remove_role_from_instance_profile(InstanceProfileName=instance_profile, RoleName=role)
        except:
            pass

        try:
            iam_client.delete_instance_profile(InstanceProfileName=instance_profile)
        except:
            pass

        try:
            iam_client.detach_role_policy(RoleName=role, PolicyArn=policy_arn)
        except:
            pass

        try:
            iam_client.detach_role_policy(RoleName=role, PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        except:
            pass

        try:
            iam_client.delete_policy(PolicyArn=policy_arn)
        except:
            pass

        try:
            iam_client.delete_role(RoleName=role)
        except:
            pass


        LOG.info("...Deleting SSM parameters")
        for key in model_key_list:
            try:
                ssm_parameter_action(ssm_action_delete, session, instance_id, key)
            except:
                pass

        progress = ProgressEvent(status=OperationStatus.SUCCESS)

    except Exception as err:
        msg = f"...Unexpected error checking state: {type(err).__name__}: {str(err)}"
        LOG.info(msg)
        progress = ProgressEvent(status=OperationStatus.FAILED, errorCode=HandlerErrorCode.NotFound, message=msg)


    LOG.info(f"Exiting delete_handler with code {progress.status}")
    return progress


@resource.handler(Action.READ)
def read_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:
    
    LOG.info("Starting read_handler")

    model = request.desiredResourceState
    try:
        ssm_parameter_action(ssm_action_get, session, model.Id, const_key_instance_id, model.Id)
        model = request.desiredResourceState
        model.IP = ssm_parameter_action(ssm_action_get, session, model.Id, const_key_IP)
        model.URL = ssm_parameter_action(ssm_action_get, session, model.Id, const_key_URL)
        progress = ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=model)
    except:
        progress = ProgressEvent(status=OperationStatus.FAILED, errorCode=HandlerErrorCode.NotFound)
    
    LOG.info(f"Exiting read_handler with code {progress.status}")
    return progress


@resource.handler(Action.LIST)
def list_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:

    LOG.info("Starting list_handler")
    
    ssm = session.client('ssm')
    ssm_response = ssm.get_parameters_by_path(Path='/Eq/Nagios/Monitor/Stack/instance_id')
    parameters = ssm_response['Parameters']
    models = []
    for parameter in parameters:
        try:
            key = parameter['Name']
            vals = key.split('/')
            instance_id = vals[len(vals)-1]
            name = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_name)
            ip = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_IP)
            url = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_URL)
            role = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_role)
            policy_arn = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_policy_arn)
            instance_profile = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_instance_profile)
            subnet = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_subnet)
            sg_id = ssm_parameter_action(ssm_action_get, session, instance_id, const_key_sg)
            model = ResourceModel(Name=name, Id=instance_id, IP=ip, URL=url, 
                                    Role=role, PolicyArn=policy_arn, InstanceProfile=instance_profile, 
                                    SubnetId=subnet, SecurityGroupId=sg_id)
            models.append(model)
        except:
            pass

    progress = ProgressEvent(status=OperationStatus.SUCCESS,resourceModels=models)

    LOG.info(f"Exiting list_handler with code {progress.status}")
    return progress
