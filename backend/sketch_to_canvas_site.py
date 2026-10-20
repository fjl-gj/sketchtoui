from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from sketch_to_page_json import parse_layer


SKETCH_DIR = Path("fixtures/sketch/test_001/test")
OUTPUT_DIR = SKETCH_DIR / "canvas"
INVALID_DIRECTORY_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


STYLE_CSS = r''':root { color-scheme: dark; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 800px; background: #11161e; color: #edf3fa; }
header { position: relative; z-index: 5; height: 58px; display: flex; align-items: center; gap: 16px; padding: 0 18px; border-bottom: 1px solid #2b3746; background: #19212c; }
h1 { margin: 0; font-size: 15px; font-weight: 650; }
#meta { color: #9bacbf; font-size: 12px; }
#tools { display: flex; align-items: center; gap: 8px; margin-left: auto; }
button { width: 32px; height: 30px; border: 1px solid #3a485b; border-radius: 7px; background: #242f3c; color: #eef4fb; cursor: pointer; font-size: 18px; }
button:hover { background: #34455a; }
#scale { min-width: 60px; text-align: center; color: #b8c7d9; font-size: 12px; }
#workspace { height: calc(100vh - 58px); overflow: hidden; position: relative; transition: margin-left .2s ease, margin-right .2s ease, width .2s ease; background-color: #151c25; background-image: linear-gradient(45deg, #1b2531 25%, transparent 25%), linear-gradient(-45deg, #1b2531 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #1b2531 75%), linear-gradient(-45deg, transparent 75%, #1b2531 75%); background-size: 24px 24px; background-position: 0 0, 0 12px, 12px -12px, -12px 0; }
#canvas-shell { width: 100%; height: 100%; overflow: hidden; background: #29323e; }
canvas { display: block; width: 100%; height: 100%; cursor: grab; touch-action: none; }
canvas.dragging { cursor: grabbing; }
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
#empty-state { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); padding: 18px 22px; border: 1px solid #354458; border-radius: 10px; background: rgba(24, 33, 44, .94); color: #c7d3e1; font-size: 13px; }
'''

VIEWPORT_JS = r'''window.CanvasViewport = class CanvasViewport {
  constructor(workspace, canvas, bounds) {
    this.workspace = workspace;
    this.canvas = canvas;
    this.bounds = bounds;
    this.scale = 1;
    this.panX = 0;
    this.panY = 0;
  }
  canvasCenter() { return { x: this.workspace.clientWidth / 2, y: this.workspace.clientHeight / 2 }; }
  worldCenter() { return { x: (this.bounds.minX + this.bounds.maxX) / 2, y: (this.bounds.minY + this.bounds.maxY) / 2 }; }
  transform(context) {
    const ratio = window.devicePixelRatio || 1;
    const center = this.canvasCenter();
    const world = this.worldCenter();
    context.setTransform(ratio * this.scale, 0, 0, ratio * this.scale, (center.x + this.panX - world.x * this.scale) * ratio, (center.y + this.panY - world.y * this.scale) * ratio);
  }
  resize(context) {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, this.workspace.clientWidth);
    const height = Math.max(1, this.workspace.clientHeight);
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }
  fit() {
    this.scale = Math.min(Math.max(320, this.workspace.clientWidth - 96) / this.bounds.width, Math.max(320, this.workspace.clientHeight - 96) / this.bounds.height, 1);
    this.panX = 0;
    this.panY = 0;
  }
  zoomAt(clientX, clientY, nextScale) {
    const rect = this.canvas.getBoundingClientRect();
    const pointerX = clientX - rect.left;
    const pointerY = clientY - rect.top;
    const center = this.canvasCenter();
    const world = this.worldCenter();
    const worldX = world.x + (pointerX - center.x - this.panX) / this.scale;
    const worldY = world.y + (pointerY - center.y - this.panY) / this.scale;
    this.scale = Math.max(.05, Math.min(3, nextScale));
    this.panX = pointerX - center.x - (worldX - world.x) * this.scale;
    this.panY = pointerY - center.y - (worldY - world.y) * this.scale;
  }
  focus(node) {
    const targetX = node.frame.absoluteX + node.frame.width / 2;
    const targetY = node.frame.absoluteY + node.frame.height / 2;
    const world = this.worldCenter();
    this.panX = (world.x - targetX) * this.scale;
    this.panY = (world.y - targetY) * this.scale;
  }
  worldAt(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const center = this.canvasCenter();
    const world = this.worldCenter();
    return {
      x: world.x + (clientX - rect.left - center.x - this.panX) / this.scale,
      y: world.y + (clientY - rect.top - center.y - this.panY) / this.scale,
    };
  }
};
'''

