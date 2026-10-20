from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from sketch_to_page_json import parse_layer


DEFAULT_SKETCH_DIR = Path("fixtures/sketch/test_001/test")
DEFAULT_PAGE_ID = "748D2293-E71E-4046-BCB8-DAFFC5467DAC"
DEFAULT_JSON_OUTPUT = DEFAULT_SKETCH_DIR / "登录.canvas.json"
DEFAULT_HTML_OUTPUT = DEFAULT_SKETCH_DIR / "登录.canvas.html"

HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sketch 整体画布</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 720px; background: #11161e; color: #edf3fa; }
    header { height: 58px; display: flex; align-items: center; gap: 18px; padding: 0 18px; border-bottom: 1px solid #2b3746; background: #19212c; }
    h1 { margin: 0; font-size: 15px; font-weight: 650; }
    #meta { color: #9bacbf; font-size: 12px; }
    #tools { display: flex; align-items: center; gap: 8px; margin-left: auto; }
    button { width: 32px; height: 30px; border: 1px solid #3a485b; border-radius: 7px; background: #242f3c; color: #eef4fb; cursor: pointer; font-size: 18px; }
    button:hover { background: #34455a; }
    #scale { min-width: 60px; text-align: center; color: #b8c7d9; font-size: 12px; }
    #workspace { height: calc(100vh - 58px); overflow: hidden; position: relative; background-color: #151c25; background-image: linear-gradient(45deg, #1b2531 25%, transparent 25%), linear-gradient(-45deg, #1b2531 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #1b2531 75%), linear-gradient(-45deg, transparent 75%, #1b2531 75%); background-size: 24px 24px; background-position: 0 0, 0 12px, 12px -12px, -12px 0; }
    #canvas-shell { width: 100%; height: 100%; overflow: hidden; background: #29323e; }
    canvas { display: block; width: 100%; height: 100%; cursor: grab; touch-action: none; }
    canvas.dragging { cursor: grabbing; }
    #workspace { transition: margin-left .2s ease, margin-right .2s ease, width .2s ease; }
    #sidebar, #inspector { position: fixed; z-index: 4; top: 58px; bottom: 0; display: flex; flex-direction: column; background: #1a222d; transition: transform .2s ease; }
    #sidebar { left: 0; width: 320px; transform: translateX(-100%); border-right: 1px solid #344154; box-shadow: 8px 0 32px rgba(0, 0, 0, .26); }
    #inspector { right: 0; width: 390px; transform: translateX(100%); border-left: 1px solid #344154; box-shadow: -8px 0 32px rgba(0, 0, 0, .26); }
    body.sidebar-open #sidebar, body.inspector-open #inspector { transform: translateX(0); }
    body.sidebar-open #workspace { width: calc(100% - 320px); margin-left: 320px; }
    body.inspector-open #workspace { width: calc(100% - 390px); margin-right: 390px; }
    body.sidebar-open.inspector-open #workspace { width: calc(100% - 710px); margin-left: 320px; margin-right: 390px; }
    #sidebar-header, #inspector-header { display: flex; align-items: center; justify-content: space-between; height: 50px; padding: 0 14px; border-bottom: 1px solid #2e3a4a; color: #e7edf5; font-size: 13px; font-weight: 650; }
    #close-inspector { width: 28px; height: 28px; font-size: 18px; }
    #layer-tree { flex: 1; overflow: auto; padding: 8px 0 20px; color: #c5d0dd; font-size: 12px; }
    #layer-tree details { margin: 0; }
    #layer-tree summary, .tree-leaf { display: flex; align-items: center; gap: 7px; min-height: 27px; padding: 4px 10px; cursor: pointer; list-style: none; user-select: none; }
    #layer-tree summary::-webkit-details-marker { display: none; }
    #layer-tree summary::before { content: '›'; width: 10px; color: #8494a8; font-size: 16px; line-height: 10px; transform: rotate(0deg); transition: transform .12s ease; }
    #layer-tree details[open] > summary::before { transform: rotate(90deg); }
    .tree-leaf::before { content: '•'; width: 10px; color: #718398; text-align: center; }
    #layer-tree summary:hover, .tree-leaf:hover { background: #263344; }
    #layer-tree .tree-selected { background: #315273 !important; color: #ffffff; }
    .tree-type { min-width: 68px; color: #7c9bc1; font-size: 10px; text-transform: uppercase; }
    .tree-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #inspector-content { flex: 1; overflow: auto; padding: 14px; }
    #selection-summary { display: grid; grid-template-columns: 92px 1fr; gap: 7px 10px; margin-bottom: 14px; color: #bac7d7; font-size: 12px; }
    #selection-summary dt { color: #7890ac; }
    #selection-summary dd { margin: 0; overflow-wrap: anywhere; }
    #selection-data { margin: 0; padding: 12px; overflow: auto; border: 1px solid #2c3949; border-radius: 8px; background: #121820; color: #c9d6e5; font: 11px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }
    #hover-tooltip { position: fixed; z-index: 8; display: none; max-width: 280px; padding: 8px 10px; border: 1px solid #4a637f; border-radius: 7px; background: rgba(18, 27, 38, .94); box-shadow: 0 8px 24px rgba(0, 0, 0, .28); color: #edf5ff; font-size: 12px; line-height: 1.45; pointer-events: none; }
    #hover-tooltip.visible { display: block; }
    #hover-tooltip .tooltip-type { color: #7fb9f7; font-size: 10px; text-transform: uppercase; }
    #toggle-sidebar { font-size: 16px; }
  </style>
</head>
<body>
  <header>
    <button id="toggle-sidebar" title="显示或隐藏图层目录" aria-label="显示或隐藏图层目录">☰</button>
    <h1 id="title"></h1>
    <span id="meta"></span>
    <div id="tools"><button id="zoom-out">−</button><span id="scale"></span><button id="zoom-in">+</button><button id="fit" title="适应窗口">⊡</button></div>
  </header>
  <aside id="sidebar">
    <div id="sidebar-header"><span>图层目录</span><span id="page-count"></span></div>
    <div id="layer-tree"></div>
  </aside>
  <aside id="inspector">
    <div id="inspector-header"><span id="inspector-title">图层数据</span><button id="close-inspector" title="关闭数据面板">×</button></div>
    <div id="inspector-content"><dl id="selection-summary"></dl><pre id="selection-data"></pre></div>
  </aside>
  <div id="hover-tooltip"></div>
  <main id="workspace"><div id="canvas-shell"><canvas id="canvas"></canvas></div></main>
  <script id="canvas-data" type="application/json">__CANVAS_DATA__</script>
  <script>
    const model = JSON.parse(document.getElementById("canvas-data").textContent);
    const pages = model.designPages;
    const bounds = model.bounds;
    const workspace = document.getElementById("workspace");
    const canvas = document.getElementById("canvas");
    const context = canvas.getContext("2d");
    const imageCache = new Map();
    let scale = 1;
    let panX = 0;
    let panY = 0;
    let dragState = null;
    let selectedNode = null;
    let hoveredNode = null;
    const treeRows = new Map();
    document.getElementById("title").textContent = `${model.sketchPage.name} · 整体画布`;
    document.getElementById("meta").textContent = `${pages.length} 个设计页面 · ${model.statistics.totalLayers} 图层 · ${bounds.width} × ${bounds.height}`;
    document.getElementById("page-count").textContent = `${pages.length} 个页面`;

    function rgba(color) { return color ? `rgba(${Math.round(color.red * 255)}, ${Math.round(color.green * 255)}, ${Math.round(color.blue * 255)}, ${color.alpha ?? 1})` : null; }
    function point(value) { const match = /^\{\s*([^,]+),\s*([^}]+)\}$/.exec(value || ""); return match ? [Number(match[1]), Number(match[2])] : [0, 0]; }
    function enabled(items) { return (items || []).filter(item => item.enabled); }
    function roundedRect(width, height, radii) { const radius = Math.max(0, Math.min(width / 2, height / 2, Number((radii || [])[0] || 0))); context.beginPath(); context.moveTo(radius, 0); context.lineTo(width - radius, 0); context.quadraticCurveTo(width, 0, width, radius); context.lineTo(width, height - radius); context.quadraticCurveTo(width, height, width - radius, height); context.lineTo(radius, height); context.quadraticCurveTo(0, height, 0, height - radius); context.lineTo(0, radius); context.quadraticCurveTo(0, 0, radius, 0); context.closePath(); }
    function applyShadow(style) { const shadow = enabled(style.shadows)[0]; if (!shadow || !shadow.color) return; context.shadowColor = rgba(shadow.color); context.shadowBlur = shadow.blurRadius || 0; context.shadowOffsetX = shadow.offsetX || 0; context.shadowOffsetY = shadow.offsetY || 0; }
    function clearShadow() { context.shadowColor = "transparent"; context.shadowBlur = 0; context.shadowOffsetX = 0; context.shadowOffsetY = 0; }
    function paintPath(style) { const fill = enabled(style.fills)[0]; if (fill && fill.color) { context.fillStyle = rgba(fill.color); context.save(); context.globalAlpha *= fill.opacity ?? 1; context.fill(); context.restore(); } const border = enabled(style.borders)[0]; if (border && border.color && border.thickness) { context.strokeStyle = rgba(border.color); context.lineWidth = border.thickness; context.save(); context.globalAlpha *= border.opacity ?? 1; context.stroke(); context.restore(); } }
    function drawBox(node) { const style = node.style || {}; if (!enabled(style.fills).length && !enabled(style.borders).length) return; applyShadow(style); roundedRect(node.frame.width, node.frame.height, style.cornerRadii); paintPath(style); clearShadow(); }
    function drawPath(node) { if (!(node.points || []).length) return; context.beginPath(); node.points.forEach((item, index) => { const [x, y] = point(item.point); const pointX = x * node.frame.width; const pointY = y * node.frame.height; if (index) context.lineTo(pointX, pointY); else context.moveTo(pointX, pointY); }); context.closePath(); applyShadow(node.style || {}); paintPath(node.style || {}); clearShadow(); }
    function drawText(node) { const text = node.text || {}; const run = (text.runs || [])[0] || {}; const font = run.font || {}; const size = font.size || Math.max(12, node.frame.height); context.font = `${size}px "${font.name || "sans-serif"}", "PingFang SC", "Microsoft YaHei", sans-serif`; context.fillStyle = rgba(run.color) || "#111827"; context.textBaseline = "top"; context.textAlign = run.alignment === 1 ? "center" : run.alignment === 2 ? "right" : "left"; const textX = run.alignment === 1 ? node.frame.width / 2 : run.alignment === 2 ? node.frame.width : 0; String(text.content || "").split("\n").forEach((line, index) => context.fillText(line, textX, index * size * 1.25)); }
    function getImage(reference) { if (!reference) return null; if (!imageCache.has(reference)) { const image = new Image(); image.onload = render; image.onerror = render; image.src = reference; imageCache.set(reference, image); } return imageCache.get(reference); }
    function drawImage(node) { const image = getImage(node.image && node.image.reference); if (image && image.complete && image.naturalWidth) context.drawImage(image, 0, 0, node.frame.width, node.frame.height); else { context.fillStyle = "#d7dee8"; context.fillRect(0, 0, node.frame.width, node.frame.height); } }
    function drawNode(node) { if (!node.visible) return; const width = node.frame.width; const height = node.frame.height; context.save(); context.globalAlpha = node.style?.opacity ?? 1; context.translate(node.frame.absoluteX + width / 2, node.frame.absoluteY + height / 2); context.rotate((node.rotation || 0) * Math.PI / 180); context.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1); context.translate(-width / 2, -height / 2); if (["design_page", "group", "rectangle"].includes(node.type)) drawBox(node); if (node.type === "shape_path") drawPath(node); if (node.type === "text") drawText(node); if (node.type === "image") drawImage(node); context.restore(); (node.children || []).forEach(drawNode); }
    function drawOutline(node, strokeStyle, fillStyle) { if (!node) return; const frame = node.frame; context.save(); context.globalAlpha = 1; context.setLineDash([6 / scale, 4 / scale]); context.lineWidth = 2 / scale; context.strokeStyle = strokeStyle; context.fillStyle = fillStyle; context.fillRect(frame.absoluteX, frame.absoluteY, frame.width, frame.height); context.strokeRect(frame.absoluteX, frame.absoluteY, frame.width, frame.height); context.restore(); }
    function drawSelection() { drawOutline(selectedNode, "#47a4ff", "rgba(71, 164, 255, .16)"); }
    function drawHover() { if (hoveredNode && hoveredNode !== selectedNode) drawOutline(hoveredNode, "#f2c94c", "rgba(242, 201, 76, .11)"); }
    function canvasCenter() { return { x: workspace.clientWidth / 2, y: workspace.clientHeight / 2 }; }
    function worldCenter() { return { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 }; }
    function render() { const ratio = window.devicePixelRatio || 1; const width = Math.max(1, workspace.clientWidth); const height = Math.max(1, workspace.clientHeight); const center = canvasCenter(); const world = worldCenter(); canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); canvas.style.width = `${width}px`; canvas.style.height = `${height}px`; context.setTransform(1, 0, 0, 1, 0, 0); context.clearRect(0, 0, canvas.width, canvas.height); context.setTransform(ratio * scale, 0, 0, ratio * scale, (center.x + panX - world.x * scale) * ratio, (center.y + panY - world.y * scale) * ratio); pages.forEach(drawNode); drawHover(); drawSelection(); document.getElementById("scale").textContent = `${Math.round(scale * 100)}%`; }
    function setScale(value) { scale = Math.max(.05, Math.min(3, value)); render(); }
    function zoomAt(clientX, clientY, nextScale) { const rect = canvas.getBoundingClientRect(); const pointerX = clientX - rect.left; const pointerY = clientY - rect.top; const center = canvasCenter(); const world = worldCenter(); const worldX = world.x + (pointerX - center.x - panX) / scale; const worldY = world.y + (pointerY - center.y - panY) / scale; scale = Math.max(.05, Math.min(3, nextScale)); panX = pointerX - center.x - (worldX - world.x) * scale; panY = pointerY - center.y - (worldY - world.y) * scale; render(); }
    function fit() { scale = Math.min(Math.max(320, workspace.clientWidth - 96) / bounds.width, Math.max(320, workspace.clientHeight - 96) / bounds.height, 1); panX = 0; panY = 0; render(); }
    function focusNode(node) { const targetX = node.frame.absoluteX + node.frame.width / 2; const targetY = node.frame.absoluteY + node.frame.height / 2; const world = worldCenter(); panX = (world.x - targetX) * scale; panY = (world.y - targetY) * scale; render(); }
    function inspectorValue(value) { return value === undefined || value === null || value === "" ? "—" : String(value); }
    function inspectorNodeData(node) { const { children = [], ...properties } = node; return properties; }
    function updateInspector(node) { const title = document.getElementById("inspector-title"); const summary = document.getElementById("selection-summary"); const data = document.getElementById("selection-data"); const rows = [["名称", node.name], ["类型", node.type], ["Sketch 类型", node.sketchClass], ["对象 ID", node.id], ["局部坐标", `${node.frame.x}, ${node.frame.y}`], ["画布坐标", `${node.frame.absoluteX}, ${node.frame.absoluteY}`], ["尺寸", `${node.frame.width} × ${node.frame.height}`], ["子图层数", (node.children || []).length]]; title.textContent = node.name || "图层数据"; summary.replaceChildren(); rows.forEach(([label, value]) => { const key = document.createElement("dt"); key.textContent = label; const item = document.createElement("dd"); item.textContent = inspectorValue(value); summary.append(key, item); }); data.textContent = JSON.stringify(inspectorNodeData(node), null, 2); }
    function updateTreeSelection() { treeRows.forEach(row => row.classList.toggle("tree-selected", row.dataset.nodeId === selectedNode?.id)); }
    function selectNode(node) { selectedNode = node; updateInspector(node); updateTreeSelection(); document.body.classList.add("inspector-open"); focusNode(node); window.setTimeout(render, 220); }
    function nodeLabel(node) { return node.name || node.id || "未命名图层"; }
    function addTreeNode(parent, node, depth, open) { const children = node.children || []; const item = document.createElement(children.length ? "details" : "div"); if (children.length) item.open = open; const row = document.createElement(children.length ? "summary" : "div"); if (!children.length) row.className = "tree-leaf"; row.dataset.nodeId = node.id; treeRows.set(node.id, row); row.style.paddingLeft = `${10 + depth * 14}px`; const type = document.createElement("span"); type.className = "tree-type"; type.textContent = node.type; const name = document.createElement("span"); name.className = "tree-name"; name.textContent = nodeLabel(node); row.append(type, name); row.addEventListener("click", () => window.setTimeout(() => selectNode(node), 0)); item.append(row); if (children.length) children.forEach(child => addTreeNode(item, child, depth + 1, false)); parent.append(item); }
    function renderLayerTree() { const tree = document.getElementById("layer-tree"); treeRows.clear(); tree.replaceChildren(); pages.forEach(page => addTreeNode(tree, page, 0, true)); updateTreeSelection(); }
    canvas.addEventListener("wheel", event => { event.preventDefault(); zoomAt(event.clientX, event.clientY, scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12)); }, { passive: false });
    canvas.addEventListener("pointerdown", event => { dragState = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX, panY }; canvas.setPointerCapture(event.pointerId); canvas.classList.add("dragging"); });
    function flattenNodes(node, nodes) { nodes.push(node); (node.children || []).forEach(child => flattenNodes(child, nodes)); }
    function hitTest(clientX, clientY) { const rect = canvas.getBoundingClientRect(); const center = canvasCenter(); const world = worldCenter(); const worldX = world.x + (clientX - rect.left - center.x - panX) / scale; const worldY = world.y + (clientY - rect.top - center.y - panY) / scale; const nodes = []; pages.forEach(page => flattenNodes(page, nodes)); return nodes.reverse().find(node => node.visible && worldX >= node.frame.absoluteX && worldX <= node.frame.absoluteX + node.frame.width && worldY >= node.frame.absoluteY && worldY <= node.frame.absoluteY + node.frame.height) || null; }
    function showHoverTooltip(node, clientX, clientY) { const tooltip = document.getElementById("hover-tooltip"); if (!node) { tooltip.classList.remove("visible"); return; } const type = document.createElement("div"); type.className = "tooltip-type"; type.textContent = node.type; const name = document.createElement("strong"); name.textContent = nodeLabel(node); const details = document.createElement("div"); details.textContent = `${Math.round(node.frame.width)} × ${Math.round(node.frame.height)} · x: ${Math.round(node.frame.absoluteX)}, y: ${Math.round(node.frame.absoluteY)}`; tooltip.replaceChildren(type, name, details); tooltip.style.left = `${clientX + 14}px`; tooltip.style.top = `${clientY + 14}px`; tooltip.classList.add("visible"); }
    function updateHover(clientX, clientY) { const nextNode = hitTest(clientX, clientY); if (hoveredNode !== nextNode) { hoveredNode = nextNode; render(); } showHoverTooltip(nextNode, clientX, clientY); }
    canvas.addEventListener("pointermove", event => { if (dragState && event.pointerId === dragState.pointerId) { panX = dragState.panX + event.clientX - dragState.x; panY = dragState.panY + event.clientY - dragState.y; render(); return; } updateHover(event.clientX, event.clientY); });
    canvas.addEventListener("pointerleave", () => { if (!hoveredNode) return; hoveredNode = null; document.getElementById("hover-tooltip").classList.remove("visible"); render(); });
    function stopDragging(event) { if (!dragState || event.pointerId !== dragState.pointerId) return; dragState = null; canvas.classList.remove("dragging"); }
    canvas.addEventListener("pointerup", stopDragging);
    canvas.addEventListener("pointercancel", stopDragging);
    canvas.addEventListener("dblclick", fit);
    document.getElementById("zoom-in").addEventListener("click", () => { const center = canvas.getBoundingClientRect(); zoomAt(center.left + center.width / 2, center.top + center.height / 2, scale * 1.15); });
    document.getElementById("zoom-out").addEventListener("click", () => { const center = canvas.getBoundingClientRect(); zoomAt(center.left + center.width / 2, center.top + center.height / 2, scale / 1.15); });
    document.getElementById("fit").addEventListener("click", fit);
    document.getElementById("toggle-sidebar").addEventListener("click", () => { const open = document.body.classList.toggle("sidebar-open"); document.getElementById("toggle-sidebar").setAttribute("aria-expanded", String(open)); window.setTimeout(render, 220); });
    document.getElementById("close-inspector").addEventListener("click", () => { document.body.classList.remove("inspector-open"); window.setTimeout(render, 220); });
    window.addEventListener("resize", render);
    renderLayerTree();
    fit();
  </script>
