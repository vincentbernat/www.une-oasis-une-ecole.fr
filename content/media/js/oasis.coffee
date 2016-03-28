$ = window.jQuery
oasis = {}

#
# 0. Prefix free
#
oasis.prefixfree = ->
  pf = window.PrefixFree
  return if not pf?
  for property in pf.properties
    e = do (property) ->
      camelCased = window.StyleFix.camelCase(property)
      PrefixCamelCased = pf.prefixProperty(property, true)
      $.cssProps[camelCased] = PrefixCamelCased

#
# 1. Effects
#
oasis.effects = {}

# 1.1 Images
oasis.effects.images = (article) ->
  # Turn any article image into the appropriate class and randomize a bit the rotation
  nb = 0
  $("article p > img").parent()
    .addClass("oasis-image")
    .each (index, el) ->
      # Rotation
      r = Math.random() + 1
      r = -r if Math.random() > 0.5
      $(el).css(transform: "rotate(#{r}deg)")
      # Alternate side
      $(el).addClass("oasis-image-alternate") if (nb++) % 2 != 0

# 1.2 Menu
oasis.effects.menu = ->
  # Handle menu by changing the image appropriately
  carousel = $("nav .oasis-carousel")
  menu = $("nav .oasis-menu")

  toggle = (enter, nb) ->
    carousel.find("img").each (index, el) ->
      if index == nb
        $(el).toggleClass("selected", enter).toggleClass("unselected", !enter)

  carousel.find("img").addClass("unselected")
  carousel.find("img").first().addClass("active") if !carousel.find("img.active").length
  menu.find("li")
    .on("mouseenter", (event) -> toggle(true, $(@).index()))
    .on("mouseleave", (event) -> toggle(false, $(@).index()))

#
# Final: execute everything when jQuery is ready
#
$ ->
  oasis.prefixfree()
  oasis.effects.images()
  oasis.effects.menu()