RENDERER_JS = r'''window.CanvasRenderer = class CanvasRenderer {
  constructor(canvas, assetBase) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.assetBase = assetBase;
    this.imageCache = new Map();
  }
  rgba(color) { return color ? `rgba(${Math.round(color.red * 255)}, ${Math.round(color.green * 255)}, ${Math.round(color.blue * 255)}, ${color.alpha ?? 1})` : null; }
  enabled(items) { return (items || []).filter(item => item.enabled); }
  point(value) { const match = /^\{\s*([^,]+),\s*([^}]+)\}$/.exec(value || ""); return match ? [Number(match[1]), Number(match[2])] : [0, 0]; }
  roundedRect(width, height, radii) { const context = this.context; const radius = Math.max(0, Math.min(width / 2, height / 2, Number((radii || [])[0] || 0))); context.beginPath(); context.moveTo(radius, 0); context.lineTo(width - radius, 0); context.quadraticCurveTo(width, 0, width, radius); context.lineTo(width, height - radius); context.quadraticCurveTo(width, height, width - radius, height); context.lineTo(radius, height); context.quadraticCurveTo(0, height, 0, height - radius); context.lineTo(0, radius); context.quadraticCurveTo(0, 0, radius, 0); context.closePath(); }
  applyShadow(style) { const shadow = this.enabled(style.shadows)[0]; if (!shadow || !shadow.color) return; const context = this.context; context.shadowColor = this.rgba(shadow.color); context.shadowBlur = shadow.blurRadius || 0; context.shadowOffsetX = shadow.offsetX || 0; context.shadowOffsetY = shadow.offsetY || 0; }
  clearShadow() { const context = this.context; context.shadowColor = "transparent"; context.shadowBlur = 0; context.shadowOffsetX = 0; context.shadowOffsetY = 0; }
  paintPath(style) { const context = this.context; const fill = this.enabled(style.fills)[0]; if (fill && fill.color) { context.fillStyle = this.rgba(fill.color); context.save(); context.globalAlpha *= fill.opacity ?? 1; context.fill(); context.restore(); } const border = this.enabled(style.borders)[0]; if (border && border.color && border.thickness) { context.strokeStyle = this.rgba(border.color); context.lineWidth = border.thickness; context.save(); context.globalAlpha *= border.opacity ?? 1; context.stroke(); context.restore(); } }
  drawBox(node) { const style = node.style || {}; if (!this.enabled(style.fills).length && !this.enabled(style.borders).length) return; this.applyShadow(style); this.roundedRect(node.frame.width, node.frame.height, style.cornerRadii); this.paintPath(style); this.clearShadow(); }
  drawPath(node) { if (!(node.points || []).length) return; const context = this.context; context.beginPath(); node.points.forEach((item, index) => { const [x, y] = this.point(item.point); const pointX = x * node.frame.width; const pointY = y * node.frame.height; if (index) context.lineTo(pointX, pointY); else context.moveTo(pointX, pointY); }); context.closePath(); this.applyShadow(node.style || {}); this.paintPath(node.style || {}); this.clearShadow(); }
  drawText(node) { const context = this.context; const text = node.text || {}; const run = (text.runs || [])[0] || {}; const font = run.font || {}; const size = font.size || Math.max(12, node.frame.height); context.font = `${size}px "${font.name || "sans-serif"}", "PingFang SC", "Microsoft YaHei", sans-serif`; context.fillStyle = this.rgba(run.color) || "#111827"; context.textBaseline = "top"; context.textAlign = run.alignment === 1 ? "center" : run.alignment === 2 ? "right" : "left"; const textX = run.alignment === 1 ? node.frame.width / 2 : run.alignment === 2 ? node.frame.width : 0; String(text.content || "").split("\n").forEach((line, index) => context.fillText(line, textX, index * size * 1.25)); }
  imageFor(reference, redraw) { if (!reference) return null; if (!this.imageCache.has(reference)) { const image = new Image(); image.onload = redraw; image.onerror = redraw; image.src = `${this.assetBase}${reference}`; this.imageCache.set(reference, image); } return this.imageCache.get(reference); }
  drawImage(node, redraw) { const context = this.context; const image = this.imageFor(node.image && node.image.reference, redraw); if (image && image.complete && image.naturalWidth) context.drawImage(image, 0, 0, node.frame.width, node.frame.height); else { context.fillStyle = "#d7dee8"; context.fillRect(0, 0, node.frame.width, node.frame.height); } }
  drawNode(node, redraw) { if (!node.visible) return; const context = this.context; const width = node.frame.width; const height = node.frame.height; context.save(); context.globalAlpha = node.style?.opacity ?? 1; context.translate(node.frame.absoluteX + width / 2, node.frame.absoluteY + height / 2); context.rotate((node.rotation || 0) * Math.PI / 180); context.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1); context.translate(-width / 2, -height / 2); if (["design_page", "group", "rectangle"].includes(node.type)) this.drawBox(node); if (node.type === "shape_path") this.drawPath(node); if (node.type === "text") this.drawText(node); if (node.type === "image") this.drawImage(node, redraw); context.restore(); (node.children || []).forEach(child => this.drawNode(child, redraw)); }
  drawOutline(node, viewport, strokeStyle, fillStyle) { if (!node) return; const context = this.context; const frame = node.frame; context.save(); context.globalAlpha = 1; context.setLineDash([6 / viewport.scale, 4 / viewport.scale]); context.lineWidth = 2 / viewport.scale; context.strokeStyle = strokeStyle; context.fillStyle = fillStyle; context.fillRect(frame.absoluteX, frame.absoluteY, frame.width, frame.height); context.strokeRect(frame.absoluteX, frame.absoluteY, frame.width, frame.height); context.restore(); }
  render(pages, viewport, selected, hovered, redraw) { this.context.save(); viewport.resize(this.context); viewport.transform(this.context); pages.forEach(page => this.drawNode(page, redraw)); if (hovered && hovered !== selected) this.drawOutline(hovered, viewport, "#f2c94c", "rgba(242, 201, 76, .11)"); this.drawOutline(selected, viewport, "#47a4ff", "rgba(71, 164, 255, .16)"); this.context.restore(); }
};
'''