</body>
</html>'''


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source_file:
        return json.load(source_file)


def find_object_by_id(value: Any, object_id: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("do_objectID") == object_id:
            return value
        for child in value.values():
            found = find_object_by_id(child, object_id)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_object_by_id(child, object_id)
            if found is not None:
                return found
    return None


def translate_absolute_positions(layer: dict[str, Any], offset_x: float, offset_y: float) -> None:
    layer["frame"]["absoluteX"] += offset_x
    layer["frame"]["absoluteY"] += offset_y
    for child in layer.get("children", []):
        translate_absolute_positions(child, offset_x, offset_y)


def count_layers(layer: dict[str, Any], counts: Counter[str]) -> None:
    counts[layer["type"]] += 1
    for child in layer.get("children", []):
        count_layers(child, counts)


def build_page_canvas(sketch_dir: Path, page_id: str) -> dict[str, Any]:
    sketch_dir = Path(sketch_dir)
    meta = load_json(sketch_dir / "meta.json")
    document = load_json(sketch_dir / "document.json")
    page_meta = meta.get("pagesAndArtboards", {}).get(page_id)
    if page_meta is None:
        raise ValueError(f"Page {page_id} was not found in meta.json.")

    page_reference = next(
        (item for item in document.get("pages", []) if item.get("_ref") == f"pages/{page_id}"),
        None,
    )
    if page_reference is None:
        raise ValueError(f"Page {page_id} was not referenced by document.json.")

    page_path = sketch_dir / f"{page_reference['_ref']}.json"
    page_data = load_json(page_path)
    design_pages = []
    for artboard_id, artboard_meta in page_meta.get("artboards", {}).items():
        raw_layer = find_object_by_id(page_data.get("layers", []), artboard_id)
        if raw_layer is None:
            raise ValueError(f"Artboard {artboard_id} was indexed but not found in {page_path}.")
        parsed_layer = parse_layer(raw_layer, sketch_dir, is_design_page=True)
        source_frame = raw_layer.get("frame", {})
        translate_absolute_positions(parsed_layer, source_frame.get("x", 0), source_frame.get("y", 0))
        parsed_layer["metaName"] = artboard_meta.get("name")
        design_pages.append(parsed_layer)

    minimum_x = min(page["frame"]["absoluteX"] for page in design_pages)
    minimum_y = min(page["frame"]["absoluteY"] for page in design_pages)
    maximum_x = max(page["frame"]["absoluteX"] + page["frame"]["width"] for page in design_pages)
    maximum_y = max(page["frame"]["absoluteY"] + page["frame"]["height"] for page in design_pages)
    counts: Counter[str] = Counter()
    for design_page in design_pages:
        count_layers(design_page, counts)

    return {
        "source": {
            "sketchDirectory": str(sketch_dir),
            "pageFile": str(page_path),
            "metaFile": str(sketch_dir / "meta.json"),
        },
        "sketchPage": {"id": page_id, "name": page_meta.get("name")},
        "bounds": {
            "minX": minimum_x,
            "minY": minimum_y,
            "maxX": maximum_x,
            "maxY": maximum_y,
            "width": maximum_x - minimum_x,
            "height": maximum_y - minimum_y,
        },
        "designPages": design_pages,
        "statistics": {"totalLayers": sum(counts.values()), "byType": dict(sorted(counts.items()))},
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(value, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def write_preview(path: Path, canvas_data: dict[str, Any]) -> None:
    embedded_data = json.dumps(canvas_data, ensure_ascii=False).replace("</", "<\\/")
    with path.open("w", encoding="utf-8") as output_file:
        output_file.write(HTML_TEMPLATE.replace("__CANVAS_DATA__", embedded_data))


def main() -> None:
    canvas_data = build_page_canvas(DEFAULT_SKETCH_DIR, DEFAULT_PAGE_ID)
    write_json(DEFAULT_JSON_OUTPUT, canvas_data)
    write_preview(DEFAULT_HTML_OUTPUT, canvas_data)
    print(f"Canvas data: {DEFAULT_JSON_OUTPUT}")
    print(f"Canvas preview: {DEFAULT_HTML_OUTPUT}")


if __name__ == "__main__":
    main()
