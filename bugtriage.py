#!/usr/bin/env python
""" Tools for bug triage"""
# Stdlib
import logging
import os
# Extra packages
import click
import click_log
from launchpadlib.launchpad import Launchpad
from toolkit import CONTEXT_SETTINGS

# Workdir and other click defaults for this script
WORK_DIR_OPT = ['-w', '--workdir']
WORK_DIR_OPT_PARAMS = dict(default='/tmp/bugtriage',
                           type=click.Path(exists=True, file_okay=False,
                                           dir_okay=True, writable=True,
                                           resolve_path=True),
                           help='Work directory: Temporary workspace folder',
                           show_default=True)

# CODE STARTS HERE
LOGGER = logging.getLogger(__name__)
click_log.basic_config(LOGGER)

# STATIC VARS
STATES = ['New']
ORDERBY = '-datecreated'


@click.command(context_settings=CONTEXT_SETTINGS)
@click_log.simple_verbosity_option(LOGGER)
@click.option(*WORK_DIR_OPT, **WORK_DIR_OPT_PARAMS)
def generate_page(**kwargs):
    """ Generate a bug triage page to help the triaging process
    """

    cache_folder = kwargs['workdir'] + '/cache/'
    if not os.path.lexists(cache_folder):
        LOGGER.info("Creating cache folder")
        os.mkdir(cache_folder)

    launchpad = Launchpad.login_anonymously('osa_toolkit',
                                            'production', cache_folder,
                                            version='devel')
    oa = launchpad.projects['openstack-ansible']
    for bug in oa.searchTasks(status=STATES, order_by=ORDERBY):
        # bug title is like:
        # '
        # Bug #1724025 in openstack-ansible:
        # invalid regular expression..."
        # '
        bug_name = "".join(bug.title.split(":")[1:])
        print("#link {link}\n\t{name}".format(link=bug.web_link,
                                              name=bug_name))