HIT_TEST_JS = r'''window.CanvasHitTest = {
  flatten(node, nodes) { nodes.push(node); (node.children || []).forEach(child => this.flatten(child, nodes)); },
  nodes(pages) { const nodes = []; pages.forEach(page => this.flatten(page, nodes)); return nodes; },
  find(pages, viewport, clientX, clientY) { const world = viewport.worldAt(clientX, clientY); return this.nodes(pages).reverse().find(node => node.visible && world.x >= node.frame.absoluteX && world.x <= node.frame.absoluteX + node.frame.width && world.y >= node.frame.absoluteY && world.y <= node.frame.absoluteY + node.frame.height) || null; },
};
'''

TREE_JS = r'''window.CanvasLayerTree = class CanvasLayerTree {
  constructor(container, onSelect) { this.container = container; this.onSelect = onSelect; this.rows = new Map(); }
  label(node) { return node.name || node.id || "未命名图层"; }
  addNode(parent, node, depth, open) { const children = node.children || []; const item = document.createElement(children.length ? "details" : "div"); if (children.length) item.open = open; const row = document.createElement(children.length ? "summary" : "div"); if (!children.length) row.className = "tree-leaf"; row.dataset.nodeId = node.id; this.rows.set(node.id, row); row.style.paddingLeft = `${10 + depth * 14}px`; const type = document.createElement("span"); type.className = "tree-type"; type.textContent = node.type; const name = document.createElement("span"); name.className = "tree-name"; name.textContent = this.label(node); row.append(type, name); row.addEventListener("click", () => window.setTimeout(() => this.onSelect(node), 0)); item.append(row); if (children.length) children.forEach(child => this.addNode(item, child, depth + 1, false)); parent.append(item); }
  render(pages) { this.rows.clear(); this.container.replaceChildren(); pages.forEach(page => this.addNode(this.container, page, 0, true)); }
  select(node) { this.rows.forEach(row => row.classList.toggle("tree-selected", row.dataset.nodeId === node?.id)); }
};
'''

