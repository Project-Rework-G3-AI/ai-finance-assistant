import pymupdf


def render_pdf_pages(
    pdf_bytes: bytes,
    dpi: int = 180
) -> list[dict]:
    """
    Render setiap halaman PDF menjadi JPEG.
    
    """

    pages = []

    with pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    ) as pdf:

        for page_index, page in enumerate(pdf):

            pixmap = page.get_pixmap(
                dpi=dpi,
                colorspace=pymupdf.csRGB,
                alpha=False
            )

            image_bytes = pixmap.tobytes("jpeg")

            pages.append({
                "page_number": page_index + 1,
                "image_bytes": image_bytes,
                "mime_type": "image/jpeg"
            })

    return pages
