#!/usr/bin/env python
""" Tools for releasing openstack-ansible project repositories"""

from datetime import datetime
import fileinput
import glob
import logging
import os
import re
import shutil
import subprocess
from urlparse import urlparse
import xmlrpclib

# Extra Packages
import click
import click_log
from git import Repo                    # GitPython package
import requirements as requirementslib  # requirements-parser package
from ruamel.yaml import YAML
import semver
from toolkit import *

# Convenience settings that will spread accross many the functions
# CODE NAME -> Major Release number mapping.
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
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
WORK_DIR_OPT = ['-w', '--workdir']
WORK_DIR_OPT_PARAMS = dict(default='/tmp/newcode',
                           type=click.Path(exists=True, file_okay=False,
                                           dir_okay=True, writable=True,
                                           resolve_path=True),
                           help='Work directory: Temporary workspace folder')
COMMIT_OPT = ['--commit/--no-commit']
COMMIT_PARAMS = dict(default=False,
                     help='commits automatically the generated changes')
OPENSTACK_REPOS = "https://git.openstack.org/openstack"
PYPI_URL = "https://pypi.python.org/pypi"
# Path to Ansible role requirements in workspace
ARR_PATH = '/openstack-ansible/ansible-role-requirements.yml'


# CODE STARTS HERE
LOGGER = logging.getLogger(__name__)
click_log.basic_config(LOGGER)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option('--branch', required=True)
@click.option('--version', required=True)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option(*COMMIT_OPT, **COMMIT_PARAMS)
def update_os_release_file(**kwargs):
    """ Update in tree a release file
    with a given branch (code name) and
    version (release number) inside a new
    checkin of the openstack/release repo
    in your workdir
    """

    releases_repo_url = OPENSTACK_REPOS + '/releases.git'
    releases_folder = kwargs['workdir'] + '/releases'

    # Args validation
    LOGGER.info("Doing pre-flight checks")
    if kwargs['branch'] not in VALID_CODE_NAMES:
        raise SystemExit("Invalid branch name {}".format(kwargs['branch']))
    if kwargs['version'] == "auto":
        version = click.prompt("Auto is not yet implemented here. Version?")
    else:
        version = kwargs['version']

    pre_release = (version.endswith(PRE_RELEASE_PREFIXES))

    if not pre_release:
        # For extra safety, ensure it's semver.
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
                   "checked out at the right version?").format(oa_folder),
                  abort=True)
    # Args validation done.

    yaml = YAML()
    oa = Repo(oa_folder)
    head_commit = oa.head.commit
    LOGGER.info("Found OpenStack-Ansible version {}".format(head_commit))
    if os.path.lexists(releases_folder):
        click.confirm('Deleting ' + releases_folder + '. OK?', abort=True)
        shutil.rmtree(releases_folder)
    releases_repo = Repo.clone_from(
        url=releases_repo_url,
        to_path=releases_folder,
        branch="master")

    LOGGER.info("Reading ansible-role-requirements")
    arr, _, _ = load_yaml(kwargs['workdir'] + ARR_PATH)

    LOGGER.info("Reading releases deliverable for the given branch")
    deliverable_file_path = ('deliverables/' + kwargs['branch'] +
                             '/openstack-ansible.yaml')
    deliverable_file = releases_folder + "/" + deliverable_file_path
    deliverable, ind, bsi = load_yaml(deliverable_file)

    # if no releases yet (start of cycle), prepare releases, as a list
    if not deliverable.get('releases'):
        deliverable['releases'] = []

    # Ensure the new release is last
    deliverable['releases'].append(
        {'version': "{}".format(version),
         'projects': []}
    )

    # Now we can build in the order we want and still keep std dicts
    deliverable['releases'][-1]['projects'].append(
        {'repo': 'openstack/openstack-ansible',
         'hash': "{}".format(head_commit)}
    )

    # Select OpenStack Projects and rename them for releases.
    # Keep their SHA
    regex = re.compile('^' + OPENSTACK_REPOS + '/.*')
    for role in arr:
        if regex.match(role['src']):
            deliverable['releases'][-1]['projects'].append(
                {'repo': urlparse(role['src']).path.lstrip('/'),
                 'hash': role['version']}
            )

    with open(deliverable_file, 'w') as df_h:
        yaml.explicit_start = True
        yaml.block_seq_indent = bsi
        yaml.indent = ind
        yaml.dump(deliverable, df_h)
        LOGGER.info("Patched!")

    if kwargs['commit']:
        message = """Release OpenStack-Ansible {}/{}

        """.format(kwargs['branch'], version)
        releases_repo.index.add([deliverable_file_path])
        releases_repo.index.commit(message)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