INSPECTOR_JS = r'''window.CanvasInspector = class CanvasInspector {
  constructor(title, summary, data) { this.title = title; this.summary = summary; this.data = data; }
  value(value) { return value === undefined || value === null || value === "" ? "—" : String(value); }
  ownData(node) { const { children, ...properties } = node; return properties; }
  show(node) { const rows = [["名称", node.name], ["类型", node.type], ["Sketch 类型", node.sketchClass], ["对象 ID", node.id], ["局部坐标", `${node.frame.x}, ${node.frame.y}`], ["画布坐标", `${node.frame.absoluteX}, ${node.frame.absoluteY}`], ["尺寸", `${node.frame.width} × ${node.frame.height}`], ["子图层数", (node.children || []).length]]; this.title.textContent = node.name || "图层数据"; this.summary.replaceChildren(); rows.forEach(([label, value]) => { const key = document.createElement("dt"); key.textContent = label; const item = document.createElement("dd"); item.textContent = this.value(value); this.summary.append(key, item); }); this.data.textContent = JSON.stringify(this.ownData(node), null, 2); }
};
'''

APP_JS = r'''window.CanvasApp = {
  start(data, config) {
    const pages = data.designPages || [];
    const workspace = document.getElementById("workspace");
    const canvas = document.getElementById("canvas");
    const emptyState = document.getElementById("empty-state");
    document.getElementById("title").textContent = `${data.sketchPage.name} · 整体画布`;
    document.getElementById("meta").textContent = `${pages.length} 个设计页面 · ${data.statistics.totalLayers} 图层 · ${data.bounds.width} × ${data.bounds.height}`;
    document.getElementById("page-count").textContent = `${pages.length} 个页面`;
    if (!pages.length) { emptyState.hidden = false; return; }
    const viewport = new window.CanvasViewport(workspace, canvas, data.bounds);
    const renderer = new window.CanvasRenderer(canvas, config.assetBase);
    const inspector = new window.CanvasInspector(document.getElementById("inspector-title"), document.getElementById("selection-summary"), document.getElementById("selection-data"));
    const tooltip = document.getElementById("hover-tooltip");
    let selectedNode = null;
    let hoveredNode = null;
    let dragState = null;
    let tree;
    const label = node => node.name || node.id || "未命名图层";
    const redraw = () => { renderer.render(pages, viewport, selectedNode, hoveredNode, redraw); document.getElementById("scale").textContent = `${Math.round(viewport.scale * 100)}%`; };
    const selectNode = node => { selectedNode = node; inspector.show(node); tree.select(node); document.body.classList.add("inspector-open"); viewport.focus(node); redraw(); window.setTimeout(redraw, 220); };
    tree = new window.CanvasLayerTree(document.getElementById("layer-tree"), selectNode);
    const showTooltip = (node, clientX, clientY) => { if (!node) { tooltip.classList.remove("visible"); return; } const type = document.createElement("div"); type.className = "tooltip-type"; type.textContent = node.type; const name = document.createElement("strong"); name.textContent = label(node); const details = document.createElement("div"); details.textContent = `${Math.round(node.frame.width)} × ${Math.round(node.frame.height)} · x: ${Math.round(node.frame.absoluteX)}, y: ${Math.round(node.frame.absoluteY)}`; tooltip.replaceChildren(type, name, details); tooltip.style.left = `${clientX + 14}px`; tooltip.style.top = `${clientY + 14}px`; tooltip.classList.add("visible"); };
    const updateHover = (clientX, clientY) => { const nextNode = window.CanvasHitTest.find(pages, viewport, clientX, clientY); if (hoveredNode !== nextNode) { hoveredNode = nextNode; redraw(); } showTooltip(nextNode, clientX, clientY); };
    canvas.addEventListener("wheel", event => { event.preventDefault(); viewport.zoomAt(event.clientX, event.clientY, viewport.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12)); redraw(); }, { passive: false });
    canvas.addEventListener("pointerdown", event => { dragState = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX: viewport.panX, panY: viewport.panY }; canvas.setPointerCapture(event.pointerId); canvas.classList.add("dragging"); });
    canvas.addEventListener("pointermove", event => { if (dragState && event.pointerId === dragState.pointerId) { viewport.panX = dragState.panX + event.clientX - dragState.x; viewport.panY = dragState.panY + event.clientY - dragState.y; redraw(); return; } updateHover(event.clientX, event.clientY); });
    canvas.addEventListener("pointerleave", () => { if (!hoveredNode) return; hoveredNode = null; tooltip.classList.remove("visible"); redraw(); });
    const stopDragging = event => { if (!dragState || event.pointerId !== dragState.pointerId) return; dragState = null; canvas.classList.remove("dragging"); };
    canvas.addEventListener("pointerup", stopDragging);
    canvas.addEventListener("pointercancel", stopDragging);
    canvas.addEventListener("dblclick", () => { viewport.fit(); redraw(); });
    document.getElementById("zoom-in").addEventListener("click", () => { const rect = canvas.getBoundingClientRect(); viewport.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, viewport.scale * 1.15); redraw(); });
    document.getElementById("zoom-out").addEventListener("click", () => { const rect = canvas.getBoundingClientRect(); viewport.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, viewport.scale / 1.15); redraw(); });
    document.getElementById("fit").addEventListener("click", () => { viewport.fit(); redraw(); });
    document.getElementById("toggle-sidebar").addEventListener("click", () => { const open = document.body.classList.toggle("sidebar-open"); document.getElementById("toggle-sidebar").setAttribute("aria-expanded", String(open)); window.setTimeout(redraw, 220); });
    document.getElementById("close-inspector").addEventListener("click", () => { document.body.classList.remove("inspector-open"); window.setTimeout(redraw, 220); });
    window.addEventListener("resize", redraw);
    tree.render(pages);
    viewport.fit();
    redraw();
  },
};
'''

