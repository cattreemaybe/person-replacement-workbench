from pathlib import Path

from PIL import Image, ImageDraw


root = Path(__file__).resolve().parent / "test-assets"
root.mkdir(exist_ok=True)

person = Image.new("RGB", (500, 700), "#d9c9b2")
draw = ImageDraw.Draw(person)
draw.ellipse((158, 98, 342, 282), fill="#d79d76")
draw.rounded_rectangle((112, 280, 388, 760), radius=120, fill="#384f68")
draw.ellipse((209, 170, 225, 186), fill="#332a25")
draw.ellipse((275, 170, 291, 186), fill="#332a25")
draw.arc((210, 195, 290, 250), start=15, end=165, fill="#773c38", width=7)
person.save(root / "person.png")

scene = Image.new("RGB", (1000, 700), "#c6d6cf")
draw = ImageDraw.Draw(scene)
draw.rectangle((0, 440, 1000, 700), fill="#9e8469")
draw.ellipse((80, 50, 220, 190), fill="#e8c879")
draw.rectangle((70, 280, 330, 450), fill="#755744")
draw.rectangle((740, 110, 910, 450), fill="#8799a1")
draw.ellipse((500, 180, 640, 320), fill="#bb896a")
draw.rounded_rectangle((455, 300, 685, 730), radius=100, fill="#703b36")
scene.save(root / "scene.png")
