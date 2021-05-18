# imports
import logging
import os
import boto3

from models import ResourceHandlerRequest, ResourceModel

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
def init_ec2_client(model):
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.SUCCESS, resourceModel=model
    )
    ec2_client = boto3.client('ec2')
    return model, progress, ec2_client

def get_repo(id, gh_client):
    try:
        return gh_client.get_repo(int(id))
    except GithubException as e:
        if e._GithubException__status == 404:
            raise exceptions.NotFound(TYPE_NAME, id)
        raise

# =====================================
# Main Resource Handlers
# =====================================
@resource.handler(Action.CREATE)
def create_handler(_, request: ResourceHandlerRequest, __) -> ProgressEvent:
    model, progress, gh_client = init_gh_client(request.desiredResourceState)
    private = False if model.Visibility == "public" else True
    if model.Org:
        repo_parent = gh_client.get_organization(model.Org)
    else:
        repo_parent = gh_client.get_user()
    model.Namespace = f"{repo_parent.login}/{model.Name}"
    try:
        repo = repo_parent.create_repo(model.Name, private=private)
        repo.replace_topics(["created-with-cloudformation"])
    except GithubException as e:
        # when the repo name already exists, return a specific error
        if isinstance(e.data["errors"][0], dict):
            message = e.data["errors"][0].get("message")
            if message == "name already exists on this account":
                raise exceptions.AlreadyExists(TYPE_NAME, model.Namespace)
        raise exceptions.InternalFailure(str(e.data["errors"]))
    model.Id = int(repo.id)
    model.HttpsUrl = repo.clone_url
    model.SshUrl = repo.ssh_url
    return progress

@resource.handler(Action.UPDATE)
def update_handler(_s, request: ResourceHandlerRequest, _c) -> ProgressEvent:
    model, progress, gh_client = init_gh_client(request.desiredResourceState)
    repo = get_repo(model.Id, gh_client)
    private = model.Visibility == "private"
    repo.edit(name=model.Name, private=private)
    return progress

@resource.handler(Action.DELETE)
def delete_handler(_s, request: ResourceHandlerRequest, _c) -> ProgressEvent:
    model, progress, gh_client = init_gh_client(request.desiredResourceState)
    repo = get_repo(model.Id, gh_client)
    repo.delete()
    return progress

@resource.handler(Action.READ)
def read_handler(_s, request: ResourceHandlerRequest, _c) -> ProgressEvent:
    model, progress, gh_client = init_gh_client(request.desiredResourceState)
    repo = get_repo(model.Id, gh_client)
    model.HttpsUrl = repo.clone_url
    model.SshUrl = repo.ssh_url
    model.Namespace = repo.full_name
    model.Visibility = "private" if repo.private else "public"
    return progress

@resource.handler(Action.LIST)
def list_handler(_s, _r, _c):
    raise NotImplementedError("LIST handler not implemented")