def bump_upstream_sources(**kwargs):
    """ Bump OpenStack projects SHA in OA repo
    """

    # Find out current tracking branch to bump
    # the services matching the branch:
    oa_folder = kwargs['workdir'] + '/openstack-ansible'
    try:
        remote_branch = tracking_branch_name(oa_folder)
    except ValueError as verr:
        raise SystemExit(verr)

    LOGGER.info("Each file can take a while to update.")
    prevline = {}
    reporegex = re.compile('(?P<project>.*)_git_repo: (?P<remote>.*)')
    branchregex = re.compile(('(?P<project>.*)_git_install_branch: '
                              '(?P<sha>[0-9a-f]{40}) '
                              '# HEAD of "(?P<branch>.*)" '
                              'as of .*'))

    update_files = glob.glob(
        "{}/playbooks/defaults/repo_packages/*.yml".format(oa_folder))

    stable_branch_skips = [
        "openstack_testing.yml",
        "nova_consoles.yml",
    ]

    for filename in update_files:
        if remote_branch.startswith("stable/") and \
                os.path.basename(filename) in stable_branch_skips:
            LOGGER.info("Skipping {} for stable branch".format(filename))
            continue
        LOGGER.info("Updating {}".format(filename))
        for line in fileinput.input(filename, inplace=True):
            rrm = reporegex.match(line)
            if rrm:
                # Extract info of repo line (previous line)
                # for branch line (current line)
                prevline['project'] = rrm.group('project')
                prevline['remote'] = rrm.group('remote')
            print(branchregex.sub(
                lambda x: bump_project_sha_with_comments(x, prevline), line)),

    LOGGER.info("All files patched !")
    msg = ("Here is a commit message you could use:\n"
           "Update all SHAs for {new_version}\n\n"
           "This patch updates all the roles to the latest available stable \n"
           "SHA's, copies the release notes from the updated roles into the \n"
           "integrated repo, updates all the OpenStack Service SHA's, and \n"
           "updates the appropriate python requirements pins. \n\n"
           "Depends-On: {release_changeid}").format(
               new_version=os.environ.get('new_version', '<NEW VERSION>'),
               release_changeid=os.environ.get('release_changeid', '<TODO>'),)
    click.echo(msg)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
