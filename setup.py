""" pip installable tools for working with OpenStack-Ansible """
from setuptools import setup

setup(
    name='osa_toolkit',
    version='0.1',
    py_modules=['release','maturity'],
    install_requires=[
        'Click',
        'click-log',
        'GitPython',
        'Jinja2',
        'requirements-parser',
        'ruamel.yaml',
        'semver'
    ],
    entry_points='''
        [console_scripts]
        check-global-requirements=release:check_global_requirement_pins
        bump-upstream-sources=release:bump_upstream_sources
        update-role-files=release:update_role_files
        bump-ansible-role-requirements=release:bump_arr
        bump-oa-release-number=release:bump_oa_release_number
        update-os-release-file=release:update_os_release_file
        update-role-maturity-matrix=maturity:update_role_maturity_matrix
    ''',
)
