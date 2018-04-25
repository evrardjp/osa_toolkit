Release
=======

Release tooling for OpenStack-Ansible.

If you're not using default workspace folder (/tmp/releases), you should define it in all the commands.

Bumping master
--------------

Steps:

1. Checkout to master (not detached)
1. Suggest upper constraints pin changes:
   ``check-global-requirements``
1. unset release_changeid
1. unset next_release
1. Update Upstream Projects:
   ```bash
    bump-upstream-sources
   ```
1. Update role files by using the source branch updater lib
1. Git review

Freeze before master milestone release
--------------------------------------

Steps:

1. unset release_changeid
1. unset next_release
1. Go to OA folder
1. Ensure you're master (not detached)
1. Freeze ansible-role-requirements by doing:
   ```bash
    bump-ansible-role-requirements --external-roles
   ```
1. Freeze release number by doing
   ```bash
    bump-oa-release-number --version=17.0.0.0rc1 --commit
   ```
1. Edit commit message
1. git review in OA

Release after master milestone freeze
-------------------------------------

1. Go to OA folder
1. Ensure you're still at the right sha in your workspace folder (detached or not).
1. Emit release commit by doing (it will be based on checked out sha)
   ```bash
    update-os-release-file --branch=queens --version=17.0.0.0b3 --commit
   ```
1. Review in your release folder and git review
1. Unfreeze manually: git revert would remove the release notes.

Doing a stable release
----------------------

Steps:

1. unset release_changeid
1. unset next_release
1. Go to OA folder
1. Ensure you're at the head of your branch you want to release, or at the right sha.
   ```
   update-os-release-file --branch=pike --version=auto --commit
   ```
1. Go to release folder in workspace
1. Review and
   ```bash
   git review -t release_osa
   ```
1. Take review change id
   ```bash
   export release_changeid=$(git log HEAD^..HEAD | awk '/Change-Id/ {print $2}')
   ```
1. Ensure you're into OA folder, in a branch you can commit to (tracking what's needed)
1. Bump files
   ```bash
   bump-ansible-role-requirements
   bump-oa-release-number --version=auto
       export next_release= ...
   check-global-requirements
   bump-upstream-sources --commit
   #update-role-files --comit
   ```
1. Review OpenStack-Ansible folder and each of the roles.
1. git review -s
1. git commit --amend
1. git review -t release_osa

Maturity
========

This toolkit will manage the maturity matrix that appears on openstack-ansible
docs.

If you're not using default workspace folder (/tmp/maturity), you should define it in all the commands.

For now, only one command is implemented:
update-role-maturity-matrix (--commit)

Bug triage
==========

This toolkit will list all tools for triaging bugs and, in the future, make trends

If you're not using default workspace folder (/tmp/bugtriage), you should define it in all the commands.

For now, only one command is implemented:
generate-bug-triage-page . it generates a list of links for the https://etherpad.openstack.org/p/osa-bugtriage page.