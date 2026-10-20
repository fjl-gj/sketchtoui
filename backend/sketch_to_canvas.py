from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT_PATH = Path("fixtures/sketch/test_001/test/注册页.parsed.json")
DEFAULT_OUTPUT_PATH = Path("fixtures/sketch/test_001/test/注册页.preview.html")

HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sketch 预览</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 720px; background: #12161d; color: #eef2f7; }
    header { height: 58px; display: flex; align-items: center; gap: 18px; padding: 0 18px; border-bottom: 1px solid #293241; background: #1a2029; }
    h1 { margin: 0; font-size: 15px; font-weight: 650; }
    #meta { color: #9cabbd; font-size: 12px; }
    #tools { display: flex; align-items: center; gap: 8px; margin-left: auto; }
    button { width: 32px; height: 30px; border: 1px solid #394556; border-radius: 7px; background: #232c38; color: #edf3fa; cursor: pointer; font-size: 18px; }
    button:hover { background: #304053; }
    #scale { min-width: 60px; text-align: center; color: #b7c5d7; font-size: 12px; }
    #workspace { height: calc(100vh - 58px); overflow: auto; padding: 48px; background-color: #151b23; background-image: linear-gradient(45deg, #1a222d 25%, transparent 25%), linear-gradient(-45deg, #1a222d 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #1a222d 75%), linear-gradient(-45deg, transparent 75%, #1a222d 75%); background-size: 24px 24px; background-position: 0 0, 0 12px, 12px -12px, -12px 0; }
    #canvas-shell { width: max-content; margin: auto; border-radius: 5px; overflow: hidden; box-shadow: 0 20px 70px rgba(0, 0, 0, .48), 0 0 0 1px rgba(255, 255, 255, .12); background: #fff; }
    canvas { display: block; }
  </style>
</head>
<body>
  <header>
    <h1 id="title"></h1>
    <span id="meta"></span>
    <div id="tools">
      <button id="zoom-out" aria-label="缩小">−</button>
      <span id="scale"></span>
      <button id="zoom-in" aria-label="放大">+</button>
      <button id="fit" aria-label="适应窗口" title="适应窗口">⊡</button>
    </div>
  </header>
  <main id="workspace"><div id="canvas-shell"><canvas id="canvas"></canvas></div></main>
  <script id="page-data" type="application/json">__PAGE_DATA__</script>
  <script>
    const documentData = JSON.parse(document.getElementById("page-data").textContent);
    const page = documentData.designPage;
    const workspace = document.getElementById("workspace");
    const canvas = document.getElementById("canvas");
    const context = canvas.getContext("2d");
    const imageCache = new Map();
    let scale = 1;

    document.getElementById("title").textContent = page.name;
    document.getElementById("meta").textContent = `${page.frame.width} × ${page.frame.height} · ${documentData.statistics.totalLayers} 图层`;

    function rgba(color) {
      if (!color) return null;
      return `rgba(${Math.round(color.red * 255)}, ${Math.round(color.green * 255)}, ${Math.round(color.blue * 255)}, ${color.alpha ?? 1})`;
    }

    function parsePoint(value) {
      const match = /^\{\s*([^,]+),\s*([^}]+)\}$/.exec(value || "");
      return match ? [Number(match[1]), Number(match[2])] : [0, 0];
    }

    function enabled(items) {
      return (items || []).filter(item => item.enabled);
    }

    function applyShadow(style) {
      const shadow = enabled(style.shadows)[0];
      if (!shadow || !shadow.color) return;
      context.shadowColor = rgba(shadow.color);
      context.shadowBlur = shadow.blurRadius || 0;
      context.shadowOffsetX = shadow.offsetX || 0;
      context.shadowOffsetY = shadow.offsetY || 0;
    }

    function resetShadow() {
      context.shadowColor = "transparent";
      context.shadowBlur = 0;
      context.shadowOffsetX = 0;
      context.shadowOffsetY = 0;
    }

    function roundedRect(width, height, radii) {
      const radius = Math.max(0, Math.min(width / 2, height / 2, Number((radii || [])[0] || 0)));
      context.beginPath();
      context.moveTo(radius, 0);
      context.lineTo(width - radius, 0);
      context.quadraticCurveTo(width, 0, width, radius);
      context.lineTo(width, height - radius);
      context.quadraticCurveTo(width, height, width - radius, height);
      context.lineTo(radius, height);
      context.quadraticCurveTo(0, height, 0, height - radius);
      context.lineTo(0, radius);
      context.quadraticCurveTo(0, 0, radius, 0);
      context.closePath();
    }

    function paintCurrentPath(style) {
      const fill = enabled(style.fills)[0];
      if (fill && fill.color) {
        context.fillStyle = rgba(fill.color);
        context.globalAlpha *= fill.opacity ?? 1;
        context.fill();
        context.globalAlpha /= fill.opacity ?? 1;
      }
      const border = enabled(style.borders)[0];
      if (border && border.color && border.thickness) {
        context.strokeStyle = rgba(border.color);
        context.lineWidth = border.thickness;
        context.globalAlpha *= border.opacity ?? 1;
        context.stroke();
        context.globalAlpha /= border.opacity ?? 1;
      }
    }

    function drawBox(node) {
      const style = node.style || {};
      const hasPaint = enabled(style.fills).length || enabled(style.borders).length;
      if (!hasPaint) return;
      applyShadow(style);
      roundedRect(node.frame.width, node.frame.height, style.cornerRadii);
      paintCurrentPath(style);
      resetShadow();
    }

    function drawPath(node) {
      const points = node.points || [];
      if (!points.length) return;
      const width = node.frame.width;
      const height = node.frame.height;
      context.beginPath();
      points.forEach((point, index) => {
        const [x, y] = parsePoint(point.point);
        const pointX = x * width;
        const pointY = y * height;
        if (index === 0) context.moveTo(pointX, pointY);
        else context.lineTo(pointX, pointY);
      });
      context.closePath();
      applyShadow(node.style || {});
      paintCurrentPath(node.style || {});
      resetShadow();
    }

    function drawText(node) {
      const text = node.text || {};
      const run = (text.runs || [])[0] || {};
      const font = run.font || {};
      const size = font.size || Math.max(12, node.frame.height);
      const family = font.name || "sans-serif";
      context.font = `${size}px "${family}", "PingFang SC", "Microsoft YaHei", sans-serif`;
      context.fillStyle = rgba(run.color) || "#111827";
      context.textBaseline = "top";
      const alignment = run.alignment;
      context.textAlign = alignment === 1 ? "center" : alignment === 2 ? "right" : "left";
      const textX = alignment === 1 ? node.frame.width / 2 : alignment === 2 ? node.frame.width : 0;
      const lineHeight = Math.max(size * 1.25, node.frame.height / Math.max(1, String(text.content || "").split("\n").length));
      String(text.content || "").split("\n").forEach((line, index) => context.fillText(line, textX, index * lineHeight));
    }

    function getImage(reference) {
      if (!reference) return null;
      if (!imageCache.has(reference)) {
        const image = new Image();
        image.onload = render;
        image.onerror = render;
        image.src = reference;
        imageCache.set(reference, image);
      }
      return imageCache.get(reference);
    }

    function drawImage(node) {
      const image = getImage(node.image && node.image.reference);
      if (image && image.complete && image.naturalWidth) {
        context.drawImage(image, 0, 0, node.frame.width, node.frame.height);
      } else {
        context.fillStyle = "#d7dee8";
        context.fillRect(0, 0, node.frame.width, node.frame.height);
      }
    }

    function drawLayer(node) {
      if (!node.visible) return;
      const width = node.frame.width;
      const height = node.frame.height;
      context.save();
      context.globalAlpha = node.style?.opacity ?? 1;
      context.translate(node.frame.absoluteX + width / 2, node.frame.absoluteY + height / 2);
      context.rotate((node.rotation || 0) * Math.PI / 180);
      context.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1);
      context.translate(-width / 2, -height / 2);
      if (["design_page", "group", "rectangle"].includes(node.type)) drawBox(node);
      if (node.type === "shape_path") drawPath(node);
      if (node.type === "text") drawText(node);
      if (node.type === "image") drawImage(node);
      context.restore();
      (node.children || []).forEach(drawLayer);
    }

    function render() {
      const ratio = window.devicePixelRatio || 1;
      const width = page.frame.width * scale;
      const height = page.frame.height * scale;
      canvas.width = Math.max(1, Math.round(width * ratio));
      canvas.height = Math.max(1, Math.round(height * ratio));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio * scale, 0, 0, ratio * scale, 0, 0);
      context.clearRect(0, 0, page.frame.width, page.frame.height);
      drawLayer(page);
      document.getElementById("scale").textContent = `${Math.round(scale * 100)}%`;
    }

    function setScale(nextScale) {
      scale = Math.max(0.2, Math.min(2.5, nextScale));
      render();
    }

    function fit() {
      const availableWidth = Math.max(320, workspace.clientWidth - 96);
      const availableHeight = Math.max(320, workspace.clientHeight - 96);
      setScale(Math.min(availableWidth / page.frame.width, availableHeight / page.frame.height, 1));
    }

    document.getElementById("zoom-in").addEventListener("click", () => setScale(scale * 1.15));
    document.getElementById("zoom-out").addEventListener("click", () => setScale(scale / 1.15));
    document.getElementById("fit").addEventListener("click", fit);
    window.addEventListener("resize", fit);
    fit();
  </script>
</body>
</html>
'''


def generate_canvas_preview(input_path: Path, output_path: Path) -> Path:
    with Path(input_path).open("r", encoding="utf-8") as source_file:
        page_data: dict[str, Any] = json.load(source_file)

    embedded_data = json.dumps(page_data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__PAGE_DATA__", embedded_data)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write(html)
    return output_path


def main() -> None:
    output_path = generate_canvas_preview(DEFAULT_INPUT_PATH, DEFAULT_OUTPUT_PATH)
    print(f"Preview: {output_path}")


if __name__ == "__main__":
    main()
