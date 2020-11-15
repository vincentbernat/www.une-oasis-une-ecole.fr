oasis = {}

# 1.1 Images
oasis.images = (article) ->
  # Turn any article image into the appropriate class and randomize a bit the rotation
  nb = 0
  els = document.querySelectorAll("article p > img")
  for el in els
    el = el.parentNode
    el.className += " oasis-image"
    # Rotation
    r = Math.random() + 1
    r = -r if Math.random() > 0.5
    el.style.transform = "rotate(#{r}deg)"
    el.className += " oasis-image-alternate" if (nb++) % 2 != 0

#
# Final: execute everything
#
oasis.images()
