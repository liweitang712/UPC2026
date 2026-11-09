"""Replace a row-uniform RGB PDF colorbar image with equivalent vector strips."""

import argparse
from itertools import groupby
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject, NumberObject


def convert(source, destination):
    writer = PdfWriter(clone_from=str(source))
    if len(writer.pages) != 1:
        raise ValueError("Expected a single-page figure")
    page = writer.pages[0]
    if len(page.images) != 1:
        raise ValueError("Expected one colorbar image")
    image = page.images[0]
    bitmap = image.image
    if bitmap.mode != "RGB":
        raise ValueError("Expected an RGB colorbar")

    colors = []
    for y in range(bitmap.height):
        color = bitmap.getpixel((0, y))
        if any(bitmap.getpixel((x, y)) != color for x in range(bitmap.width)):
            raise ValueError("Image varies horizontally and is not a vertical colorbar")
        colors.append(color)

    stream = DecodedStreamObject()
    operators = []
    first = 0
    for color, group in groupby(colors):
        count = sum(1 for _ in group)
        bottom = 1 - (first + count) / bitmap.height
        height = count / bitmap.height
        operators.append(" ".join(f"{channel / 255:.9f}" for channel in color) + " rg")
        operators.append(f"0 {bottom:.9f} 1 {height:.9f} re f")
        first += count
    stream.set_data(("\n".join(operators) + "\n").encode("ascii"))
    stream.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 1, 1)]),
    })
    resources = page["/Resources"]["/XObject"]
    key = next(key for key in resources if resources[key].get("/Subtype") == "/Image")
    resources[key] = writer._add_object(stream)
    with destination.open("wb") as output:
        writer.write(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    convert(args.source, args.destination)