HTML_TEMPLATE = '''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sketch Canvas</title>
  <link rel="stylesheet" href="../_shared/style.css">
</head>
<body>
  <header>
    <button id="toggle-sidebar" title="显示或隐藏图层目录" aria-label="显示或隐藏图层目录">☰</button>
    <h1 id="title"></h1>
    <span id="meta"></span>
    <div id="tools"><button id="zoom-out">−</button><span id="scale"></span><button id="zoom-in">+</button><button id="fit" title="适应窗口">⊡</button></div>
  </header>
  <aside id="sidebar"><div id="sidebar-header"><span>图层目录</span><span id="page-count"></span></div><div id="layer-tree"></div></aside>
  <aside id="inspector"><div id="inspector-header"><span id="inspector-title">图层数据</span><button id="close-inspector" title="关闭数据面板">×</button></div><div id="inspector-content"><dl id="selection-summary"></dl><pre id="selection-data"></pre></div></aside>
  <div id="hover-tooltip"></div>
  <main id="workspace"><div id="canvas-shell"><canvas id="canvas"></canvas><div id="empty-state" hidden>这个分组没有可渲染的设计页面。</div></div></main>
  <script src="./canvas-data.js"></script>
  <script src="../_shared/viewport.js"></script>
  <script src="../_shared/renderer.js"></script>
  <script src="../_shared/hit-test.js"></script>
  <script src="../_shared/layer-tree.js"></script>
  <script src="../_shared/inspector.js"></script>
  <script src="../_shared/app.js"></script>
  <script>window.CanvasApp.start(window.CANVAS_DATA, { assetBase: "../../" });</script>
</body>
</html>
'''


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source_file:
        return json.load(source_file)


