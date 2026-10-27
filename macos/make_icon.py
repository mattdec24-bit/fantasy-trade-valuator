"""Generate the app's field/route icon with the bundled Pillow, no remote assets."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw

output = Path(sys.argv[1]); output.mkdir(parents=True, exist_ok=True)
image = Image.new('RGBA', (1024, 1024))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((40, 40, 984, 984), radius=220, fill='#163e33')
for y in (245, 420, 595, 770):
    draw.line((135, y, 889, y), fill='#3a5e4b', width=7)
    for x in (170, 855): draw.line((x, y-25, x, y+25), fill='#668064', width=6)
draw.line((250, 660, 250, 385, 745, 385), fill='#d4ed89', width=48, joint='curve')
draw.polygon(((720, 300), (830, 385), (720, 470)), fill='#d4ed89')
draw.line((775, 525, 775, 700, 395, 700), fill='#e8ecdc', width=34, joint='curve')
draw.polygon(((415, 635), (330, 700), (415, 765)), fill='#e8ecdc')
draw.ellipse((195, 605, 305, 715), fill='#d4ed89')
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        image.resize((size*scale, size*scale), Image.Resampling.LANCZOS).save(output / f'icon_{size}x{size}{"@2x" if scale == 2 else ""}.png')
