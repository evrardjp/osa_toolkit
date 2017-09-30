#!/usr/bin/env python
""" Tools for releasing openstack-ansible project repositories"""

import binascii
from collections import OrderedDict
import click
import click_log
import logging
import os
import re
import semver
import shutil
import libs
from urlparse import urlparse
import yaml
import yamlordereddictloader
from ruamel.yaml import YAML
from git import Repo

VALID_CODE_NAMES = {
    "queens": 17,
    "pike": 16,
    "ocata": 15,
    "newton": 14,
}
PRE_RELEASE_PREFIXES = (
    "0b1",
    "0b2",
    "0b3",
    "0rc1",
    "0rc2",
    "0rc3",
)

# Convenience settings that will spread accross many the functions
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
WORK_DIR_OPT = ['-w', '--workdir']
WORK_DIR_OPT_PARAMS = dict(
    default='/tmp/newcode',
    type=click.Path(exists=True, file_okay=False,
                    dir_okay=True, writable=True, resolve_path=True),
    help='Work directory: Temporary workspace folder'
)
COMMIT_OPT = ['--commit/--no-commit']
COMMIT_PARAMS = dict(
    default=False,
    help='Auto commit work'
)
OPENSTACK_REPOS = "https://git.openstack.org/openstack/"

# CODE STARTS HERE
logger = logging.getLogger(__name__)
click_log.basic_config(logger)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(logger)
@click.option('--branch', required=True)
@click.option('--version', required=True)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option(*COMMIT_OPT, **COMMIT_PARAMS)
def update_os_release_file(*args, **kwargs):
    """ Prepare a new release for the openstack/release repo in your workdir """

    # Steps:
    #
    # Enter OA folder, find out its sha
    # Given a OPENSTACK branch name
    # Cleanup "releases" repo in workspace
    # Git clone repo master in workspace
    # Find out each a-r-r shas
    # Output a-r-r and OA HEAD sha into a structure for releases
    #
    releases_repo_url = OPENSTACK_REPOS + 'releases.git'
    releases_folder = kwargs['workdir'] + '/releases'

    # Args validation
    logger.info("Doing pre-flight checks")
    if kwargs['branch'] not in VALID_CODE_NAMES:
        raise SystemExit("Invalid branch name {}".format(kwargs['branch']))
    if kwargs['version'] == "auto":
        version = click.prompt("Auto is not yet implemented here. Version?")
    else:
        version = kwargs['version']

    pre_release = (version.endswith(PRE_RELEASE_PREFIXES))

    if not pre_release:
        try:
            semver_res = semver.parse(version)
        except Exception as exc:
            raise SystemExit(exc)
        major_version = semver_res['major']
    else:
        major_version = int(version.split(".")[0])

    if major_version != VALID_CODE_NAMES[kwargs['branch']]:
        raise SystemExit("Not a valid number for this series")

    oa_folder = kwargs['workdir'] + '/openstack-ansible'
    click.confirm(("Are your sure your {} folder is properly "
                   "checked out at the right version?").format(oa_folder))

    # Do work now
    oa = Repo(oa_folder)
    head_commit = oa.head.commit
    logger.info("Found OpenStack-Ansible version {}".format(head_commit))
    if os.path.lexists(releases_folder):
        if click.confirm('Deleting ' + kwargs['workdir'] + '/releases. OK?'):
            shutil.rmtree(releases_folder)
    releases_repo = Repo.clone_from(
        url=releases_repo_url,
        to_path=releases_folder,
        branch="master")

    # Preparing Release: OA repo details
    oa_details = OrderedDict()
    oa_details['repo'] = 'openstack/openstack-ansible'
    oa_details['hash'] = "{}".format(head_commit)
    projects = [oa_details]

    # Preparing Release: ansible-role-requirements details
    with open(kwargs['workdir'] +
              '/openstack-ansible/ansible-role-requirements.yml') as arr_f:
        arr = yaml.load(arr_f.read(), Loader=yamlordereddictloader.Loader)
    regex = re.compile('^' + OPENSTACK_REPOS + '.*')
    for role in arr:
        if regex.match(role['src']):
            repo_release = OrderedDict()
            # cleanup
            repo = urlparse(role['src']).path.lstrip('/')
            # keep only repo and hash
            repo_release['repo'] = repo
            repo_release['hash'] = role['version']
            # add to final
            projects.append(repo_release.copy())

    release = OrderedDict()
    release['version'] = "{}".format(version)
    release['projects'] = projects

    logger.info("Patching the deliverable file from releases...")
    deliverable_file = (releases_folder + '/deliverables/' +
                        kwargs['branch'] + '/openstack-ansible.yaml')
    with open(deliverable_file, 'r') as deliverable_fh:
        deliverable = yaml.load(deliverable_fh.read(),
                                Loader=yamlordereddictloader.Loader)

    if deliverable.get('releases'):
        deliverable['releases'].append(release)
    else:
        deliverable['releases'] = [release]

    yaml.dump(deliverable, open(deliverable_file, 'w'),
              Dumper=yamlordereddictloader.Dumper, default_flow_style=False,indent=2)
    logger.info("Patched!")

    if kwargs['commit']:
        click.echo("The auto commit is not yet implemented.")


def update_openstack_projects():
    """ Bump OpenStack projects and their files in our roles"""
    # Finds out which tracking branch you are on
    # Generates a commit in OA and each of its roles
    # Generates a git show output
    # Asks before triggering git review

    pass


