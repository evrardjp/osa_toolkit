#!/usr/bin/env python
""" Update OpenStack-Ansible Role maturity table from their respective repos
"""
# Stdlib
from datetime import datetime
import codecs
import logging
import os
import shutil
# Extra Packages
import click
import click_log
from git import Repo
from jinja2 import Template
from toolkit import CONTEXT_SETTINGS, OPENSTACK_REPOS, load_yaml

# Workdir
PROJECT_CONFIG = OPENSTACK_REPOS + "-infra/project-config"
WORK_DIR_OPT = ['-w', '--workdir']
WORK_DIR_OPT_PARAMS = dict(default='/tmp/maturity',
                           type=click.Path(exists=True, file_okay=False,
                                           dir_okay=True, writable=True,
                                           resolve_path=True),
                           help='Work directory: Temporary workspace folder')
COMMIT_OPT = ['--commit/--no-commit']
COMMIT_PARAMS = dict(default=False,
                     help='commits automatically the generated changes')
# Deprecated roles data:
DEPRECATED_ROLES = [
    # {
    #     'maturity_level': 'retired',
    #     'name': '',
    #     'created_during': '',
    #     'retired_during': '',
    # },
    {
        'maturity_level': 'retired',
        'name': 'openstack-ansible-security',
        'created_during': 'liberty',
        'retired_during': 'pike',
    },
    {
        'maturity_level': 'retired',
        'name': 'pip_lock_down',
        'created_during': 'liberty',
        'retired_during': 'newton',
    },
]
# CODE STARTS HERE
LOGGER = logging.getLogger(__name__)
click_log.basic_config(LOGGER)


def generate_maturity_matrix_html(roles=None):
    """ From Information about roles, generate a matrix, return html."""
    script_dir = os.path.dirname(__file__)
    template_path = os.path.join(script_dir, 'maturity_table.html.j2')
    with codecs.open(template_path, encoding='utf-8') as mt_tmpl_fh:
        mt_tmpl = mt_tmpl_fh.read()
    template = Template(mt_tmpl)
    return template.render(roles=roles)


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
@click.option(*COMMIT_OPT, **COMMIT_PARAMS)
def update_role_maturity_matrix(**kwargs):
    """ Update in tree the maturity.html file
    by fetching each of the role's metadata
    inside your workdir
    """
    LOGGER.info("Workspace folder is %s" % kwargs['workdir'])
    matrix = []
    # Find projects through Project Config
    LOGGER.info("Cloning OpenStack Project Config")
    pjct_cfg_path = kwargs['workdir'] + '/project-config'
    if os.path.lexists(pjct_cfg_path):
        LOGGER.info("Project config already exists, updating.")
        # If exists, ensure up to date
        pjct_cfg_repo = Repo(pjct_cfg_path)
        pjct_cfg_repo_o = pjct_cfg_repo.remotes.origin
        pjct_cfg_repo_o.pull()
    else:
        _ = Repo.clone_from(
            url=PROJECT_CONFIG,
            to_path=pjct_cfg_path,
            branch="master")

    LOGGER.info("Cloning OpenStack-Ansible")
    oa_folder = kwargs['workdir'] + '/openstack-ansible'
    if os.path.lexists(oa_folder):
        LOGGER.info("openstack-ansible already exists, updating.")
        # If exists, ensure up to date
        oa_repo = Repo(oa_folder)
        oa_repo_o = oa_repo.remotes.origin
        oa_repo_o.pull()
    else:
        oa_repo = Repo.clone_from(
            url="{}/openstack-ansible".format(OPENSTACK_REPOS),
            to_path=oa_folder,
            branch="master")
    arr, _, _ = load_yaml('{}/ansible-role-requirements.yml'.format(oa_folder))

    # For each project, get the metadata
    pjcts, _, _ = load_yaml("{}/gerrit/projects.yaml".format(pjct_cfg_path))
    for project in pjcts:
        role = dict()
        if project['project'].startswith('openstack/openstack-ansible-'):
            project_fullname = project['project'].split('/')[-1]
            project_shortname = project_fullname.split(
                'openstack-ansible-')[-1]
        elif project['project'] == 'openstack/ansible-hardening':
            project_fullname = 'ansible-hardening'
            project_shortname = 'ansible-hardening'
        else:
            continue
        LOGGER.info("Loading metadata for %s" % project_shortname)

        project_path = "{}/{}".format(kwargs['workdir'], project_fullname)
        if os.path.lexists(project_path):
            # If exists, ensure up to date
            project_repo = Repo(project_path)
            origin = project_repo.remotes.origin
            origin.pull()
        else:
            # cloning the project!
            project_repo = Repo.clone_from(
                url="{}/{}".format(OPENSTACK_REPOS, project_fullname),
                to_path=project_path,
                branch="master")

        role['name'] = project_shortname
        # Example of standard metadata:
        # galaxy_info:
        #   author: rcbops
        #   description: Installation and setup of neutron
        #   company: Rackspace
        #   license: Apache2
        #   min_ansible_version: 2.2
        #   platforms:
        #     - name: Ubuntu
        #       versions:
        #         - xenial
        #     - name: EL
        #       versions:
        #         - 7
        #     - name: opensuse
        #       versions:
        #         - 42.1
        #         - 42.2
        #         - 42.3
        #   categories:
        #     - cloud
        #     - python
        #     - neutron
        #     - development
        #     - openstack
        try:
            std_meta, _, _ = load_yaml(
                "{}/meta/main.yml".format(project_path))
        except IOError:
            # If no meta/main (like ops), don't count as
            # a role to update.
            continue
        # Only take what you need
        role['opensuse'] = False
        role['ubuntu'] = False
        role['centos'] = False
        for platform in std_meta['galaxy_info']['platforms']:
            if platform['name'].lower() == 'opensuse':
                role['opensuse'] = True
                role['opensuse_versions'] = platform['versions']
            elif platform['name'].lower() == 'ubuntu':
                role['ubuntu'] = True
                role['ubuntu_versions'] = platform['versions']
            elif (platform['name'].lower() == 'centos' or
                  platform['name'].upper() == 'EL'):
                role['centos'] = True
                role['centos_versions'] = platform['versions']
        # Example of maturity info metadata:
        # maturity_info:
        #     status: complete
        #     created_during: mitaka
        try:
            osa_meta, _, _ = load_yaml(
                "{}/meta/openstack-ansible.yml".format(project_path))
        except IOError:
            role['maturity_level'] = 'unknown'
            role['created_during'] = 'unknown'
            role['retired_during'] = 'unknown'
        else:
            role['maturity_level'] = osa_meta['maturity_info']['status'].lower()
            role['created_during'] = \
                osa_meta['maturity_info']['created_during'].lower()
            role['retired_during'] = osa_meta['maturity_info'].get(
                'retired_during', 'unknown').lower()
        # Now checking presence in ansible-role-requirements.yml
        role['in_arr'] = any(
            arr_role['name'] == project_shortname for arr_role in arr
        )
        matrix.append(role)

    matrix.extend(DEPRECATED_ROLES)

    # Write file
    LOGGER.info("Patching OpenStack-Ansible")
    fpth = "doc/source/contributor/role-maturity-matrix.html"
    with codecs.open("{}/{}".format(oa_folder, fpth),
                     mode='w', encoding='utf-8') as matrix_fh:
        matrix_fh.write(generate_maturity_matrix_html(matrix))
    # Commit
    if kwargs['commit']:
        message = ("Updating roles maturity\n\n"
                   "Update for the {:%d.%m.%Y}\n").format(datetime.now())
        oa_repo.index.add([fpth])
        oa_repo.index.commit(message)
