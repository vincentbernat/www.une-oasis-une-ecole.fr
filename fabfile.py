from fabric.api import *
from fabric.contrib.console import confirm

import os
import shutil
import time
import glob
import hashlib
import yaml

os.umask(0022)
env.shell = "/bin/sh -c"
env.command_prefixes = [ 'export PATH=$HOME/.virtualenvs/hyde/bin:$PATH',
                         'export VIRTUAL_ENV=$HOME/.virtualenvs/hyde' ]

def _hyde(args):
    return local('hyde -x %s' % args)

@task
def regen():
    """Regenerate dev content"""
    local('rm -rf deploy')
    gen()

@task
def gen():
    """Generate dev content"""
    _hyde('gen')

@task
def serve():
    """Serve dev content"""
    _hyde('serve -a 0.0.0.0')

@task
def build():
    """Build production content"""
    local("git checkout master")
    local("rm -rf .final/*")
    conf = "site-production.yaml"
    media = yaml.load(file(conf))['media_url']
    _hyde('gen -c %s' % conf)
    with lcd(".final"):
        for p in [ 'media/js/*.js',
                   'media/css/*.css' ]:
            files = local("echo %s" % p, capture=True).split(" ")
            for f in files:
                # Compute hash
                md5 = local("md5sum %s" % f, capture=True).split(" ")[0][:8]
                print "[+] MD5 hash for %s is %s" % (f, md5)
                # New name
                root, ext = os.path.splitext(f)
                newname = "%s.%s%s" % (root, md5, ext)
                # Symlink
                local("ln -s %s %s" % (os.path.basename(f), newname))
                # Remove deploy/media
                f = f[len('media/'):]
                newname = newname[len('media/'):]
                if ext == ".png":
                    # Fix CSS
                    local("sed -i 's@%s@%s@g' media/css/*.css" % (f, newname))
                else:
                    # Fix HTML
                    local(r"find . -name '*.html' -type f -print0 | xargs -r0 sed -i "
                          '"'
                          r"s@\([\"']\)%s%s\1@\1%s%s\1@g"
                          '"' % (media, f, media, newname))
        # Fix permissions
        local(r"find * -type f -print0 | xargs -r0 chmod a+r")
        local(r"find * -type d -print0 | xargs -r0 chmod a+rx")


        local("git add *")
        local("git diff --stat HEAD")
        if confirm("More diff?", default=True):
            local("git diff --word-diff HEAD")
        if confirm("Keep?", default=True):
            local('git commit -a -m "Autocommit"')
        else:
            local("git reset --hard")
            local("git clean -d -f")
            abort("Build rollbacked")

@task
def push():
    """Push production content to remote locations"""
    # git
    local("git push github")
    local("git push ace.luffy.cx")

    # media.luffy.cx
    local("rsync --exclude=.git -a .final/media/ ace.luffy.cx:/srv/www/oasis/media/")

    # HTML
    local("rsync --exclude=.git -a .final/ ace.luffy.cx:/srv/www/oasis/")
