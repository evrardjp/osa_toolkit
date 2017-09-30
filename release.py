#!/usr/bin/env python
""" Tools for releasing openstack-ansible project repositories"""

from datetime import datetime
import fileinput
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
from git import cmd as gitcmd
from git import Repo
import requirements as requirementslib  # requirements-parser package
from ruamel.yaml import YAML
import semver
from toolkit import load_yaml

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
                                           dir_okay=True, writable=True, resolve_path=True),
                           help='Work directory: Temporary workspace folder')
COMMIT_OPT = ['--commit/--no-commit']
COMMIT_PARAMS = dict(default=False,
                     help='commits automatically the generated changes')
OPENSTACK_REPOS = "https://git.openstack.org/openstack"
PYPI_URL = "https://pypi.python.org/pypi"
# Path to Ansible role requirements in workspace
ARR_PATH = '/openstack-ansible/ansible-role-requirements.yml'
VERSION_NUMBER_FILES = ["group_vars/all/all.yml",
                        "playbooks/inventory/group_vars/all.yml"]


def get_package_version(pypiConn, pkg_name):
    """Get the current package version from PyPI."""
    pkg_result = [v for v in pypiConn.package_releases(pkg_name, True)
                  if not re.compile('a|b|rc').search(v)]
    if pkg_result:
        pkg_version = pkg_result[0]
    else:
        pkg_version = 'Not available.'

    return pkg_version


def find_latest_version(url, version):
    """ Discovers, from a git remote, the latest
        "appropriate" tag/sha based on a version:
        If version is a branch, returns the head
            of the branch.
        If version is a tag, find the latest patch
            release.
    """
    # Use GitPtyhon git.cmd to avoid fetching repos
    # as listing remotes is not implemented outside Repo use
    gcli = gitcmd.Git()
    # this stores a sha for a matching branch/tag
    # tag will watch if ending with a number
    # (so v11.1, 1.11.1rc1 would still match)
    regex = re.compile('(?P<sha>[0-9a-f]{40})\t(?P<reference>'
                       'refs/heads/(?P<branch>.*)'
                       '|refs/tags/(?P<tag>.*\d))')

    search_ver = version.split('.')
    # sadly we can't presume the ls-remote list will be sorted
    # so we have to find out ourselves.
    patch_releases = []

    for remote in gcli.ls_remote('--refs', url).splitlines():
        m = regex.match(remote)
        if m and m.group('branch') and m.group('branch') == version:
            return m.group('sha')
        elif m and m.group('tag'):
            ref_of_tag = m.group('tag').split('.')
            # keep a tag if it's almost the same (only last part changes)
            # as what we are looking for.
            # Store its version and sha.
            if ref_of_tag[0:-1] and ref_of_tag[0:-1] == search_ver[0:-1]:
                # store only the last bit, space efficient!
                patch_releases.append(ref_of_tag[-1])

    # Returns the highest value if something was found
    if patch_releases:
        search_ver[-1] = max(patch_releases)
        return ".".join(search_ver)
    else:
        logger.info("No new sha found for {}".format(url))
        return version


def getCurrentOSAVersion(folder):
    """ Finds the current OpenStack-Ansible version
        Input:
            Folder of openstack-ansible
            (without the end slash)
    """
    for filename in VERSION_NUMBER_FILES:
        var_file = "{}/{}".format(folder, filename)
        if os.path.exists(var_file):
            data, _, _ = load_yaml(var_file)
            if data.get('openstack_release'):
                return filename, data.get('openstack_release')


# CODE STARTS HERE
logger = logging.getLogger(__name__)
click_log.basic_config(logger)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(logger)
@click.option('--branch', required=True)
@click.option('--version', required=True)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option(*COMMIT_OPT, **COMMIT_PARAMS)
def update_os_release_file(**kwargs):
    """ Prepare a new release for the openstack/release repo
        in your workdir
    """

    # Steps:
    #
    # Enter OA folder, find out its sha
    # Given a OPENSTACK branch name
    # Cleanup "releases" repo in workspace
    # Git clone repo master in workspace
    # Find out each a-r-r shas
    # Output a-r-r and OA HEAD sha into a structure for releases
    #
    releases_repo_url = OPENSTACK_REPOS + '/releases.git'
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
    logger.info("Found OpenStack-Ansible version {}".format(head_commit))
    if os.path.lexists(releases_folder):
        click.confirm('Deleting ' + releases_folder + '. OK?', abort=True)
        shutil.rmtree(releases_folder)
    releases_repo = Repo.clone_from(
        url=releases_repo_url,
        to_path=releases_folder,
        branch="master")

    logger.info("Reading ansible-role-requirements")
    arr, _, _ = load_yaml(kwargs['workdir'] + ARR_PATH)

    logger.info("Reading releases deliverable for the given branch")
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
        logger.info("Patched!")

    if kwargs['commit']:
        message = """Release OpenStack-Ansible {}/{}

        """.format(kwargs['branch'], version)
        releases_repo.index.add([deliverable_file_path])
        releases_repo.index.commit(message)


