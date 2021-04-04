# -*- coding: utf-8 -*-
from invoke import task

import os
import sys
import time
import yaml
import contextlib

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


@contextlib.contextmanager
def step(what):
    green = "\033[32;1m"
    blue = "\033[34;1m"
    yellow = "\033[33;1m"
    reset = "\033[0m"
    now = time.time()
    print(f"{blue}▶ {yellow}{what}{reset}", file=sys.stderr)
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
def build(c):
    """Build production content"""
    c.run("[ $(git rev-parse --abbrev-ref HEAD) = latest ]")
    c.run("rm -rf .final/*")
    conf = "site-production.yaml"
    media = yaml.safe_load(open(conf))['media_url']
    with step("run Hyde"):
        c.run('hyde -x gen -c %s' % conf)
    with c.cd(".final"):
        # Image optimization
        with step("convert JPG to WebP"):
            c.run("find media/images -type f -name '*.jpg' -print"
                  " | xargs -n1 -P4 -i cwebp -q 84 -af '{}' -o '{}'.webp")
        with step("convert JPG to AVIF"):
            libavif = c.run("nix-build --no-out-link -E '(import <nixpkgs>{}).libavif'").stdout.strip()
            c.run("find media/images -type f -name '*.jpg' -print"
                  f" | xargs -n1 -P4 -i {libavif}/bin/avifenc --codec aom --yuv 420 "
                  "                                           --min 20 --max 25 '{}' '{}'.avif"
                  " > /dev/null")
        with step("optimize JPG"):
            jpegoptim = c.run("nix-build --no-out-link "
                              "  -E 'with (import <nixpkgs>{}); "
                              "        jpegoptim.override { libjpeg = mozjpeg; }'").stdout.strip()
            c.run("find media/images -type f -name '*.jpg' -print0"
                  "  | sort -z "
                  f" | xargs -0 -n10 -P4 {jpegoptim}/bin/jpegoptim --max=84 --all-progressive --strip-all")
        with step("optimize PNG"):
            c.run("find media/images -type f -name '*.png' -print0"
                  " | sort -z "
                  " | xargs -0 -n10 -P4 pngquant --skip-if-larger --strip "
                  "                              --quiet --ext .png --force "
                  "|| true")
        with step("convert PNG to WebP"):
            c.run("find media/images -type f -name '*.png' -print"
                  " | xargs -n1 -P4 -i cwebp -z 8 '{}' -o '{}'.webp")
        with step("remove WebP/AVIF files not small enough"):
            c.run("for f in media/images/**/*.{webp,avif}; do"
                  "  orig=$(stat --format %s ${f%.*});"
                  "  new=$(stat --format %s $f);"
                  "  (( $orig*0.90 > $new )) || rm $f;"
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
def push(c):
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
          "".format(" ".join(hosts)), hide=False)
    c.run("xdg-open goaccess.html")
