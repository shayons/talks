# Coffee-bag artwork

Created with the built-in image-generation tool on 2026-09-08. These are generic packaging illustrations, not photographs of real inventory. No brand, certification, country, price, or product name is embedded in the artwork.

| Asset | Roast levels |
| --- | --- |
| `coffee-light.webp` | light, medium-light |
| `coffee-medium.webp` | medium; fallback |
| `coffee-dark.webp` | medium-dark, dark |

The initial generations returned visible checkerboard backgrounds. One edit per asset replaced them with warm cream studio backgrounds. Shipped files are opaque 640 × 640 WebP images, encoded with `cwebp -q 85 -resize 640 640`. No external image service is used at runtime.

The UI labels packaging illustrative and renders product identity, USD price, and stock from canonical response fields. Update `catalog.py` when real product photography becomes available.

## Generation prompts

### light

Use case: product-mockup. Asset type: isolated coffee-bag product artwork for the Coffee & queries educational coffee catalog. Make one photorealistic standing specialty-coffee pouch, natural pale kraft paper with a quiet ochre paper label. Premium but modest folded flat-bottom paper bag with sealed top, realistic slight creases and tactile paper grain. Near-front three-quarter view, entire bag centered, generous clear margin around it, no cropping. Soft studio light from upper left. Transparent background, preserve alpha, with only a subtle natural contact shadow. A plain rectangular label with a tiny abstract coffee-bean mark, no words, no country, price, weight, certifications, brand logo, or product claims. No other objects, loose beans, table, props, scenery, hands, border, or watermark. Square product photograph; bag occupies about 75 percent of image height. The product identity, roast, price and availability will be rendered as live text beside this illustrative packaging.

### medium

Use case: product-mockup. Asset type: isolated coffee-bag product artwork for the Coffee & queries educational coffee catalog. Make one photorealistic standing specialty-coffee pouch, muted forest-green matte paper with a warm ivory paper label. Premium but modest folded flat-bottom paper bag with sealed top, realistic slight creases and tactile paper grain. Near-front three-quarter view, entire bag centered, generous clear margin around it, no cropping. Soft studio light from upper left. Transparent background, preserve alpha, with only a subtle natural contact shadow. A plain rectangular label with a tiny abstract coffee-bean mark, no words, no country, price, weight, certifications, brand logo, or product claims. No other objects, loose beans, table, props, scenery, hands, border, or watermark. Square product photograph; bag occupies about 75 percent of image height. The product identity, roast, price and availability will be rendered as live text beside this illustrative packaging.

### dark

Use case: product-mockup. Asset type: isolated coffee-bag product artwork for the Coffee & queries educational coffee catalog. Make one photorealistic standing specialty-coffee pouch, deep espresso-brown matte paper with a warm ivory paper label. Premium but modest folded flat-bottom paper bag with sealed top, realistic slight creases and tactile paper grain. Near-front three-quarter view, entire bag centered, generous clear margin around it, no cropping. Soft studio light from upper left. Transparent background, preserve alpha, with only a subtle natural contact shadow. A plain rectangular label with a tiny abstract coffee-bean mark, no words, no country, price, weight, certifications, brand logo, or product claims. No other objects, loose beans, table, props, scenery, hands, border, or watermark. Square product photograph; bag occupies about 75 percent of image height. The product identity, roast, price and availability will be rendered as live text beside this illustrative packaging.

## Background correction

Applied separately to each generation:

Edit this coffee-bag image only: replace the entire gray-and-white checkerboard with one smooth, solid warm cream studio background (#f3ebe0), including the ground beneath the bag. No checker pattern anywhere. Keep the bag, paper texture, label, coffee-bean symbol, color and camera angle unchanged. Keep a soft natural contact shadow beneath the bag. This is an opaque image with a plain cream background, not transparency. No text or added objects. Center the complete bag in a square composition.