def check_global_requirement_pins():
    """ Check if there are new versions of packages in pypy for our pins """
    pass
    # Assuming the OA Folder is clean.
    # Needs:
    #   OA folder checked out tracking a branch name matching requirements
    #   Internet connectivity to PyPI
    #   Internet connectivity to requirements
    # Steps:
    # Opening global-requirement-pins.txt in OpenStack-Ansible folder
    # for each requirement, get latest version on pypi
    #   see get-pypi-pkg-version.py
    #   (build a list of pypi versions/update version dicts)
    # If pypi has a different version than current:
    #   Find out which branch we are using
    #   Clone "requirements" repo in workspace
    #       or fetch it to latest version for branch
    #   Load upper constraints file
    #   For each requirement:
    #       Find requiremt in upper constraints
    #       Print:
    #           Current: <requirement>
    #           PyPI: <requirement>
    #       If present in uc, print
    #           Upper Constraints: <requirement>


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(logger)
# @click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
# @click.option(*OPENSTACK_BRANCH_OPT, **OPENSTACK_BRANCH_OPT_PARAMS)
# @click.option(*OA_FOLDER_OPT, **OA_FOLDER_OPT_PARAMS)
@click.option("--external-roles/--no-external-roles", default=False)
def bump_arr(**kwargs):
    """ Update Ansible Role Requirements for branch, effectively freezing them"""
    logger.info("Reading ansible-role-requirements file in this folder")
    pass
    # Assuming the OA Folder is clean.
    # Steps:
    #
    # Opening ARR in OpenStack-Ansible folder
    # Get Tracking Branch: Check branch from OA FOLDER
    # Git clone and checkout branch for OA roles (matching git.openstack.org)
    # Copy role's release notes
    #   rsync -aq ${osa_repo_tmp_path}/releasenotes/notes/*.yaml \
    #   releasenotes/notes/
    # Save latest sha of the role
    # Bump role sha in file
    #   "$current_source_dir/ansible-role-requirements-editor.py" \
    #   -f ansible-role-requirements.yml -n "${role_name}" -v "${role_version}"
    #
    # OPTIONAL: Bump external roles
    # Git clone external role
    # Iterate through similar tags (last number of version bump max)
    #   Sort tags
    #   As long as a tag doesn't match each of the (length -1) numbers,continue
    #   Take first match

    # with open('ansible-role-requirements.yml', 'r') as arr_f:
    #     arr = yaml.safe_load(arr_f.read())

    # logger.error("Failed to divide by zero.")


def bump_oa_release_number():
    """ Update OpenStack Ansible version number in code """
    pass
    # Dirties the OA repo with a new version
    # Steps:
    #
    # For each file, in succesion (do not fail if not exists)
    #   [ group_vars/all/all.yml, playbooks/inventory/group_vars/all.yml ]
    #   check if 'openstack_release' exists
    #       If exists retuns file and version
    #
    # Version X will be:
    #   If version given in argument, take this as a value
    #   If not given in argument, semver.bump_patch on version found
    #
    # Open file and edit openstack_release: <version X>, save


# def release():
#     """ Do all the above functions in a chain """

#     # Steps:
#     # update_os_release_file
#     # git review
#     #   returns X
#     # Take review change id
#     # SHA Bump of ARR
#     # SHA Bump of Upstream
#     # git review
#     #   Depends on <X>
#     #
#     """
#     #current_hash=$(git rev-parse HEAD)
#     #current_version=$(awk '/openstack_release:/ {print $2}' playbooks/inventory/group_vars/all.yml)
#     #../release-yaml-file-prep.py -f ansible-role-requirements.yml -v "${current_version}" | awk "/projects:/{print; print \"      - repo: openstack/openstack-ansible\n        hash: ${current_hash}\"; next}1" | sed '/^releases:/d' | sed '/^\s*$/d' >> ~/code/releases/deliverables/newton/openstack-ansible.yaml
#     """

#     """
#     Update all SHAs for ${new_version}" \
#     -m "This patch updates all the roles to the latest available stable
#     SHA's, copies the release notes from the updated roles into the
#     integrated repo, updates all the OpenStack Service SHA's, and
#     updates the appropriate python requirements pins.

#     Depends-On: ${release_changeid}"

#     """
#     pass


if __name__ == '__main__':
    update_os_release_file()

# @click.group(context_settings=CONTEXT_SETTINGS)
# @click.option('--debug/--no-debug', default=False)
# @click.option('-d', '--directory',
#               default='/tmp/code',
#               type=click.Path(exists=True, file_okay=False,
#                               dir_okay=True, writable=True, resolve_path=True),
#               help='Temporary workspace folder')
# @click.pass_context
# def cli(ctx, debug, directory):  # pragma: no cover
#     ctx.obj['DEBUG'] = debug
#     ctx.obj['DIRECTORY'] = directory
#     if debug:
#         logging.getLogger().setLevel(logging.DEBUG)
#     else:
#         logging.getLogger().setLevel(logging.INFO)

# @cli.command()
# @click.option('-d', '--directory',
#               default='/tmp/code',
#               help='Temporary workspace folder')
# @click.pass_context
# def arr_update(ctx):
#     """ Update Ansible Role Requirements for branch """
#     click.echo('Temporary workspace folder is %s' % (ctx.obj['DIRECTORY']))
#     logging.info("Woot")
#     logging.debug("only appears on debug")


# if __name__ == '__main__':
#     cli(obj={})