def update_role_files(**kwargs):
    """ Bump OpenStack Projects files into their
        OpenStack-Ansible role
    """

    # Finds out which tracking branch you are on
    # Generates a commit in OA and each of its roles
    # Generates a git show output
    # Asks before triggering git review

    # Example commit message
    # Update all SHAs for 15.1.8
    # This patch updates all the roles to the latest available stable
    # SHA's, copies the release notes from the updated roles into the
    # integrated repo, updates all the OpenStack Service SHA's, and
    # updates the appropriate python requirements pins.
    click.echo("Not implemented yet")


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
def check_global_requirement_pins(**kwargs):
    """ Check if there are new versions of packages in pypy for our pins """
    # Needs:
    #   OA folder checked out tracking a branch name matching requirements
    #   Internet connectivity to PyPI
    #   Internet connectivity to requirements

    pypi = xmlrpclib.ServerProxy(PYPI_URL)

    # Find requirements repo details
    data, _, _ = load_yaml((kwargs['workdir'] + '/openstack-ansible/'
                            'playbooks/defaults/repo_packages/'
                            'openstack_services.yml'))

    # Clean new requirements repo!
    LOGGER.info("Downloading the requirements repo")
    requirements_folder = kwargs['workdir'] + '/requirements'
    if os.path.lexists(requirements_folder):
        click.confirm('Deleting ' + requirements_folder + '. OK?', abort=True)
        shutil.rmtree(requirements_folder)

    requirements_repo = Repo.clone_from(
        url=data['requirements_git_repo'],
        to_path=requirements_folder)
    requirements_repo.git.checkout(data['requirements_git_install_branch'])

    with open(requirements_folder + '/upper-constraints.txt', 'r') as uc_fh:
        upper_constraints = uc_fh.read()

    LOGGER.info("Displaying results")
    with open((kwargs['workdir'] +
               '/openstack-ansible/global-requirement-pins.txt'), 'r') as gr:
        for requirement in requirementslib.parse(gr):
            cstrs = [cstr for cstr in requirementslib.parse(upper_constraints)
                     if cstr.name == requirement.name]
            pypi_pkg = get_pypi_version(pypi, requirement.name)
            print("Name: {name}\n"
                  "Current global Requirement Pin: {pin} \n"
                  "PyPI Latest version: {pypi}\n".format(name=requirement.name,
                                                         pin=requirement.specs,
                                                         pypi=pypi_pkg))
            if cstrs:
                print("""Upper constraint from OpenStack requirements: {}
                      """.format(cstrs[0].specs))
            else:
                print("Constraint not found in OpenStack requirements\n")


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option("--external-roles/--no-external-roles", default=False)
@click.option("--release-notes/no-release-notes", default=True)
def bump_arr(**kwargs):
    """ Update Roles in Ansible Role Requirements for branch,
    effectively freezing them.
    Fetches their release notes
    """

    # Discover branch currently tracking
    oa_folder = kwargs['workdir'] + '/openstack-ansible/'
    try:
        remote_branch = tracking_branch_name(oa_folder)
    except ValueError as verr:
        raise SystemExit(verr)

    # Load ARRrrrr (pirate mode)
    arr, ind, bsi = load_yaml(kwargs['workdir'] + ARR_PATH)

    # Cleanup before doing anything else
    click.confirm("Deleting all the role folders in workspace {}\n"
                  "Are you sure? ".format(kwargs['workdir']))

    # Clone only the OpenStack hosted roles
    regex = re.compile(OPENSTACK_REPOS + '/(.*)')
    for role in arr:
        LOGGER.info("Updating {}".format(role['name']))
        role_path = kwargs['workdir'] + '/' + role['name']
        if regex.match(role['src']):
            if os.path.lexists(role_path):
                shutil.rmtree(role_path)
            # We need to clone instead of ls-remote-ing this
            # way we can rsync the release notes
            role_repo = Repo.clone_from(
                url=role['src'],
                to_path=role_path,
                branch=remote_branch,
            )
            role['version'] = "{}".format(role_repo.head.commit)
            if kwargs['release_notes']:
                LOGGER.info("Processing its release notes")
                subprocess.call(
                    ["rsync", "-aq",
                     "{}/releasenotes/notes/*.yaml".format(role_path),
                     "{}/releasenotes/notes/".format(oa_folder)])

        elif kwargs['external_roles']:
            # For external roles, don't clone,
            # find the latest "matching" tag (patch release)
            # or the latest sha (master)
            role['version'] = find_latest_remote_ref(role['src'],
                                                     role['version'])

    with open(kwargs['workdir'] + ARR_PATH, 'w') as role_req_file:
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.block_seq_indent = bsi
        yaml.indent = ind
        yaml.dump(arr, role_req_file)
        LOGGER.info("Ansible Role Requirements file patched!")

    msg = ("Here is a commit message you could use:\n"
           "Update all SHAs for {new_version}\n\n"
           "This patch updates all the roles to the latest available stable \n"
           "SHA's, copies the release notes from the updated roles into the \n"
           "integrated repo, updates all the OpenStack Service SHA's, and \n"
           "updates the appropriate python requirements pins. \n\n"
           "Depends-On: {release_changeid}").format(
               new_version=os.environ.get('new_version', '<NEW VERSION>'),
               release_changeid=os.environ.get('release_changeid', '<TODO>'),
    )
    click.echo(msg)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option('--version', default="auto")
@click.option(*COMMIT_OPT, **COMMIT_PARAMS)
def bump_oa_release_number(**kwargs):
    """ Update OpenStack Ansible version number in code """

    oa_folder = kwargs['workdir'] + '/openstack-ansible/'
    fpth, cver = get_oa_version(oa_folder)
    LOGGER.info("Current version {} in {}".format(cver, fpth))

    if cver == "master":
        click.confirm("Master should only changed when necessary. Sure?")

    if kwargs['version'] == "auto":
        LOGGER.info("Guessing next version")
        cver_l = cver.split(".")
        try:
            cver_l[-1] = str(int(cver_l[-1]) + 1)
        except ValueError as vee:
            LOGGER.error("Cannot up the version: {}".format(vee))
            nver = click.prompt("New version?")
        else:
            nver = ".".join(cver_l)
    else:
        nver = kwargs['version']

    for line in fileinput.input("{}/{}".format(oa_folder, fpth),
                                inplace=True):
        print(line.replace(
            "openstack_release: {}".format(cver),
            "openstack_release: {}".format(nver))),
    LOGGER.info("Updated the version in repo to {}".format(nver))

    if kwargs['commit']:
        message = """Set OpenStack-Ansible release to {}

        """.format(nver)
        repo = Repo(oa_folder)
        repo.index.add([fpth])
        repo.index.commit(message)


if __name__ == '__main__':
    # update_os_release_file()
    # check_global_requirement_pins()
    # bump_arr()
    # bump_oa_release_number()
    bump_upstream_sources()
