import streamlit as st
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas
import math
from io import BytesIO
from copy import deepcopy

st.set_page_config(page_title="Mätning av planritning", layout="wide")

if "canvas_key" not in st.session_state:
    st.session_state.canvas_key = "canvas_0"

if "canvas_counter" not in st.session_state:
    st.session_state.canvas_counter = 0

if "canvas_data" not in st.session_state:
    st.session_state.canvas_data = {"objects": []}


def get_line_coords(line):

    cx = line["left"]
    cy = line["top"]

    x1 = cx + line["x1"]
    y1 = cy + line["y1"]

    x2 = cx + line["x2"]
    y2 = cy + line["y2"]

    if snap_mode:

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        if dx > dy:
            # Horisontell
            y2 = y1
        else:
            # Vertikal
            x2 = x1

    return x1, y1, x2, y2


def get_area_bounds(area):
    width = abs(area["width"] * area.get("scaleX", 1))
    height = abs(area["height"] * area.get("scaleY", 1))
    left = area["left"]
    top = area["top"]

    if area.get("originX") == "center":
        left -= width / 2
    elif area.get("originX") == "right":
        left -= width

    if area.get("originY") == "center":
        top -= height / 2
    elif area.get("originY") == "bottom":
        top -= height

    return left, top, left + width, top + height


def get_object_type(obj):
    return obj.get("type", "").lower()


def transform_canvas_data(
    canvas_data,
    zoom,
    crop_left,
    crop_top,
    display_scale=1.0,
    inverse=False,
):
    transformed = deepcopy(canvas_data)
    factor = 1 / (zoom * display_scale) if inverse else zoom * display_scale

    for obj in transformed.get("objects", []):
        if "left" in obj:
            if inverse:
                obj["left"] = obj["left"] / (zoom * display_scale) + crop_left
            else:
                obj["left"] = (obj["left"] - crop_left) * zoom * display_scale
        if "top" in obj:
            if inverse:
                obj["top"] = obj["top"] / (zoom * display_scale) + crop_top
            else:
                obj["top"] = (obj["top"] - crop_top) * zoom * display_scale

        for key in ("x1", "x2", "y1", "y2", "width", "height", "strokeWidth"):
            if key in obj:
                obj[key] *= factor

    return transformed


