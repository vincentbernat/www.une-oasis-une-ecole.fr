# -*- coding: utf-8 -*-
from invoke import task

import os
import sys
import time
import yaml
import csv
import re
import datetime
import contextlib
import urllib
import xml.etree.ElementTree as ET

conf = "site-production.yaml"
media = yaml.safe_load(open(conf))['media_url']
hosts = ["web03.luffy.cx", "web04.luffy.cx", "web05.luffy.cx", "web06.luffy.cx"]


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


@contextlib.contextmanager
def step(what):
    green = "\033[32;1m"
    blue = "\033[34;1m"
    yellow = "\033[33;1m"
    reset = "\033[0m"
    now = time.time()
    print(f"{blue}▶ {yellow}{what}{reset}...", file=sys.stderr)
    yield
    elapsed = int(time.time() - now)
    print(f"{blue}▶ {green}{what}{reset} ({elapsed}s)",
          file=sys.stderr)


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
    c.run('hyde -x serve -a 0.0.0.0', pty=True, hide=False)


@task
def prune(c, before='1 year ago'):
    """Prune old commits."""
    with c.cd(".final"):
        out = c.run(f"git log --before='{before}' --pretty=format:%H | head -1").stdout.strip()
        assert(out != "")
        c.run(f"echo {out} > .git/shallow")
        c.run("git gc --prune=now")


@task
def build(c):
    """Build production content"""
    c.run('git annex lock && [ -z "$(git status --porcelain)" ]')
    c.run("rm -rf .final/*")
    with step("run Hyde"):
        c.run('hyde -x gen -c %s' % conf)
    with c.cd(".final"):
        # Fix HTML (<source> is an empty tag)
        with step("fix HTML"):
            c.run(r"find . -name '*.html' -print0"
                  r"| xargs -0 sed -i 's+\(<source[^>]*>\)</source>+\1+g'")
            c.run(r"find . -name '*.html' -print0"
                  r"| xargs -0 sed -i 's+\(<track[^>]*>\)</track>+\1+g'")

        # Image optimization
        with step("optimize images"):
            c.run("cd .. ; NIX_PATH=target=$PWD/.final/media/images nix build --impure .#build.optimizeImages")
            c.run("cp -r --no-preserve=mode ../result/* media/images/. && rm ../result")

        # We want to prefer JPGs if their sizes are not too large.
        # The idea is that:
        #  - JPG decoding is fast
        #  - JPG has progressive decoding
        #
        # We prefer smaller WebPs over AVIFs as all browsers
        # supporting AVIF also support WebP.
        with step("remove WebP/AVIF files not small enough"):
            c.run("for f in media/images/**/*.{webp,avif}; do"
                  "  orig=$(stat --format %s ${f%.*});"
                  "  new=$(stat --format %s $f);"
                  "  (( $orig*0.90 > $new )) || rm $f;"
                  "done", shell="/bin/zsh")
            c.run("for f in media/images/**/*.avif; do"
                  "  [[ -f ${f%.*}.webp ]] || continue;"
                  "  orig=$(stat --format %s ${f%.*}.webp);"
                  "  new=$(stat --format %s $f);"
                  "  (( $orig > $new )) || rm $f;"
                  "done", shell="/bin/zsh")
            c.run(r"""
printf "     %10s %10s %10s\n" Original WebP AVIF
printf " PNG %10s %10s %10s\n" \
   $(find media/images -name '*.png' | wc -l) \
   $(find media/images -name '*.png.webp' | wc -l) \
   $(find media/images -name '*.png.avif' | wc -l)
printf " JPG %10s %10s %10s\n" \
   $(find media/images -name '*.jpg' | wc -l) \
   $(find media/images -name '*.jpg.webp' | wc -l) \
   $(find media/images -name '*.jpg.avif' | wc -l)
            """, hide='err')

        # Compute hash on various files
        with step("compute hash for static files"):
            for p in ['media/css/*.css']:
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
                    if ext in [".png", ".svg", ".ttf", ".woff", ".woff2"]:
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

        # Delete unwanted files
        c.run("find . -type f -name '.*' -delete")

        c.run("git add *")
        c.run("git diff --stat HEAD || true", pty=True, hide=False)
        if confirm("More diff?", default=True):
            c.run("env GIT_PAGER=less git diff --word-diff HEAD || true",
                  pty=True, hide=False)
        if confirm("Keep?", default=True):
            c.run('git commit -a -m "Autocommit"', hide=False)
        else:
            c.run("git reset --hard")
            c.run("git clean -d -f")
            raise RuntimeError("Build rollbacked")


@task
def push(c, clean=False):
    """Push built site to production"""
    with step("push to GitHub"):
        c.run("git push github")

    with c.cd(".final"):
        # Restore timestamps (this relies on us not truncating
        # history too often)
        with step("restore timestamps"):
            c.run('''
for f in $(git ls-tree -r -t --full-name --name-only HEAD); do
    touch -d $(git log --pretty=format:%cI -1 HEAD -- "$f") -h "$f";
done''')

    # media
    for host in hosts:
        with step(f"push media to {host}"):
            c.run("rsync --exclude=.git --copy-unsafe-links -rt "
                  ".final/media/ {}:/data/webserver/media.une-oasis-une-ecole.fr/".format(host))

    # HTML
    for host in hosts:
        with step(f"push HTML to {host}"):
            c.run("rsync --exclude=.git --exclude=media "
                  "--delete-delay --copy-unsafe-links -rt "
                  ".final/ {}:/data/webserver/www.une-oasis-une-ecole.fr/".format(host))
            c.run("ssh {} sudo systemctl reload nginx".format(host))

    for host in hosts:
        with step(f"clean images on {host}"):
            c.run("rsync --exclude=.git --copy-unsafe-links -rt "
                  "--delete-delay "
                  "--include='**/' "
                  "--include='*.avif' --include='*.webp' "
                  "--exclude='*' "
                  ".final/media/images "
                  "{}:/data/webserver/media.une-oasis-une-ecole.fr/".format(host))
    if clean:
        for host in hosts:
            with step(f"clean files on {host}"):
                c.run("rsync --exclude=.git --copy-unsafe-links -rt "
                      "--delete-delay --exclude=videos/\\*/ "
                      ".final/media/ "
                      "{}:/data/webserver/media.une-oasis-une-ecole.fr/".format(host))
