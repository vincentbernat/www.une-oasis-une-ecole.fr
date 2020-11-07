# -*- coding: utf-8 -*-
from invoke import task

import os
import sys
import time
import yaml
import csv
import re
import datetime

os.environ["PATH"] = os.path.expanduser('~/.virtualenvs/hyde/bin') \
    + os.pathsep + os.environ["PATH"]
hosts = ["web03.luffy.cx", "web04.luffy.cx"]

def confirm(question, default=False):
    if default:
        suffix = "Y/n"
    else:
        suffix = "y/N"
    while True:
        response = input("{0} [{1}] ".format(question, suffix))
        response = response.lower().strip()  # Normalize
        # Default
        if not response:
            return default
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        err = "I didn't understand you. Please specify '(y)es' or '(n)o'."
        print(err, file=sys.stderr)


@task
def gen(c):
    """Generate dev content"""
    c.run('hyde -x gen')


@task(post=[gen])
def regen(c):
    """Regenerate dev content"""
    c.run('rm -rf deploy')


@task
def serve(c):
    """Serve dev content"""
    c.run('hyde -x serve -a 0.0.0.0', pty=True)


@task
def build(c):
    """Build production content"""
    c.run("[ $(git rev-parse --abbrev-ref HEAD) = latest ]")
    c.run("rm -rf .final/*")
    conf = "site-production.yaml"
    media = yaml.safe_load(open(conf))['media_url']
    c.run('hyde -x gen -c %s' % conf)
    with c.cd(".final"):
        # Convert JPG to webp
        c.run("find media/images -type f -name '*.jpg' -print"
              " | xargs -n1 -P4 -i cwebp -quiet -q 84 -af '{}' -o '{}'.webp")
        # Optimize JPG
        jpegoptim = c.run("nix-build --no-out-link "
                          "  -E 'with (import <nixpkgs>{}); "
                          "        jpegoptim.override { libjpeg = mozjpeg; }'").stdout.strip()
        c.run("find media/images -type f -name '*.jpg' -print0"
              "  | sort -z "
              f" | xargs -0 -n10 -P4 {jpegoptim}/bin/jpegoptim --max=84 --all-progressive --strip-all")
        # Optimize PNG
        c.run("find media/images -type f -name '*.png' -print0"
              " | sort -z "
              " | xargs -0 -n10 -P4 pngquant --skip-if-larger --strip "
              "                              --quiet --ext .png --force "
              "|| true")
        # Convert PNG to webp
        c.run("find media/images -type f -name '*.png' -print"
              " | xargs -n1 -P4 -i cwebp -quiet -z 6 '{}' -o '{}'.webp")
        # Remove WebP if size is greater than original file
        c.run("for f in media/images/**/*.webp; do"
              "  orig=$(stat --format %s ${f%.webp});"
              "  webp=$(stat --format %s $f);"
              "  (( $orig*0.90 > $webp )) || rm $f;"
              "done", shell="/bin/zsh")

        for p in ['media/js/*.js',
                  'media/css/*.css']:
            sed_html = []
            sed_css = []
            files = c.run("echo %s" % p, hide=True).stdout.strip().split(" ")
            for f in files:
                # Compute hash
                md5 = c.run("md5sum %s" % f,
                            hide="out").stdout.split(" ")[0][:14]
                sha = c.run("openssl dgst -sha256 -binary %s"
                            "| openssl enc -base64 -A" % f,
                            hide="out").stdout.strip()
                # New name
                root, ext = os.path.splitext(f)
                newname = "%s.%s%s" % (root, md5, ext)
                c.run("cp %s %s" % (f, newname))
                # Remove deploy/media
                f = f[len('media/'):]
                newname = newname[len('media/'):]
                if ext in [".png", ".svg", ".woff", ".woff2"]:
                    # Fix CSS
                    sed_css.append('s+{})+{})+g'.format(f, newname))
                if ext not in [".png", ".svg"]:
                    # Fix HTML
                    sed_html.append(
                        (r"s,"
                         r"\(data-\|\)\([a-z]*=\)\([\"']\){}{}\3,"
                         r"\1\2\3{}{}\3 \1integrity=\3sha256-{}\3 "
                         r"crossorigin=\3anonymous\3,"
                         r"g").format(media, f, media, newname, sha))
            if sed_css:
                c.run("find . -name '*.css' -type f -print0 | "
                      "xargs -r0 -n10 -P5 sed -i {}".format(
                          " ".join(("-e '{}'".format(x) for x in sed_css))))
            if sed_html:
                c.run("find . -name '*.html' -type f -print0 | "
                      "xargs -r0 -n10 -P5 sed -i {}".format(
                          " ".join(('-e "{}"'.format(x) for x in sed_html))))

        # Fix permissions
        c.run(r"find * -type f -print0 | xargs -r0 chmod a+r")
        c.run(r"find * -type d -print0 | xargs -r0 chmod a+rx")

        c.run("git add *")
        c.run("git diff --stat HEAD || true", pty=True)
        if confirm("More diff?", default=True):
            c.run("git diff --word-diff HEAD || true", pty=True)
        if confirm("Keep?", default=True):
            c.run('git commit -a -m "Autocommit"')
        else:
            c.run("git reset --hard")
            c.run("git clean -d -f")
            raise RuntimeError("Build rollbacked")


@task
def push(c):
    """Push built site to production"""
    c.run("git push github")

    with c.cd(".final"):
        # Restore timestamps (this relies on us not truncating
        # history too often)
        c.run('''
for f in $(git ls-tree -r -t --full-name --name-only HEAD); do
    touch -d $(git log --pretty=format:%cI -1 HEAD -- "$f") -h "$f";
done''')

    # media
    for host in hosts:
        c.run("rsync --exclude=.git --copy-unsafe-links -rt "
              ".final/media/ {}:/data/webserver/media.une-oasis-une-ecole.fr/".format(host))

    # HTML
    for host in hosts:
        c.run("rsync --exclude=.git --exclude=media "
              "--delete-delay --copy-unsafe-links -rt "
              ".final/ {}:/data/webserver/www.une-oasis-une-ecole.fr/".format(host))


@task
def analytics(c):
    """Get some stats"""
    c.run("for h in {};"
          "do ssh $h zcat -f /var/log/nginx/vincent.bernat.ch.log\\*"
          "   | grep -v atom.xml;"
          "done"
          " | LANG=en_US.utf8 goaccess "
          "       --ignore-crawlers "
          "       --http-protocol=no "
          "       --no-term-resolver "
          "       --no-ip-validation "
          "       --output=goaccess.html "
          "       --log-format=COMBINED "
          "       --ignore-panel=KEYPHRASES "
          "       --ignore-panel=REQUESTS_STATIC "
          "       --ignore-panel=GEO_LOCATION "
          "       --sort-panel=REQUESTS,BY_VISITORS,DESC "
          "       --sort-panel=NOT_FOUND,BY_VISITORS,DESC "
          "       --sort-panel=HOSTS,BY_VISITORS,DESC "
          "       --sort-panel=OS,BY_VISITORS,DESC "
          "       --sort-panel=BROWSERS,BY_VISITORS,DESC "
          "       --sort-panel=REFERRERS,BY_VISITORS,DESC "
          "       --sort-panel=REFERRING_SITES,BY_VISITORS,DESC "
          "       --sort-panel=STATUS_CODES,BY_VISITORS,DESC "
          "".format(" ".join(hosts)))
    c.run("xdg-open goaccess.html")