def make_zoomed_view(image, zoom, horizontal_pan, vertical_pan, display_scale=1.0):
    width, height = image.size
    crop_width = max(1, int(round(width / zoom)))
    crop_height = max(1, int(round(height / zoom)))
    crop_left = int(round((width - crop_width) * horizontal_pan / 100))
    crop_top = int(round((height - crop_height) * vertical_pan / 100))
    crop = image.crop(
        (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
    )
    display_size = (
        max(1, round(width * display_scale)),
        max(1, round(height * display_scale)),
    )
    return crop.resize(display_size, Image.Resampling.LANCZOS), crop_left, crop_top


def draw_dimension_line(draw, x1, y1, x2, y2, snap_mode=True):

    # Grön ton
    color = (0, 90, 0)

    # Streckad linje
    dash_length = 10
    gap_length = 6

    dx = x2 - x1
    dy = y2 - y1

    length = math.sqrt(dx**2 + dy**2)

    if length == 0:
        return

    ux = dx / length
    uy = dy / length

    pos = 0

    while pos < length:

        end = min(pos + dash_length, length)

        sx = x1 + ux * pos
        sy = y1 + uy * pos

        ex = x1 + ux * end
        ey = y1 + uy * end

        draw.line(
            [(sx, sy), (ex, ey)],
            fill=color,
            width=2
        )

        pos += dash_length + gap_length

    # Ändmarkörer: I------I

    marker_size = 8

    nx = -uy
    ny = ux

    draw.line(
        [
            (
                x1 - nx * marker_size,
                y1 - ny * marker_size
            ),
            (
                x1 + nx * marker_size,
                y1 + ny * marker_size
            )
        ],
        fill=color,
        width=3
    )

    draw.line(
        [
            (
                x2 - nx * marker_size,
                y2 - ny * marker_size
            ),
            (
                x2 + nx * marker_size,
                y2 + ny * marker_size
            )
        ],
        fill=color,
        width=3
    )


def render_measurements(base_image, lines, areas, scale, known_distance, snap, include_area_fill=False):
    rendered = base_image.convert("RGBA")

    if include_area_fill:
        overlay = Image.new("RGBA", rendered.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for _, area in areas:
            left, top, right, bottom = get_area_bounds(area)
            overlay_draw.rectangle(
                (left, top, right, bottom),
                fill=(0, 120, 0, 72),
                outline=(0, 90, 0, 220),
                width=2,
            )
        rendered = Image.alpha_composite(rendered, overlay)

    draw = ImageDraw.Draw(rendered)
    if scale is not None:
        for line_number, (_, line) in enumerate(lines):
            x1, y1, x2, y2 = get_line_coords(line)
            draw_dimension_line(draw, x1, y1, x2, y2, snap)

            if line_number == 0:
                text = f"R: {known_distance:.2f}m"
                background = "lightgreen"
            else:
                meters = math.hypot(x2 - x1, y2 - y1) * scale
                text = f"L{line_number}: {meters:.2f}m"
                background = "white"

            draw_centered_label(draw, text, ((x1 + x2) / 2, (y1 + y2) / 2), background)

    for area_number, (_, area) in enumerate(areas, start=1):
        left, top, right, bottom = get_area_bounds(area)
        if scale is not None:
            square_meters = (right - left) * (bottom - top) * scale**2
            text = f"A{area_number}: {square_meters:.2f} sqm"
        else:
            text = f"A{area_number}: Ange referens"
        draw_centered_label(
            draw,
            text,
            ((left + right) / 2, (top + bottom) / 2),
            "white",
        )

    return rendered


def draw_centered_label(draw, text, center, background):
    bbox = draw.textbbox((0, 0), text)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    center_x, center_y = center
    padding = 8
    draw.rectangle(
        (
            (center_x - width / 2 - padding, center_y - height / 2 - padding),
            (center_x + width / 2 + padding, center_y + height / 2 + padding),
        ),
        fill=background,
    )
    draw.text(
        (
            center_x - (bbox[0] + bbox[2]) / 2,
            center_y - (bbox[1] + bbox[3]) / 2,
        ),
        text,
        fill="black",
    )


st.title("Mätning av planritning")
st.caption("Kalibrera ritningen med en känd sträcka och mät längder eller areor.")

controls_column, plan_column = st.columns([1.05, 4], gap="large")

with controls_column:
    with st.container(border=True):
        st.subheader("Verktyg och inställningar")
        uploaded = st.file_uploader(
            "Ladda upp ritning",
            type=["png", "jpg", "jpeg"],
        )
        tool = st.radio(
            "Mätverktyg",
            options=["Linje", "Area"],
            horizontal=True,
        )
        snap_mode = st.checkbox(
            "Lås linjer horisontellt/vertikalt",
            value=True,
        )
        zoom = st.slider(
            "Zoom",
            min_value=1.0,
            max_value=4.0,
            value=1.0,
            step=0.25,
            help="Förstora ritningen för noggrannare mätning.",
        )
        horizontal_pan = st.slider(
            "Panorera horisontellt",
            min_value=0,
            max_value=100,
            value=50,
            disabled=zoom == 1.0,
        )
        vertical_pan = st.slider(
            "Panorera vertikalt",
            min_value=0,
            max_value=100,
            value=50,
            disabled=zoom == 1.0,
        )
        drawing_size = st.slider(
            "Ritningens storlek",
            min_value=75,
            max_value=200,
            value=150,
            step=5,
            format="%d%%",
            help="Ändrar visningsstorleken utan att påverka måtten.",
        )

if uploaded:
    img = Image.open(uploaded)
else:
    img = Image.open("layout_test.png")

objects = st.session_state.canvas_data.get("objects", [])
line_objects = [
    (index, obj)
    for index, obj in enumerate(objects)
    if get_object_type(obj) == "line"
]
area_objects = [
    (index, obj)
    for index, obj in enumerate(objects)
    if get_object_type(obj) == "rect"
]

if line_objects:
    with controls_column:
        with st.container(border=True):
            st.markdown("#### Kalibrering")
            st.number_input(
                "Känd referenslängd (meter)",
                min_value=0.01,
                value=st.session_state.get("known_distance", 1.0),
                step=0.1,
                key="known_distance",
                help="Ange den verkliga längden på referenslinjen R.",
            )
else:
    with controls_column:
        with st.container(border=True):
            st.markdown("#### Kalibrering")
            st.info("Rita den första linjen på ritningen. Den blir referens R.")

known_distance = st.session_state.get("known_distance", 1.0)

# Bygg den bild som ska visas i canvasen
scale = None

if line_objects:
    ref = line_objects[0][1]
    x1, y1, x2, y2 = get_line_coords(ref)
    ref_pixels = math.hypot(x2 - x1, y2 - y1)
    if ref_pixels > 0:
        scale = known_distance / ref_pixels

display_img = render_measurements(
    img,
    line_objects,
    area_objects,
    scale,
    known_distance,
    snap_mode,
)
display_img, crop_left, crop_top = make_zoomed_view(
    display_img,
    zoom,
    horizontal_pan,
    vertical_pan,
    drawing_size / 100,
)
view_canvas_data = transform_canvas_data(
    st.session_state.canvas_data,
    zoom,
    crop_left,
    crop_top,
    display_scale=drawing_size / 100,
)
view_canvas_key = (
    f"{st.session_state.canvas_key}_"
    f"{zoom}_{horizontal_pan}_{vertical_pan}_{drawing_size}"
)

with plan_column:
    st.subheader("Planritning")
    canvas_width = max(1, round(img.width * drawing_size / 100))
    canvas_height = max(1, round(img.height * drawing_size / 100))
    canvas_result = st_canvas(
        background_image=display_img,
        drawing_mode="line" if tool == "Linje" else "rect",
        initial_drawing=view_canvas_data,
        stroke_width=1,
        stroke_color="rgba(0,120,0,0.4)",
        fill_color="rgba(0,120,0,0.25)",
        update_streamlit=True,
        height=canvas_height,
        width=canvas_width,
        key=view_canvas_key
    )

if canvas_result.json_data is not None:
    if canvas_result.json_data != view_canvas_data:
        st.session_state.canvas_data = transform_canvas_data(
            canvas_result.json_data,
            zoom,
            crop_left,
            crop_top,
            display_scale=drawing_size / 100,
            inverse=True,
        )
        st.session_state.canvas_counter += 1
        st.session_state.canvas_key = f"canvas_{st.session_state.canvas_counter}"
        st.rerun()

    objects = st.session_state.canvas_data["objects"]

export_image = render_measurements(
    img,
    line_objects,
    area_objects,
    scale,
    known_distance,
    snap_mode,
    include_area_fill=True,
)
image_buffer = BytesIO()
export_image.save(image_buffer, format="PNG")
with controls_column:
    with st.container(border=True):
        st.markdown("#### Mätningar")
        st.caption(f"{len(line_objects)} linjer · {len(area_objects)} områden")
        if line_objects and scale is not None:
            st.success(f"Skala: {scale:.6f} m/pixel")

        if area_objects:
            if scale is not None:
                total_area = 0.0
                for _, area in area_objects:
                    left, top, right, bottom = get_area_bounds(area)
                    total_area += (right - left) * (bottom - top) * scale**2
                st.metric("Total area", f"{total_area:.2f} sqm")
            else:
                st.info("Ange en referenslinje för att beräkna total area.")

    line_number = 0
    area_number = 0
    if not objects:
        st.caption("Dina linjer och areor visas här när de har ritats.")
    else:
        for object_index, obj in enumerate(objects):
            if get_object_type(obj) == "line":
                x1, y1, x2, y2 = get_line_coords(obj)
                pixels = math.hypot(x2 - x1, y2 - y1)
                if line_number == 0:
                    label = f"R: {known_distance:.2f}m"
                else:
                    value = f"{pixels * scale:.2f}m" if scale is not None else "Ange referens"
                    label = f"L{line_number}: {value}"
                line_number += 1
            elif get_object_type(obj) == "rect":
                left, top, right, bottom = get_area_bounds(obj)
                square_meters = (
                    (right - left) * (bottom - top) * scale**2
                    if scale is not None
                    else None
                )
                value = f"{square_meters:.2f} sqm" if square_meters is not None else "Ange referens"
                label = f"A{area_number + 1}: {value}"
                area_number += 1
            else:
                continue

            col1, col2 = st.columns([5, 1], vertical_alignment="center")
            with col1:
                st.write(label)
            with col2:
                if st.button(
                    "🗑",
                    key=f"delete_object_{object_index}",
                    help=f"Ta bort {label}",
                ):
                    objects.pop(object_index)
                    st.session_state.canvas_data["objects"] = objects
                    st.session_state.canvas_counter += 1
                    st.session_state.canvas_key = f"canvas_{st.session_state.canvas_counter}"
                    st.rerun()

    st.download_button(
        "Ladda ner ritning med mätningar",
        data=image_buffer.getvalue(),
        file_name="ritning_med_mattningar.png",
        mime="image/png",
        width="stretch",
    )

    if st.button("Rensa alla mätningar", width="stretch"):
        st.session_state.canvas_data = {"objects": []}
        st.session_state.pop("known_distance", None)
        st.session_state.canvas_counter += 1
        st.session_state.canvas_key = f"canvas_{st.session_state.canvas_counter}"
        st.rerun()
