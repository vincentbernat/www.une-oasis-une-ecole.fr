oasis = {}

#
# 1. Effects
#
oasis.effects = {}

# 1.1 Images
oasis.effects.images = (article) ->
  # Is browser modern enough?
  if typeof document.querySelectorAll != "function"
    return
  # Turn any article image into the appropriate class and randomize a bit the rotation
  nb = 0
  els = document.querySelectorAll("article p > img")
  for el in els
    el = el.parentNode
    el.className += " oasis-image"
    # Rotation
    r = Math.random() + 1
    r = -r if Math.random() > 0.5
    el.style.transform = el.style.webkitTransform = "rotate(#{r}deg)"
    el.className += " oasis-image-alternate" if (nb++) % 2 != 0

# 1.2 Menu
oasis.effects.menu = ->
  # Is browser modern enough?
  if typeof document.querySelectorAll != "function"
    return
  # Handle menu by changing the image appropriately
  carousel = document.querySelector("nav .oasis-carousel")
  menu = document.querySelector("nav .oasis-menu")

  toggle = (enter, nb) ->
    for el, index in carousel.querySelectorAll("img")
      if index == nb
        if enter
          el.classList.add 'selected'
          el.classList.remove 'unselected'
        else
          el.classList.add 'unselected'
          el.classList.remove 'selected'

  for el in carousel.querySelectorAll("img")
    el.classList.add "unselected"
  carousel.querySelector("img").classList.add 'active'
  for el, index in menu.querySelectorAll("li")
    f = (index) ->
      el.addEventListener("mouseenter", (event) -> toggle(true, index))
      el.addEventListener("mouseleave", (event) -> toggle(false, index))
    f(index)

#
# Final: execute everything
#
oasis.effects.images()
oasis.effects.menu()
