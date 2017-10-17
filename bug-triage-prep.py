#!/usr/bin/env python
""" Generate a list of bugs for next bugtriage"""
from launchpadlib.launchpad import Launchpad


# STATIC VARS
CACHEDIR = "/tmp/launchpadlib/cache/"
STATES = ['New']
ORDERBY = '-datecreated'

if __name__ == '__main__':
    launchpad = Launchpad.login_anonymously('osa_toolkit',
                                            'production', CACHEDIR,
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
