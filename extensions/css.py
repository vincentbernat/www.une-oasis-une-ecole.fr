# -*- coding: utf-8 -*-
"""
CSS plugins
"""

import subprocess
import random

from pyquery import PyQuery as pq
from hyde.plugin import Plugin


class CSSPrefixerPlugin(Plugin):
    """Run CSS prefixer"""
    def text_resource_complete(self, resource, text):
        if resource.source_file.kind not in ("less", "css"):
            return
        if self.site.config.mode == "development":
            minify = "false"
        else:
            minify = "true"
        p = subprocess.Popen(['node', '-e', """
var autoprefixer = require('autoprefixer');
var cssnano = require('cssnano');
var postcss = require('postcss');
var input = '';

process.stdin.setEncoding('utf8')
process.stdin.on('readable', function() {
  var chunk = process.stdin.read();
  if (chunk) {
    input += chunk;
  }
});
process.stdin.on('end', function() {
  postcss([autoprefixer, cssnano({preset: ['default', {
           reduceIdents: false, normalizeWhitespace: %s
        }]})])
        .process(input, { from: undefined })
        .then(function(result) {
          process.stdout.write(result.css.toString());
        });
});
        """ % minify], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        stdout, _ = p.communicate(text.encode('utf-8'))
        assert p.returncode == 0
        return stdout.decode('utf-8')


class ImageCSSPlugin(Plugin):
    """Add some CSS class to images and rotate them."""

    def __init__(self, *args, **kwargs):
        super(ImageCSSPlugin, self).__init__(*args, **kwargs)
        random.seed(12001)
        self._random_state = random.getstate()

    def text_resource_complete(self, resource, text):
        if resource.source_file.kind != 'html':
            return

        d = pq(text, parser='html')
        images = d.items('article p > img')
        nb = 0
        for img in images:
            el = img.parent()
            el.addClass("oasis-image")
            # Rotate
            random.setstate(self._random_state)
            r = random.uniform(-4, 4)
            self._random_state = random.getstate()
            el.css.transform = f"rotate({r:.3f}deg)"
            nb += 1
            # Horizontal position
            if nb % 2 == 0:
                el.addClass("oasis-image-alternate")
            # Lazy loading
            img.attr.loading = "lazy"

        return u'<!DOCTYPE html>\n' + d.outer_html()