def update_openstack_projects():
    """ Bump OpenStack projects and their files in our roles"""
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

    pass


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(logger)
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
    logger.info("Downloading the requirements repo")
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

    logger.info("Displaying results")
    with open((kwargs['workdir'] +
               '/openstack-ansible/global-requirement-pins.txt'), 'r') as gr:
        for requirement in requirementslib.parse(gr):
            cstrs = [cstr for cstr in requirementslib.parse(upper_constraints)
                     if cstr.name == requirement.name]
            pypi_pkg = get_package_version(pypi, requirement.name)
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
@click_log.simple_verbosity_option(logger)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option("--external-roles/--no-external-roles", default=False)
@click.option("--release-notes/no-release-notes", default=True)
def bump_arr(**kwargs):
    """ Update Roles in Ansible Role Requirements for branch,
        effectively freezing them.
        Calls fetch_reno
        Requires Workdir
        Requires a clean OA.
    """

    # Discover branch currently tracking
    oa_folder = kwargs['workdir'] + '/openstack-ansible/'
    oa = Repo(oa_folder)
    tracking_branch = oa.active_branch.tracking_branch()
    if tracking_branch is None:
        raise SystemExit("Not tracking a remote branch, OA unclean")
    remote_branch = "{}".format(tracking_branch.remote_head)

    # Load ARRrrrr (pirate mode)
    arr, ind, bsi = load_yaml(kwargs['workdir'] + ARR_PATH)

    # Cleanup before doing anything else
    click.confirm("Deleting all the role folders in workspace {}\n"
                  "Are you sure? ".format(kwargs['workdir']))

    # Clone only the OpenStack hosted roles
    regex = re.compile(OPENSTACK_REPOS + '/(.*)')
    for role in arr:
        logger.info("Updating {}".format(role['name']))
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
                logger.info("Processing its release notes")
                subprocess.call(
                    ["rsync", "-aq",
                     "{}/releasenotes/notes/*.yaml".format(role_path),
                     "{}/releasenotes/notes/".format(oa_folder)])

        elif kwargs['external_roles']:
            # For external roles, don't clone,
            # find the latest "matching" tag (patch release)
            # or the latest sha (master)
            role['version'] = find_latest_version(role['src'],
                                                  role['version'])

    with open(kwargs['workdir'] + ARR_PATH, 'w') as role_req_file:
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.block_seq_indent = bsi
        yaml.indent = ind
        yaml.dump(arr, role_req_file)
        logger.info("Patched!")

    logger.info("Processing Release Notes")


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(logger)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option('--version', default="auto")
@click.option(*COMMIT_OPT, **COMMIT_PARAMS)
def bump_oa_release_number(**kwargs):
    """ Update OpenStack Ansible version number in code """

    oa_folder = kwargs['workdir'] + '/openstack-ansible/'
    fpth, cver = getCurrentOSAVersion(oa_folder)
    logger.info("Current version {} in {}".format(cver, fpth))

    if cver == "master":
        click.confirm("Master should only changed when necessary. Sure?")

    if kwargs['version'] == "auto":
        logger.info("Guessing next version")
        cver_l = cver.split(".")
        try:
            cver_l[-1] = str(int(cver_l[-1]) + 1)
        except ValueError as vee:
            logger.error("Cannot up the version: {}".format(vee))
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
    logger.info("Updated the version in repo to {}".format(nver))

    if kwargs['commit']:
        message = """Set OpenStack-Ansible release to {}

        """.format(nver)
        repo = Repo(oa_folder)
        repo.index.add([fpth])
        repo.index.commit(message)

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
    # update_os_release_file()
    # check_global_requirement_pins()
    # bump_arr()
    bump_oa_release_number()

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