def find_object_by_id(value: Any, object_id: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("do_objectID") == object_id:
            return value
        for child in value.values():
            result = find_object_by_id(child, object_id)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = find_object_by_id(child, object_id)
            if result is not None:
                return result
    return None


def translate_absolute_positions(layer: dict[str, Any], offset_x: float, offset_y: float) -> None:
    layer["frame"]["absoluteX"] += offset_x
    layer["frame"]["absoluteY"] += offset_y
    if "visualFrame" in layer:
        layer["visualFrame"]["absoluteX"] += offset_x
        layer["visualFrame"]["absoluteY"] += offset_y
    for child in layer.get("children", []):
        translate_absolute_positions(child, offset_x, offset_y)


def count_layers(layer: dict[str, Any], counts: Counter[str]) -> None:
    counts[layer["type"]] += 1
    for child in layer.get("children", []):
        count_layers(child, counts)


def build_canvas_data(
    sketch_dir: Path,
    document: dict[str, Any],
    page_id: str,
    page_meta: dict[str, Any],
    artboards: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_reference = next(
        (item for item in document.get("pages", []) if item.get("_ref") == f"pages/{page_id}"),
        None,
    )
    if page_reference is None:
        raise ValueError(f"Page {page_id} was not referenced by document.json.")

    page_path = sketch_dir / f"{page_reference['_ref']}.json"
    page_data = load_json(page_path)
    design_pages = []
    for artboard_id, artboard_meta in (artboards if artboards is not None else page_meta.get("artboards", {})).items():
        raw_layer = find_object_by_id(page_data.get("layers", []), artboard_id)
        if raw_layer is None:
            raise ValueError(f"Artboard {artboard_id} was indexed but not found in {page_path}.")
        parsed_layer = parse_layer(raw_layer, sketch_dir, is_design_page=True)
        source_frame = raw_layer.get("frame", {})
        translate_absolute_positions(parsed_layer, source_frame.get("x", 0), source_frame.get("y", 0))
        parsed_layer["metaName"] = artboard_meta.get("name")
        design_pages.append(parsed_layer)

    counts: Counter[str] = Counter()
    for design_page in design_pages:
        count_layers(design_page, counts)

    if design_pages:
        min_x = min(page["frame"]["absoluteX"] for page in design_pages)
        min_y = min(page["frame"]["absoluteY"] for page in design_pages)
        max_x = max(page["frame"]["absoluteX"] + page["frame"]["width"] for page in design_pages)
        max_y = max(page["frame"]["absoluteY"] + page["frame"]["height"] for page in design_pages)
    else:
        min_x, min_y, max_x, max_y = 0, 0, 1280, 720

    return {
        "source": {
            "sketchDirectory": str(sketch_dir),
            "pageFile": str(page_path),
            "metaFile": str(sketch_dir / "meta.json"),
        },
        "sketchPage": {"id": page_id, "name": page_meta.get("name")},
        "bounds": {
            "minX": min_x,
            "minY": min_y,
            "maxX": max_x,
            "maxY": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        },
        "designPages": design_pages,
        "statistics": {"totalLayers": sum(counts.values()), "byType": dict(sorted(counts.items()))},
    }


def safe_directory_name(name: str, existing: set[str]) -> str:
    base_name = INVALID_DIRECTORY_CHARACTERS.sub("_", name).strip(". ") or "未命名分组"
    candidate = base_name
    index = 2
    while candidate.casefold() in existing:
        candidate = f"{base_name}-{index}"
        index += 1
    existing.add(candidate.casefold())
    return candidate


def group_platform(page_name: str, artboard_name: str) -> str:
    normalized_page_name = re.sub(r"\s+", "", page_name).casefold()
    if normalized_page_name in {"插件", "插件版"}:
        return "plugin"
    return "mobile" if re.match(r"^\s*h5", artboard_name, re.IGNORECASE) else "desktop"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_shared_files(output_dir: Path) -> None:
    shared_dir = output_dir / "_shared"
    files = {
        "style.css": STYLE_CSS,
        "viewport.js": VIEWPORT_JS,
        "renderer.js": RENDERER_JS,
        "hit-test.js": HIT_TEST_JS,
        "layer-tree.js": TREE_JS,
        "inspector.js": INSPECTOR_JS,
        "app.js": APP_JS,
    }
    for name, content in files.items():
        write_text(shared_dir / name, content)


def write_group_page(group_dir: Path, canvas_data: dict[str, Any]) -> None:
    write_json(group_dir / "canvas.json", canvas_data)
    write_text(
        group_dir / "canvas-data.js",
        "window.CANVAS_DATA = " + json.dumps(canvas_data, ensure_ascii=False) + ";\n",
    )
    write_text(group_dir / "index.html", HTML_TEMPLATE)


def write_index(output_dir: Path, entries: list[dict[str, Any]]) -> None:
    items = "\n".join(
        f'<li><a href="{entry["directory"]}/index.html">{entry["name"]}</a><span>{entry["artboardCount"]} 个设计页面 · {entry["layerCount"]} 图层</span></li>'
        for entry in entries
    )
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Sketch Canvas 分组</title>
<style>body{{font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif;margin:40px;background:#151c25;color:#edf3fa}}h1{{margin-bottom:8px}}p{{color:#9bacbf}}ul{{padding:0;max-width:760px}}li{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:8px 0;padding:14px 16px;border:1px solid #344154;border-radius:9px;background:#1d2733}}a{{color:#7fb9f7;text-decoration:none;font-weight:650}}span{{color:#9bacbf;font-size:13px}}</style></head>
<body><h1>Sketch Canvas</h1><p>按 <code>meta.json → pagesAndArtboards</code> 分组生成的离线画布。</p><ul>{items}</ul></body></html>'''
    write_text(output_dir / "index.html", html)


def generate_canvas_site(
    sketch_dir: Path = SKETCH_DIR,
    output_dir: Path = OUTPUT_DIR,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    sketch_dir = Path(sketch_dir)
    output_dir = Path(output_dir)
    document = load_json(sketch_dir / "document.json")
    meta = load_json(sketch_dir / "meta.json")
    write_shared_files(output_dir)

    existing_directories: set[str] = {"_shared"}
    manifest_entries = []
    page_groups = list(meta.get("pagesAndArtboards", {}).items())
    page_partitions: list[tuple[str, dict[str, Any], str, dict[str, Any]]] = []
    for page_id, page_meta in page_groups:
        group_name = page_meta.get("name") or page_id
        partitions = {"desktop": {}, "mobile": {}, "plugin": {}}
        for artboard_id, artboard_meta in page_meta.get("artboards", {}).items():
            platform = group_platform(group_name, artboard_meta.get("name") or "")
            partitions[platform][artboard_id] = artboard_meta
        has_artboards = any(partitions.values())
        if not has_artboards:
            continue
        for platform, artboards in partitions.items():
            if not artboards:
                continue
            page_partitions.append((page_id, page_meta, platform, artboards))

    for index, (page_id, page_meta, platform, artboards) in enumerate(page_partitions, start=1):
        group_name = page_meta.get("name") or page_id
        label = {"desktop": "电脑端", "mobile": "移动端（H5）", "plugin": "插件版"}[platform]
        display_name = group_name if platform == "plugin" else f"{group_name} · {label}"
        directory_name = safe_directory_name(display_name, existing_directories)
        canvas_data = build_canvas_data(sketch_dir, document, page_id, page_meta, artboards)
        group_dir = output_dir / directory_name
        write_group_page(group_dir, canvas_data)
        manifest_entries.append(
            {
                "id": f"{page_id}:{platform}",
                "name": display_name,
                "directory": directory_name,
                "platform": platform,
                "artboardCount": len(canvas_data["designPages"]),
                "layerCount": canvas_data["statistics"]["totalLayers"],
            }
        )
        if progress_callback:
            progress_callback(index, len(page_partitions), display_name)

    preview_dir = sketch_dir / "previews"
    previews = [
        {"name": preview_path.stem, "path": preview_path.relative_to(sketch_dir).as_posix()}
        for preview_path in sorted(preview_dir.glob("*"))
        if preview_path.is_file()
    ]
    manifest = {"source": str(sketch_dir / "meta.json"), "groups": manifest_entries, "previews": previews}
    write_json(output_dir / "manifest.json", manifest)
    write_index(output_dir, manifest_entries)
    return manifest_entries


def main() -> None:
    groups = generate_canvas_site()
    print(f"Generated {len(groups)} group directories: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
