""" Convenient functions for releasing and other
    openstack-ansible purposes
"""
from datetime import datetime
import os
import re

from git import cmd as gitcmd           # GitPython package
from git import Repo
from ruamel.yaml.util import load_yaml_guess_indent


# Generic URLs
OPENSTACK_REPOS = "https://git.openstack.org/openstack"
PROJECT_CONFIG_REPO = OPENSTACK_REPOS + "-infra/project-config"
PYPI_URL = "https://pypi.python.org/pypi"

# Default variables for click help behavior
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


def load_yaml(path, mode='r'):
    """ Extract contents and indent details
        of a YAML file.
        Returns a tuple
        (data, indentation, block_seq_indent)
        that can be conviently used when writing:
        YAML().block_seq_indent
        YAML().indent
    """
    with open(path, mode) as fhdle:
        (data, ind, bsi) = load_yaml_guess_indent(fhdle)
        return (data, ind, bsi)


def get_pypi_version(pypi_connection, pkg_name):
    """Get the current package version from PyPI.
    Expects a xmlrpclib connection to PyPi server
    and a package name as mandatory arguments.
    """
    pkg_result = [v for v in pypi_connection.package_releases(pkg_name, True)
                  if not re.compile('a|b|rc').search(v)]
    if pkg_result:
        pkg_version = pkg_result[0]
    else:
        pkg_version = 'Not available.'

    return pkg_version


def get_oa_version(osa_folder):
    """ Fetches the current OpenStack-Ansible version.
    Folder is the path to openstack-ansible without
    the end slash.
    """

    for filename in ["group_vars/all/all.yml",
                     "playbooks/inventory/group_vars/all.yml"]:
        var_file = "{}/{}".format(osa_folder, filename)
        if os.path.exists(var_file):
            data, _, _ = load_yaml(var_file)
            if data.get('openstack_release'):
                return filename, data.get('openstack_release')


def find_latest_remote_ref(url, reference, guess=True):
    """ Discovers, from a git remote, the latest
        "appropriate" tag/sha based on a reference:
        If reference is a branch, returns the sha
        for the head of the branch.
        If reference is a tag, find the latest patch
        release of the same tag line.
    """
    # Use GitPtyhon git.cmd to avoid fetching repos
    # as listing remotes is not implemented outside Repo use
    gcli = gitcmd.Git()
    # this stores a sha for a matching branch/tag
    # tag will watch if ending with a number
    # (so v11.1, 1.11.1rc1 would still match)
    regex = re.compile('(?P<sha>[0-9a-f]{40})\t(?P<fullref>'
                       'refs/heads/(?P<branch>.*)'
                       '|refs/tags/(?P<tag>.*(\d|-eol)))')

    # search_ver will become ["master"], ["eol-mitaka"],
    # ["stable/pike"], ["16", "1", "9"]
    search_ver = reference.split('.')

    # For EOL tag matching
    if 'stable/' in reference:
        eol_tag = reference.strip('stable/') + '-eol'

    # sadly we can't presume the ls-remote list will be sorted
    # so we have to find out ourselves.
    patch_releases = []

    for remote in gcli.ls_remote('--refs', url).splitlines():
        m = regex.match(remote)
        # First, start to match the remote result with a branchname
        if m and m.group('branch') and m.group('branch') == reference:
            return m.group('sha')
        # Try to match EOL tag
        elif m and m.group('tag') == eol_tag:
            return eol_tag
        # Then try to find closest matching tags if guess work is allowed
        elif m and m.group('tag') and guess:
            ref_of_tag = m.group('tag').split('.')
            # keep a tag if it's almost the same (only last part changes)
            # as what we are looking for.
            # Store its reference and sha.
            if ref_of_tag[0:-1] and ref_of_tag[0:-1] == search_ver[0:-1]:
                # store only the last bit, space efficient!
                patch_releases.append(ref_of_tag[-1])

    # Returns the highest value if something was found
    if patch_releases:
        search_ver[-1] = max(patch_releases)
        return ".".join(search_ver)
    # Nothing else found: Return original reference.
    return reference


def tracking_branch_name(git_folder):
    """ Returns the branch name of the repo
    you are currently tracking.
    """
    repo = Repo(git_folder)
    tracking_branch = repo.active_branch.tracking_branch()
    if tracking_branch is None:
        raise ValueError(
            "{} is not tracking any remote branch".format(git_folder))
    return "{}".format(tracking_branch.remote_head)


def bump_project_sha_with_comments(match, previous_line):
    """ Take a line like:
    requirements_git_install_branch: 0143d0c2c9fc67380a4ae8e505a9a3fb55c0e888 # HEAD of "stable/pike" as of 11.09.2017
    and updates the sha, and the date, based on the branch found in the line.
    The information from previous_line contains the remote and its project (to validate data)
    """
    # Ensure previously saved line is the same as current line before
    # patching
    if previous_line['project'] != match.group('project'):
        raise SystemExit
    data = {
        "project": previous_line['project'],
        "branch": match.group('branch'),
        "sha": find_latest_remote_ref(previous_line['remote'], match.group('branch')),
        "date": '{:%d.%m.%Y}'.format(datetime.now())
    }
    return ('{project}_git_install_branch: '
            '{sha} # HEAD of "{branch}" as of '
            '{date}').format(**data)
